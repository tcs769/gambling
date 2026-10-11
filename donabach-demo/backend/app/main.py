"""Donabach demo API.

    uvicorn app.main:app --reload --port 8000

Every response is typed (see `app.api_models`). The API is stateless apart from the uploaded
documents: the frontend sends the household with each planning request.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import builder, forecast, warmup, whatif
from app.api_models import (
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
    WhatIfRequest,
    WhatIfResponse,
    YearDetailRequest,
)
from app.ml import adapters
from app.ml.adapters import NotConnected
from app.planner import explain, plan
from app.planner.strategies import CHOICES, Strategy
from app.sim.simulate import build_inputs
from app.store import NotAPdf, store


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Compile (or load from cache) the simulation kernels so the first request is fast.
    warmup.warm()
    yield


app = FastAPI(title="Donabach demo API", version="0.1.0")
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
    )


# --- Documents --------------------------------------------------------------------------------


@app.post("/documents/sample", response_model=DocumentList)
def load_sample_documents() -> DocumentList:
    return DocumentList(documents=[d.info() for d in store.add_samples()])


@app.post("/documents/upload", response_model=DocumentList)
async def upload_documents(files: list[UploadFile] = File(...)) -> DocumentList:
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


@app.post("/plan", response_model=PlanResponse)
def make_plan(request: PlanRequest) -> PlanResponse:
    return plan.build_plan(request.household, request.n_paths, request.demo_mode, request.seed, request.shock)


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
    result = plan.build_plan(household, request.n_paths, request.demo_mode, request.seed, shock)
    return WhatIfResponse(changes=changes, household=household, shock=shock, plan=result)
