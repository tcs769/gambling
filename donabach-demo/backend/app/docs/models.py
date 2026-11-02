"""Models returned by the document parser. The API embeds these directly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
FieldKind = Literal["money", "integer", "percent", "text"]
DocKind = Literal["form_1040", "brokerage_statement", "retirement_401k", "roth_ira", "unknown"]


class BBox(BaseModel):
    """Rectangle in PDF points, origin at the top-left of the page (pdfplumber convention)."""

    x0: float
    top: float
    x1: float
    bottom: float


class ParsedField(BaseModel):
    """One value read from a document.

    Confidence is rule-based. `high`: found, and every cross-check it belongs to passes (or it
    is in no check). `medium`: found, but it is the stated total or derived line of a failed
    cross-check (`flag` says why). `low`: not found (`value` and `bbox` are None, `flag` says
    what was missing).
    """

    key: str  # stable machine key, e.g. "agi_11" or "holding_3_value"
    label: str  # human label for the UI, sentence case
    group: str  # UI sub-group, e.g. "Income" or "Holdings"
    kind: FieldKind
    value: float | str | None  # None when missing; percents are 45.0 for 45%
    page: int | None  # 1-based
    bbox: BBox | None  # box around the value text, so the UI can highlight it
    confidence: Confidence
    flag: str | None  # plain-language reason when medium or low
    meta: dict[str, str | float] = Field(default_factory=dict)  # row metadata (fund name, ...)


class CrossCheck(BaseModel):
    """One consistency check between fields of a document."""

    name: str
    passed: bool
    detail: str  # a sentence with the numbers involved
    keys: list[str]  # every field the check reads


class ParsedDocument(BaseModel):
    doc_kind: DocKind
    title: str
    page_sizes: list[tuple[float, float]]  # (width, height) per page of the whole PDF, in points
    first_page: int | None = None  # 1-based, absolute: where this document starts in the PDF
    last_page: int | None = None  # 1-based, absolute: the last page of this document
    fields: list[ParsedField]
    checks: list[CrossCheck]
