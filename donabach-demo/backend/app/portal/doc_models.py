"""Request and response models of the portal's document API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.docs.models import ParsedDocument
from app.schemas import Household


class PortalDocuments(BaseModel):
    """One uploaded PDF and the documents found in it (pages are absolute in this PDF)."""

    id: str
    name: str
    size_bytes: int
    pages: int
    documents: list[ParsedDocument]


class PortalAnswers(BaseModel):
    """The goal questions the customer answers (same limits as `app.api_models.Answers`)."""

    retirement_age: int = Field(ge=50, le=70)
    retirement_spending: float = Field(ge=0)
    college_starts_in_years: int | None = Field(None, ge=0, le=30)
    college_annual_cost: float = Field(0.0, ge=0)
    college_years: int = Field(4, ge=0, le=8)
    home_purchase_in_years: int | None = Field(None, ge=0, le=30)
    home_down_payment: float = Field(0.0, ge=0)
    social_security_annual: float = Field(ge=0)
    social_security_start_age: int = Field(67, ge=62, le=70)
    charitable_giving: float = Field(0.0, ge=0)
    income_change: Literal["none", "job_loss", "raise"] = "none"  # not used by the household builder


class PortalHouseholdRequest(BaseModel):
    document_id: str
    overrides: dict[str, float] = Field(
        default_factory=dict, description="Values the customer corrected, by field key"
    )
    answers: PortalAnswers


class Correction(BaseModel):
    """One value the customer changed, with what the document said."""

    key: str
    label: str
    document_value: float | str | None
    corrected_value: float | str


class PortalHouseholdResponse(BaseModel):
    household: Household
    corrections: list[Correction]
    documents: list[ParsedDocument]  # re-checked after the corrections: flags clear when the sums match
