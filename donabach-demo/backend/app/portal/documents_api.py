"""Portal document API: load or upload the customer's PDF, read it, and build the household."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import builder
from app.api_models import Answers
from app.docs import smith
from app.docs.parse import apply_cross_checks
from app.portal.doc_models import (
    Correction,
    PortalAnswers,
    PortalDocuments,
    PortalHouseholdRequest,
    PortalHouseholdResponse,
)
from app.store import NotAPdf, StoredDocument, store

router = APIRouter(prefix="/portal")


def _documents(doc: StoredDocument) -> PortalDocuments:
    return PortalDocuments(
        id=doc.id,
        name=doc.name,
        size_bytes=doc.size_bytes,
        pages=doc.pages,
        documents=store.bundle(doc.id),
    )


@router.post("/documents/sample", response_model=PortalDocuments)
def load_sample() -> PortalDocuments:
    return _documents(store.add_sample_bundle())


@router.post("/documents/upload", response_model=PortalDocuments)
async def upload(file: Annotated[UploadFile, File()]) -> PortalDocuments:
    try:
        doc = store.add_bundle_upload(file.filename or "document.pdf", await file.read())
    except NotAPdf as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _documents(doc)


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: str) -> FileResponse:
    try:
        doc = store.get(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No document with id {doc_id}") from None
    return FileResponse(doc.path, media_type="application/pdf", filename=doc.name, content_disposition_type="inline")


@router.post("/household", response_model=PortalHouseholdResponse)
def create_household(request: PortalHouseholdRequest) -> PortalHouseholdResponse:
    try:
        documents = store.bundle(request.document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No document with id {request.document_id}") from None
    fields = {f.key: f for d in documents for f in d.fields}
    unknown = sorted(set(request.overrides) - set(fields))
    if unknown:
        raise HTTPException(status_code=422, detail=f"There is no value named {', '.join(unknown)} in these documents.")

    corrections = []
    for key, value in request.overrides.items():
        field = fields[key]
        corrections.append(
            Correction(key=key, label=field.label, document_value=field.value, corrected_value=value)
        )
        field.value = value
    for doc in documents:  # a corrected total can clear its flag (or raise a new one)
        doc.checks = apply_cross_checks(doc.doc_kind, doc.fields)

    try:
        household = builder.build_household(documents, dict(request.overrides), Answers(**request.answers.model_dump(exclude={"income_change"})))
    except builder.MissingFieldsError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing": [m.model_dump() for m in exc.missing]},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PortalHouseholdResponse(household=household, corrections=corrections, documents=documents)


@router.get("/defaults", response_model=PortalAnswers)
def defaults() -> PortalAnswers:
    """The goal answers prefilled with John Smith's (from fixtures/showcase.json)."""
    h = smith.load_showcase()
    g, ss = h["goals"], h["social_security"]
    return PortalAnswers(
        retirement_age=g["retirement_age"],
        retirement_spending=g["retirement_spending"],
        college_starts_in_years=g["college_starts_in_years"],
        college_annual_cost=g["college_annual_cost"],
        college_years=g["college_years"],
        home_purchase_in_years=g["home_purchase_in_years"],
        home_down_payment=g["home_down_payment"],
        social_security_annual=ss["annual_benefit"],
        social_security_start_age=ss["start_age"],
        charitable_giving=g.get("charitable_giving", 0.0),
    )
