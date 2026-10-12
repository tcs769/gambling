"""Donabach demo API.

    uvicorn app.main:app --reload --port 8000

Every response is typed (see `app.api_models`). The API is stateless apart from the uploaded
documents: the frontend sends the household with each planning request.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import builder, forecast, showcase, warmup, whatif
from app.api_models import (
    AdaptiveJob,
    DocumentList,
    ForecastRequest,
    ForecastResponse,
    HouseholdProfile,
    HouseholdRequest,
    ModelsStatus,
    ModelStatus,
    ParseResponse,
    PlanRequest,
    PlanResponse,
    ShowcaseRequest,
    ShowcaseResponse,
    ShowcaseWaterfall,
    WhatIfRequest,
    WhatIfResponse,
    YearDetailRequest,
)
from app.ml import adapters
from app.ml.adapters import NotConnected
from app.planner import adaptive_service, explain, plan
from app.planner.strategies import CHOICES, Strategy
from app.sim.simulate import build_inputs
from app.store import NotAPdf, store


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Compile (or load from cache) the simulation kernels so the first request is fast, then start
    # computing the demo household's adaptive plan in the background so the Plan screen can show it at once.
    warmup.warm()
    warmup.precompute_demo()
    warmup.precompute_showcase()
    yield


app = FastAPI(title="Donabach demo API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _status(model: str, result) -> ModelStatus:
    if isinstance(result, NotConnected):
        return ModelStatus(model=model, connected=False, reason=result.reason, expected_path=result.expected_path)
    return ModelStatus(model=model, connected=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models/status", response_model=ModelsStatus)
def models_status() -> ModelsStatus:
    return ModelsStatus(
        recommender=_status("recommender", adapters.load_recommender()),
        forecaster=_status("forecaster", adapters.load_forecaster()),
        policy=_status("policy", adapters.load_policy_model()),
        value=_status("value", adapters.load_value_model()),
    )


# --- Documents --------------------------------------------------------------------------------


@app.post("/documents/sample", response_model=DocumentList)
def load_sample_documents() -> DocumentList:
    return DocumentList(documents=[d.info() for d in store.add_samples()])


@app.post("/documents/upload", response_model=DocumentList)
async def upload_documents(files: Annotated[list[UploadFile], File()]) -> DocumentList:
    stored = []
    for upload in files:
        try:
            stored.append(store.add_upload(upload.filename or "document.pdf", await upload.read()))
        except NotAPdf as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DocumentList(documents=[d.info() for d in stored])


def _document(doc_id: str):
    try:
        return store.get(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No document with id {doc_id}") from None


@app.post("/documents/{doc_id}/parse", response_model=ParseResponse)
def parse_document(doc_id: str) -> ParseResponse:
    doc = _document(doc_id)
    return ParseResponse(document=doc.info(), parsed=store.parsed(doc_id))


@app.get("/documents/{doc_id}/file")
def document_file(doc_id: str) -> FileResponse:
    doc = _document(doc_id)
    return FileResponse(doc.path, media_type="application/pdf", filename=doc.name, content_disposition_type="inline")


# --- Household --------------------------------------------------------------------------------


@app.post("/household", response_model=HouseholdProfile)
def create_household(request: HouseholdRequest) -> HouseholdProfile:
    documents = []
    for doc_id in request.document_ids:
        _document(doc_id)
        documents.append(store.parsed(doc_id))
    try:
        household = builder.build_household(documents, request.overrides, request.answers)
    except builder.MissingFieldsError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing": [m.model_dump() for m in exc.missing]},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return builder.household_profile(household)


# --- Forecast and plan ------------------------------------------------------------------------


@app.post("/forecast", response_model=ForecastResponse)
def income_forecast(request: ForecastRequest) -> ForecastResponse:
    seed = plan.resolve_seed(request.demo_mode, request.seed)
    return forecast.forecast(request.household, request.n_paths, seed)


def _with_adaptive(
    response: PlanResponse, household, adaptive: bool, rollouts: int, n_eval_paths: int, risk_aversion: float, shock
) -> PlanResponse:
    """Attach the adaptive plan: at once if it is already known, else the id of the job computing it."""
    if not adaptive:
        return response
    section, job = adaptive_service.request_plan(
        household,
        Strategy.from_choices(response.strategy.choices),
        response.settings.seed,
        n_eval_paths,
        shock,
        risk_aversion,
        rollouts,
    )
    return response.model_copy(update={"adaptive": section, "adaptive_job": job})


@app.post("/plan", response_model=PlanResponse)
def make_plan(request: PlanRequest) -> PlanResponse:
    response = plan.build_plan(
        request.household, request.n_paths, request.demo_mode, request.seed, request.shock,
        request.n_eval_paths, request.risk_aversion, request.planning_style,
    )
    return _with_adaptive(
        response, request.household, request.adaptive, request.adaptive_rollouts, request.n_eval_paths,
        request.risk_aversion, request.shock,
    )


@app.get("/plan/adaptive/{job_id}", response_model=AdaptiveJob)
def adaptive_job(job_id: str) -> AdaptiveJob:
    job = adaptive_service.service.job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No adaptive job with id {job_id}")
    return job


@app.delete("/plan/adaptive/{job_id}", status_code=204)
def cancel_adaptive_job(job_id: str) -> None:
    """The caller no longer wants this job (its plan was replaced). It stops once nobody else is waiting for it."""
    if not adaptive_service.service.cancel(job_id):
        raise HTTPException(status_code=404, detail=f"No adaptive job with id {job_id}")


@app.post("/plan/year-detail", response_model=explain.YearDetail)
def year_detail(request: YearDetailRequest) -> explain.YearDetail:
    if set(request.choices) != set(CHOICES):
        raise HTTPException(status_code=422, detail=f"choices must contain exactly {list(CHOICES)}")
    try:
        strategy = Strategy.from_choices(request.choices)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid strategy choices: {exc}") from exc
    inputs = build_inputs(request.household, deterministic=True, shock=request.shock)
    return explain.year_detail(inputs, strategy, request.year_index)


@app.post("/plan/whatif", response_model=WhatIfResponse)
def plan_whatif(request: WhatIfRequest) -> WhatIfResponse:
    try:
        household, shock, changes = whatif.apply_whatif(
            request.household, request.presets, request.edits, request.shock
        )
    except whatif.WhatIfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = plan.build_plan(
        household, request.n_paths, request.demo_mode, request.seed, shock, request.n_eval_paths, request.risk_aversion,
        request.planning_style,
    )
    result = _with_adaptive(
        result, household, request.adaptive, request.adaptive_rollouts, request.n_eval_paths, request.risk_aversion, shock
    )
    return WhatIfResponse(changes=changes, household=household, shock=shock, plan=result)


@app.get("/showcase", response_model=ShowcaseResponse)
def get_showcase() -> ShowcaseResponse:
    """The showcase household: its summary card, the waterfall with every strategy on, and the whole plan over time against the
    advisor (both measures of the advantage). All of it is worked out once and kept."""
    return showcase.showcase()


@app.post("/showcase/analysis", response_model=ShowcaseWaterfall)
def showcase_analysis(request: ShowcaseRequest) -> ShowcaseWaterfall:
    """The strategy waterfall, median advantage only, with only the strategies in `enabled` switched on."""
    prepared = showcase.prepare()
    if request.enabled is not None:
        known = {step.key for step in showcase.waterfall_strategies(prepared.strategy)}
        unknown = sorted(set(request.enabled) - known)
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown strategies {unknown}; expected some of {sorted(known)}")
    return showcase.analyze(prepared, request.enabled)
