"""John Smith's document bundle: the PDF, the parser on it, the household built from it, the portal API."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pdfplumber
import pytest
from app import builder
from app.api_models import Answers
from app.docs import generate, smith
from app.docs.models import ParsedDocument
from app.docs.parse import apply_cross_checks, parse_bundle, parse_document
from app.portal.documents_api import router
from app.tax.engine import TaxInputs, compute_return
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

REPO = Path(__file__).resolve().parents[2]
PDF = REPO / "fixtures" / "smith_documents.pdf"
SHOWCASE = json.loads((REPO / "fixtures" / "showcase.json").read_text(encoding="utf-8"))["household"]
KINDS = ["form_1040", "brokerage_statement", "retirement_401k", "roth_ira"]

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(scope="module")
def docs() -> list[ParsedDocument]:
    return parse_bundle(PDF)


@pytest.fixture(scope="module")
def fields(docs):
    return {f.key: f for d in docs for f in d.fields}


def expected_values() -> dict[str, float | str]:
    a, person = SHOWCASE["accounts"], SHOWCASE["people"][0]
    ret = compute_return(
        TaxInputs(
            wages=person["wages"], interest=838.0, qualified_dividends=11624.0, ordinary_dividends=11624.0,
            net_capital_gain=0.0, children_under_17=1,
        )
    )
    out: dict[str, float | str] = {
        "taxpayer_name": "John Smith", "filing_status": "Married filing jointly", "taxpayer_age": person["age"],
        "children_under_17": 1, "child_age_1": SHOWCASE["children_ages"][0], "w2_wages_taxpayer": person["wages"],
        "wages_1a": ret.wages, "taxable_interest_2b": 838.0, "qualified_dividends_3a": 11624.0,
        "ordinary_dividends_3b": 11624.0, "capital_gain_7": 0.0, "total_income_9": ret.total_income,
        "adjustments_10": ret.total_income - ret.agi, "agi_11": ret.agi,
        "standard_deduction_12": ret.standard_deduction, "taxable_income_15": ret.taxable_income,
        "total_tax_24": ret.federal_total,
        "brokerage_total_value": a["brokerage_value"], "brokerage_cost_basis": a["brokerage_basis"],
        "brokerage_unrealized_gain": a["brokerage_value"] - a["brokerage_basis"], "brokerage_cash": a["cash"],
        "k401_total_balance": a["pretax_balance"], "k401_balance_taxpayer": a["pretax_balance"],
        "k401_contrib_taxpayer": 0.0, "roth_total_balance": a["roth_balance"], "roth_contrib_ytd": 0.0,
    }
    return out


def answers() -> dict:
    return client.get("/portal/defaults").json()


# --- the PDF ---------------------------------------------------------------------------------


def test_the_committed_pdf_equals_the_regenerated_bytes():
    assert PDF.exists(), "run `python -m app.docs.smith`"
    assert PDF.read_bytes() == smith.build_bundle()


def test_generation_is_deterministic_and_cli_writes_the_file(tmp_path):
    out = tmp_path / "x.pdf"
    assert smith.main(["--out", str(out)]) == 0
    assert out.read_bytes() == smith.build_bundle() == smith.build_bundle()


def test_every_page_has_the_fictional_footer_and_only_fake_identifiers():
    with pdfplumber.open(PDF) as pdf:
        assert len(pdf.pages) == 4
        for page in pdf.pages:
            assert (page.width, page.height) == tuple(letter)
            text = page.extract_text() or ""
            assert "SAMPLE – FICTIONAL" in text
            assert "Fictional document created for the Waramoug demo. Not a real form, statement or account." in text
            assert set(re.findall(r"\b\d{3}-\d{2}-\d{4}\b", text)) <= {"000-00-0000"}
            assert set(re.findall(r"\bXXXX-\d{4}\b", text)) <= {"XXXX-1234", "XXXX-2201", "XXXX-3301"}
            assert not re.findall(r"\b\d{9,}\b", text)  # no long digit runs that could pass for an account number
        assert "Donabach" not in " ".join(page.extract_text() or "" for page in pdf.pages)


def test_the_old_sample_pdfs_use_the_waramoug_wording_and_still_parse():
    for kind, name in generate.DOC_FILENAMES.items():
        path = REPO / "fixtures" / "sample_docs" / name
        with pdfplumber.open(path) as pdf:
            assert "created for the Waramoug demo" in pdf.pages[0].extract_text()
        doc = parse_document(path)
        assert doc.doc_kind == kind and (doc.first_page, doc.last_page) == (1, 1)
        assert parse_bundle(path) == [doc]


# --- the parser ------------------------------------------------------------------------------


def test_four_documents_with_absolute_pages(docs):
    assert [d.doc_kind for d in docs] == KINDS
    assert [(d.first_page, d.last_page) for d in docs] == [(1, 1), (2, 2), (3, 3), (4, 4)]
    for d in docs:
        assert len(d.page_sizes) == 4
        assert {f.page for f in d.fields} == {d.first_page}
        assert all(f.bbox is not None for f in d.fields)


def test_bboxes_sit_on_the_right_absolute_page(docs):
    with pdfplumber.open(PDF) as pdf:
        for d in docs:
            for f in d.fields:
                if f.kind == "text":
                    continue
                crop = pdf.pages[f.page - 1].crop((f.bbox.x0, f.bbox.top, f.bbox.x1, f.bbox.bottom))
                assert (crop.extract_text() or "").strip(), f.key


def test_every_value_equals_the_fixture(fields):
    for key, want in expected_values().items():
        got = fields[key].value
        if isinstance(want, str):
            assert got == want, key
        else:
            assert got == pytest.approx(want, abs=0.005), key


def test_holdings_roth_and_401k_allocations_add_up(fields):
    a = SHOWCASE["accounts"]
    values = [fields[f"holding_{i}_value"].value for i in range(1, 8)]
    bases = [fields[f"holding_{i}_basis"].value for i in range(1, 8)]
    assert "holding_8_value" not in fields
    assert sum(values) == pytest.approx(a["brokerage_value"] - 1.0, abs=0.005)  # the planted $1.00
    assert sum(bases) == pytest.approx(a["brokerage_basis"], abs=0.005)
    gains = sum(1 for v, b in zip(values, bases, strict=True) if v > 2 * b)
    assert gains >= 5  # large unrealized gains in most positions
    alloc = [(fields[f"alloc_{i}_value"], fields[f"alloc_{i}_pct"]) for i in range(1, 5)]
    assert sum(v.value for v, _ in alloc) == pytest.approx(a["pretax_balance"], abs=0.005)
    equity = sum(v.value for v, _ in alloc if v.meta["asset_class"] == "equity")
    assert equity / a["pretax_balance"] == pytest.approx(a["pretax_equity_share"], abs=1e-6)
    roth = [fields[f"roth_alloc_{i}_value"] for i in (1, 2)]
    assert sum(v.value for v in roth) == pytest.approx(a["roth_balance"], abs=0.005)
    assert {v.meta["asset_class"] for v in roth} == {"equity"}
    assert all(pct.value == round(v.value / a["pretax_balance"] * 100, 1) for v, pct in alloc)


def test_no_spouse_fields_and_exactly_one_flagged_field(docs, fields):
    assert not [k for k in fields if "spouse" in k]
    flagged = [f for d in docs for f in d.fields if f.confidence != "high"]
    assert [(f.key, f.confidence) for f in flagged] == [("brokerage_total_value", "medium")]
    assert "$1" in flagged[0].flag and "add up" in flagged[0].flag
    assert [c.name for d in docs for c in d.checks if not c.passed] == ["Holdings add up to the statement total"]


def test_correcting_the_total_clears_its_flag(docs):
    brokerage = next(d for d in docs if d.doc_kind == "brokerage_statement").model_copy(deep=True)
    total = next(f for f in brokerage.fields if f.key == "brokerage_total_value")
    total.value = total.value - 1.0  # now equal to the holdings' sum
    checks = apply_cross_checks(brokerage.doc_kind, brokerage.fields)
    assert total.confidence == "high" and total.flag is None
    assert next(c for c in checks if c.name.startswith("Holdings add up")).passed
    # the printed unrealized gain was computed from the old total, so that line is now the odd one out
    assert [f.key for f in brokerage.fields if f.confidence != "high"] == ["brokerage_unrealized_gain"]


def test_correcting_the_short_holding_instead_clears_everything(docs):
    brokerage = next(d for d in docs if d.doc_kind == "brokerage_statement").model_copy(deep=True)
    holding = next(f for f in brokerage.fields if f.key == "holding_5_value")
    holding.value += 1.0
    assert all(c.passed for c in apply_cross_checks(brokerage.doc_kind, brokerage.fields))
    assert all(f.confidence == "high" and f.flag is None for f in brokerage.fields)


def test_roth_statement_checks_and_a_bad_allocation_is_flagged(docs):
    roth = next(d for d in docs if d.doc_kind == "roth_ira").model_copy(deep=True)
    assert all(c.passed for c in roth.checks) and len(roth.checks) == 2
    next(f for f in roth.fields if f.key == "roth_alloc_1_value").value += 5
    apply_cross_checks("roth_ira", roth.fields)
    bad = {f.key for f in roth.fields if f.confidence == "medium"}
    assert bad == {"roth_total_balance"}


def test_optional_cash_and_spouse_rows_on_the_old_statements():
    old = {k: parse_document(REPO / "fixtures" / "sample_docs" / n) for k, n in generate.DOC_FILENAMES.items()}
    assert "brokerage_cash" not in {f.key for f in old["brokerage_statement"].fields}
    keys = {f.key for f in old["form_1040"].fields}
    assert {"spouse_age", "w2_wages_spouse"} <= keys
    assert {"k401_balance_spouse", "k401_contrib_spouse"} <= {f.key for f in old["retirement_401k"].fields}


def test_a_multi_page_section_and_foreign_pdfs():
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=letter)
    for lines in (["Cover page"], ["Roth IRA Statement"], ["continued"], ["401(k) Plan Statement"]):
        for i, line in enumerate(lines):
            c.drawString(48, 740 - 20 * i, line)
        c.showPage()
    c.save()
    got = parse_bundle(buf.getvalue())
    assert [(d.doc_kind, d.first_page, d.last_page) for d in got] == [("roth_ira", 2, 3), ("retirement_401k", 4, 4)]
    unknown = parse_bundle(b"not a pdf")
    assert [d.doc_kind for d in unknown] == ["unknown"]


# --- the household ---------------------------------------------------------------------------


def _numbers(model) -> dict:
    out = {}

    def walk(prefix, x):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(f"{prefix}.{k}", v)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(f"{prefix}[{i}]", v)
        else:
            out[prefix] = x

    walk("", model.model_dump(exclude={"snapshot", "estimated"}))
    return out


def test_the_household_built_from_the_bundle_equals_showcase(docs):
    pa = answers()
    pa.pop("income_change")
    # the customer confirms the flagged total (the document value is the right one)
    household = builder.build_household(docs, {}, Answers(**pa))
    want = _numbers(type(household).model_validate(SHOWCASE))
    got = _numbers(household)
    assert got.keys() == want.keys()
    for key, value in want.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert got[key] == pytest.approx(value, abs=0.005), key
        else:
            assert got[key] == value, key
    assert household.estimated == ["social_security"]


def test_old_three_document_flow_is_unchanged():
    old = [parse_document(REPO / "fixtures" / "sample_docs" / n) for n in generate.DOC_FILENAMES.values()]
    household = builder.build_household(old, {}, Answers())
    assert household.accounts.roth_balance == 30_000 and household.accounts.cash == 40_000
    assert household.estimated == ["roth_balance", "cash", "social_security"]
    assert household.accounts.roth_equity_share == 1.0 and len(household.people) == 2
    assert household.people[0].name == "Alex Sample"


# --- the API ---------------------------------------------------------------------------------


def test_sample_equals_upload():
    sample = client.post("/portal/documents/sample")
    assert sample.status_code == 200
    s = sample.json()
    assert s["id"] == "smith-bundle" and s["pages"] == 4 and s["size_bytes"] == PDF.stat().st_size
    assert client.post("/portal/documents/sample").json() == s
    up = client.post("/portal/documents/upload", files={"file": ("copy.pdf", PDF.read_bytes(), "application/pdf")})
    assert up.status_code == 200, up.text
    u = up.json()
    assert u["id"] != s["id"] and u["documents"] == s["documents"]
    assert [d["doc_kind"] for d in s["documents"]] == KINDS
    file = client.get(f"/portal/documents/{u['id']}/file")
    assert file.status_code == 200 and file.content == PDF.read_bytes()
    assert "inline" in file.headers["content-disposition"]
    assert client.get("/portal/documents/nope/file").status_code == 404


def test_defaults_are_john_smiths_goals():
    d = answers()
    g, ss = SHOWCASE["goals"], SHOWCASE["social_security"]
    assert d == {
        "retirement_age": g["retirement_age"], "retirement_spending": g["retirement_spending"],
        "college_starts_in_years": g["college_starts_in_years"], "college_annual_cost": g["college_annual_cost"],
        "college_years": g["college_years"], "home_purchase_in_years": g["home_purchase_in_years"],
        "home_down_payment": g["home_down_payment"], "social_security_annual": ss["annual_benefit"],
        "social_security_start_age": ss["start_age"], "charitable_giving": 0.0, "income_change": "none",
    }


def test_non_pdf_and_unknown_pdf_are_422():
    r = client.post("/portal/documents/upload", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and "not a PDF" in r.json()["detail"]
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=letter)
    c.drawString(48, 740, "Grocery list")
    c.save()
    r = client.post("/portal/documents/upload", files={"file": ("list.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 422 and "could not find" in r.json()["detail"]
    r = client.post("/portal/documents/upload", files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 422


def test_household_endpoint_matches_showcase_and_rechecks_after_overrides():
    sample = client.post("/portal/documents/sample").json()
    body = {"document_id": sample["id"], "overrides": {}, "answers": answers()}
    r = client.post("/portal/household", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["corrections"] == []
    assert sum(1 for d in out["documents"] for f in d["fields"] if f["confidence"] != "high") == 1
    assert out["household"]["accounts"]["brokerage_value"] == pytest.approx(SHOWCASE["accounts"]["brokerage_value"])

    # correcting the short holding clears the flag everywhere and leaves the household as it was
    short = {"holding_5_value": 150000.0}
    r = client.post("/portal/household", json={**body, "overrides": short})
    assert r.status_code == 200
    out = r.json()
    assert out["corrections"][0]["key"] == "holding_5_value"
    assert out["corrections"][0]["document_value"] == pytest.approx(149999.0)
    assert all(f["confidence"] == "high" for d in out["documents"] for f in d["fields"])
    assert all(c["passed"] for d in out["documents"] for c in d["checks"])
    assert out["household"]["accounts"]["brokerage_value"] == pytest.approx(SHOWCASE["accounts"]["brokerage_value"])

    # editing the stated total itself clears that field's flag (the household uses the edited value)
    r = client.post("/portal/household", json={**body, "overrides": {"brokerage_total_value": SHOWCASE["accounts"]["brokerage_value"] - 1.0}})
    out = r.json()
    total = next(f for d in out["documents"] for f in d["fields"] if f["key"] == "brokerage_total_value")
    assert total["confidence"] == "high" and total["flag"] is None
    assert out["household"]["accounts"]["brokerage_value"] == pytest.approx(SHOWCASE["accounts"]["brokerage_value"] - 1.0)


def test_household_endpoint_errors():
    sample = client.post("/portal/documents/sample").json()
    body = {"document_id": sample["id"], "overrides": {}, "answers": answers()}
    assert client.post("/portal/household", json={**body, "document_id": "nope"}).status_code == 404
    assert client.post("/portal/household", json={**body, "overrides": {"nonsense": 1}}).status_code == 422
    assert client.post("/portal/household", json={**body, "answers": {**answers(), "retirement_age": 40}}).status_code == 422
