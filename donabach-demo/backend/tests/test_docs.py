"""M2: fake documents and parser tests.

The fixture (fixtures/demo_household.json) is read here directly and the expected numbers are
rebuilt from it with the tax engine, independently of app.docs.generate, so these tests check the
generator and the parser against the fixture rather than against each other.
"""

from __future__ import annotations

import copy
import io
import json
import re
from pathlib import Path
from typing import Any

import pdfplumber
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from app.docs import generate
from app.docs.generate import DOC_FILENAMES, build_documents, generate_all
from app.docs.models import ParsedDocument, ParsedField
from app.docs.parse import apply_cross_checks, parse_document
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, compute_return

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "demo_household.json"
COMMITTED_DOCS = FIXTURE_PATH.parent / "sample_docs"
KINDS = ("form_1040", "brokerage_statement", "retirement_401k")

# The field keys that are the contract with the API and the frontend.
REQUIRED_KEYS: dict[str, list[str]] = {
    "form_1040": [
        "filing_status", "taxpayer_age", "spouse_age", "children_under_17", "child_age_1",
        "w2_wages_taxpayer", "w2_wages_spouse", "wages_1a", "taxable_interest_2b",
        "qualified_dividends_3a", "ordinary_dividends_3b", "capital_gain_7", "total_income_9",
        "adjustments_10", "agi_11", "standard_deduction_12", "taxable_income_15", "total_tax_24",
    ],
    "brokerage_statement": [
        "brokerage_total_value", "brokerage_cost_basis", "brokerage_unrealized_gain",
        *(f"holding_{i}_{part}" for i in range(1, 7) for part in ("value", "basis")),
    ],
    "retirement_401k": [
        "k401_total_balance", "k401_balance_taxpayer", "k401_balance_spouse",
        "k401_contrib_taxpayer", "k401_contrib_spouse",
        *(f"alloc_{i}_{part}" for i in range(1, 5) for part in ("value", "pct")),
    ],
}
INTEGER_KEYS = {"taxpayer_age", "spouse_age", "children_under_17", "child_age_1"}
TITLES = {
    "form_1040": "Form 1040 (2026 projection), simplified",
    "brokerage_statement": "Brokerage Account Statement",
    "retirement_401k": "401(k) Plan Statement",
}


# --- helpers --------------------------------------------------------------------------------


def expected_values(fx: dict[str, Any]) -> dict[str, dict[str, float | str]]:
    """Every value the parser must recover, rebuilt from the fixture (engine-computed 1040)."""
    tp, sp, inc = fx["taxpayer"], fx["spouse"], fx["income"]
    w2_tp, w2_sp = tp["wages"] - tp["pretax_401k"], sp["wages"] - sp["pretax_401k"]
    ret = compute_return(
        TaxInputs(
            wages=w2_tp + w2_sp,
            interest=inc["taxable_interest"],
            qualified_dividends=inc["qualified_dividends"],
            ordinary_dividends=inc["ordinary_dividends"],
            net_capital_gain=inc["net_long_term_capital_gain"],
            children_under_17=sum(1 for c in fx["children"] if c["age"] <= P.CTC_MAX_CHILD_AGE),
        )
    )
    form = {
        "filing_status": "Married filing jointly",
        "taxpayer_age": tp["age"],
        "spouse_age": sp["age"],
        "children_under_17": 1,
        "child_age_1": fx["children"][0]["age"],
        "w2_wages_taxpayer": w2_tp,
        "w2_wages_spouse": w2_sp,
        "wages_1a": round(ret.wages),
        "taxable_interest_2b": round(ret.interest),
        "qualified_dividends_3a": round(ret.qualified_dividends),
        "ordinary_dividends_3b": round(ret.ordinary_dividends),
        "capital_gain_7": round(ret.capital_gain_line),
        "total_income_9": round(ret.total_income),
        "adjustments_10": round(ret.total_income - ret.agi),
        "agi_11": round(ret.agi),
        "standard_deduction_12": round(ret.standard_deduction),
        "taxable_income_15": round(ret.taxable_income),
        "total_tax_24": round(ret.federal_total),
    }

    b, flaw = fx["brokerage"], fx["intentional_discrepancy"]
    brokerage: dict[str, float | str] = {
        "brokerage_total_value": b["total_value"],
        "brokerage_cost_basis": b["cost_basis"],
        "brokerage_unrealized_gain": b["total_value"] - b["cost_basis"],
    }
    for i, h in enumerate(b["holdings"], start=1):
        delta = flaw["printed_value_delta"] if h["ticker"] == flaw["holding_ticker"] else 0
        brokerage[f"holding_{i}_value"] = h["value"] + delta  # the one documented exception
        brokerage[f"holding_{i}_basis"] = h["basis"]

    k = fx["retirement_401k"]
    k401: dict[str, float | str] = {
        "k401_total_balance": k["total_balance"],
        "k401_balance_taxpayer": k["participants"]["taxpayer"]["balance"],
        "k401_balance_spouse": k["participants"]["spouse"]["balance"],
        "k401_contrib_taxpayer": tp["pretax_401k"],
        "k401_contrib_spouse": sp["pretax_401k"],
    }
    for i, fund in enumerate(k["allocation"], start=1):
        k401[f"alloc_{i}_value"] = fund["value"]
        k401[f"alloc_{i}_pct"] = round(fund["value"] / k["total_balance"] * 100, 1)
    return {"form_1040": form, "brokerage_statement": brokerage, "retirement_401k": k401}


def expected_meta(fx: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Row metadata by field key, from the fixture."""
    meta: dict[str, dict[str, str]] = {}
    for i, h in enumerate(fx["brokerage"]["holdings"], start=1):
        row = {"name": h["name"], "ticker": h["ticker"], "asset_class": h["asset_class"]}
        meta[f"holding_{i}_value"] = meta[f"holding_{i}_basis"] = row
    for i, fund in enumerate(fx["retirement_401k"]["allocation"], start=1):
        row = {"name": fund["name"], "asset_class": fund["asset_class"]}
        meta[f"alloc_{i}_value"] = meta[f"alloc_{i}_pct"] = row
    return meta


def expected_kind(key: str) -> str:
    if key == "filing_status":
        return "text"
    if key in INTEGER_KEYS:
        return "integer"
    return "percent" if key.endswith("_pct") else "money"


def by_key(doc: ParsedDocument) -> dict[str, ParsedField]:
    return {f.key: f for f in doc.fields}


def not_high(fields: list[ParsedField]) -> dict[str, ParsedField]:
    return {f.key: f for f in fields if f.confidence != "high"}


def reading(f: ParsedField) -> tuple:
    """What a field says, without where it sits (boxes move when a row above is removed)."""
    return (f.value, f.confidence, f.flag, f.meta)


def assert_missing(f: ParsedField) -> None:
    """A field that was not found: low confidence, no value, box or page, and a reason naming it."""
    assert (f.confidence, f.value, f.bbox, f.page) == ("low", None, None, None), f.key
    assert f.flag and f.label in f.flag, f.key


Text = tuple[float, float, str]  # x, y (from the bottom of the page), string


def make_pdf(*lines: Text, right: Text | None = None) -> bytes:
    """A tiny one-page PDF: left-aligned text lines, optionally one right-aligned string."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 9.5)
    for x, y, text in lines:
        c.drawString(x, y, text)
    if right is not None:
        c.drawRightString(right[0], right[1], right[2])
    c.showPage()
    c.save()
    return buf.getvalue()


def page_text(source: Path | bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(source) if isinstance(source, bytes) else source) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


@pytest.fixture(scope="module")
def fx() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def docs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The three PDFs freshly generated into a temp dir."""
    return generate_all(tmp_path_factory.mktemp("sample_docs"))


@pytest.fixture(scope="module")
def parsed(docs: dict[str, Path]) -> dict[str, ParsedDocument]:
    return {kind: parse_document(path) for kind, path in docs.items()}


# --- the fixture ----------------------------------------------------------------------------


def test_fixture_numbers_add_up(fx):
    b, k = fx["brokerage"], fx["retirement_401k"]
    assert (b["total_value"], b["cost_basis"]) == (150_000, 110_000)
    assert len(b["holdings"]) == 6
    assert sum(h["value"] for h in b["holdings"]) == 150_000
    assert sum(h["basis"] for h in b["holdings"]) == 110_000
    assert all(h["asset_class"] == "equity" for h in b["holdings"])
    assert k["total_balance"] == 400_000
    assert sum(p["balance"] for p in k["participants"].values()) == 400_000
    assert sum(f["value"] for f in k["allocation"]) == 400_000
    assert {f["asset_class"] for f in k["allocation"]} == {"equity", "bond"}
    generate.validate_household(fx)  # does not raise


def test_fixture_uses_only_obviously_fake_identifiers(fx):
    assert fx["taxpayer"]["ssn"] == fx["spouse"]["ssn"] == "000-00-0000"
    accounts = [
        fx["brokerage"]["account_number"],
        *(p["account"] for p in fx["retirement_401k"]["participants"].values()),
    ]
    assert all(re.fullmatch(r"XXXX-\d{4}", a) for a in accounts)
    assert "Sample" in fx["taxpayer"]["name"] and "Sample" in fx["spouse"]["name"]


def test_fixture_matches_the_brief(fx):
    assert fx["filing_status"] == "married_filing_jointly"
    assert (fx["state"], fx["tax_year"]) == ("IL", 2026)
    assert (fx["taxpayer"]["age"], fx["spouse"]["age"]) == (38, 37)
    assert (fx["taxpayer"]["wages"], fx["spouse"]["wages"]) == (140_000, 110_000)
    assert (fx["taxpayer"]["pretax_401k"], fx["spouse"]["pretax_401k"]) == (24_500, 24_500)
    assert [c["age"] for c in fx["children"]] == [8]
    income = {k: v for k, v in fx["income"].items() if not k.startswith("_")}
    assert income == {
        "taxable_interest": 800,
        "qualified_dividends": 2_700,
        "ordinary_dividends": 3_000,
        "net_long_term_capital_gain": 1_500,
    }
    n = fx["not_in_documents"]
    assert (n["roth_ira"], n["cash"]) == (30_000, 40_000)
    assert n["goals"]["home_purchase"] == {"years_from_now": 3, "down_payment": 120_000}
    assert n["goals"]["college"] == {"starts_in_years": 10, "annual_cost": 35_000, "years": 4}
    assert n["goals"]["retirement"] == {"age": 62, "annual_spending": 110_000}
    assert n["social_security"] == {"household_annual_benefit": 50_000, "start_age": 67}


def test_validate_household_rejects_numbers_that_do_not_add_up(fx):
    broken = copy.deepcopy(fx)
    broken["brokerage"]["holdings"][0]["value"] += 1
    with pytest.raises(ValueError, match="holding values"):
        generate.validate_household(broken)
    broken = copy.deepcopy(fx)
    broken["retirement_401k"]["allocation"][0]["value"] -= 1
    with pytest.raises(ValueError, match="allocation"):
        generate.validate_household(broken)


# --- generation -----------------------------------------------------------------------------


def test_generate_all_writes_three_one_page_letter_pdfs(docs):
    assert set(docs) == set(KINDS)
    assert {kind: path.name for kind, path in docs.items()} == {
        "form_1040": "form-1040-2026-projection.pdf",
        "brokerage_statement": "brokerage-statement.pdf",
        "retirement_401k": "401k-statement.pdf",
    }
    for path in docs.values():
        with pdfplumber.open(path) as pdf:
            assert [(p.width, p.height) for p in pdf.pages] == [(612.0, 792.0)]


def test_generation_is_byte_for_byte_deterministic(tmp_path):
    first = generate_all(tmp_path / "a")
    second = generate_all(tmp_path / "b")
    for kind in KINDS:
        assert first[kind].read_bytes() == second[kind].read_bytes()
    assert build_documents() == build_documents()


def test_every_page_carries_the_fictional_footer(docs):
    for kind, path in docs.items():
        pages = page_text(path)
        assert pages and all("SAMPLE – FICTIONAL" in text for text in pages), kind


def test_cli_writes_the_pdfs(tmp_path, capsys):
    assert generate.main(["--out", str(tmp_path / "cli")]) == 0
    assert sorted(p.name for p in (tmp_path / "cli").iterdir()) == sorted(DOC_FILENAMES.values())
    assert "form_1040" in capsys.readouterr().out


def test_form_1040_amounts_are_the_tax_engine_amounts(docs):
    ret = compute_return(
        TaxInputs(
            wages=201_000,
            interest=800,
            qualified_dividends=2_700,
            ordinary_dividends=3_000,
            net_capital_gain=1_500,
            children_under_17=1,
        )
    )
    assert (ret.agi, ret.taxable_income, ret.federal_total) == (206_300, 174_100, 25_232)

    # What is printed on the page, read without the parser.
    text = page_text(docs["form_1040"])[0]
    assert re.search(r"^1a Wages .* \$201,000$", text, re.M)
    assert re.search(r"^11 Adjusted gross income .* \$206,300$", text, re.M)
    assert re.search(r"^15 Taxable income .* \$174,100$", text, re.M)
    assert re.search(r"^24 Total tax \$25,232$", text, re.M)
    assert "W-2 wages, taxpayer (Alex Sample) $115,500" in text
    assert "W-2 wages, spouse (Jordan Sample) $85,500" in text

    # And the parsed lines are the engine's, line for line.
    got = {k: f.value for k, f in by_key(parse_document(docs["form_1040"])).items()}
    assert got["total_income_9"] == ret.total_income
    assert got["agi_11"] == ret.agi
    assert got["standard_deduction_12"] == ret.standard_deduction == P.STANDARD_DEDUCTION_MFJ
    assert got["taxable_income_15"] == ret.taxable_income
    assert got["total_tax_24"] == ret.federal_total


def test_the_1040_is_labelled_a_2026_projection(docs):
    text = page_text(docs["form_1040"])[0]
    assert "Form 1040 (2026 projection), simplified" in text
    assert "2025" not in text.replace("Rev. Proc. 2025-32", "")  # no 2025 form, only the cite


# --- the parser recovers every fixture value ------------------------------------------------


@pytest.fixture(scope="module", params=["generated", "committed"])
def source_docs(request, docs) -> dict[str, Path]:
    """The freshly generated PDFs, and the ones committed under fixtures/sample_docs/."""
    if request.param == "generated":
        return docs
    paths = {kind: COMMITTED_DOCS / name for kind, name in DOC_FILENAMES.items()}
    missing = [p.name for p in paths.values() if not p.exists()]
    assert not missing, f"missing {missing} in {COMMITTED_DOCS}: run `make docs`"
    return paths


@pytest.mark.parametrize("kind", KINDS)
def test_parser_recovers_every_fixture_value(fx, source_docs, kind):
    doc = parse_document(source_docs[kind])
    assert doc.doc_kind == kind
    assert doc.title == TITLES[kind]
    keys = [f.key for f in doc.fields]
    assert len(keys) == len(set(keys)), "field keys must be unique"
    expected = expected_values(fx)[kind]
    assert set(expected) == set(REQUIRED_KEYS[kind]) <= set(keys)
    got = by_key(doc)
    for key, want in expected.items():
        assert got[key].value == want, key
        assert got[key].kind == expected_kind(key), key
        assert got[key].page == 1 and got[key].bbox is not None, key
    for key, meta in expected_meta(fx).items():
        if key in got:
            assert got[key].meta == meta, key


@pytest.mark.parametrize("kind", KINDS)
def test_committed_sample_docs_are_up_to_date(docs, kind):
    # Compared by what a reader sees (all page text) and what the parser reads (values, flags,
    # boxes), not by bytes, so a newer reportlab does not trip it; a change to the generator or
    # the fixture does.
    committed = COMMITTED_DOCS / DOC_FILENAMES[kind]
    assert committed.exists(), f"{committed} is missing: run `make docs`"
    assert page_text(committed) == page_text(docs[kind]), "stale PDF: run `make docs`"
    assert parse_document(committed) == parse_document(docs[kind]), "stale PDF: run `make docs`"


def test_the_one_documented_exception_is_the_planted_discrepancy(fx, parsed):
    flaw = fx["intentional_discrepancy"]
    got = by_key(parsed["brokerage_statement"])
    off = [
        (h["ticker"], got[f"holding_{i}_value"].value - h["value"])
        for i, h in enumerate(fx["brokerage"]["holdings"], start=1)
        if got[f"holding_{i}_value"].value != h["value"]
    ]
    assert off == [(flaw["holding_ticker"], flaw["printed_value_delta"])] == [("SDIN", -1)]
    assert sum(got[f"holding_{i}_value"].value for i in range(1, 7)) == 149_999
    assert got["brokerage_total_value"].value == 150_000


def test_field_labels_groups_and_kinds_are_filled_in(parsed):
    for doc in parsed.values():
        for f in doc.fields:
            assert f.label and f.group and f.kind in ("money", "integer", "percent", "text")
            assert f.label[0].isupper(), f.label  # sentence case


def test_parsed_document_round_trips_through_json(parsed):
    for doc in parsed.values():
        assert ParsedDocument.model_validate_json(doc.model_dump_json()) == doc


# --- confidence and cross-checks ------------------------------------------------------------


def test_exactly_one_field_is_flagged_and_it_is_the_brokerage_total(fx, parsed):
    flaw = fx["intentional_discrepancy"]
    flagged = {kind: not_high(doc.fields) for kind, doc in parsed.items()}
    assert flagged["form_1040"] == {} and flagged["retirement_401k"] == {}
    assert list(flagged["brokerage_statement"]) == ["brokerage_total_value"]
    assert flaw["flagged_field"] == "brokerage_total_value"

    field = flagged["brokerage_statement"]["brokerage_total_value"]
    assert field.confidence == flaw["expected_confidence"] == "medium"
    assert field.value == 150_000 and field.bbox is not None  # still read, just not trusted
    assert field.flag == (
        "Holdings add up to $149,999 but the statement total is $150,000 (difference $1)."
    )
    # Every other field in every document, including all six holding rows, is high with no flag.
    for doc in parsed.values():
        for f in doc.fields:
            if f.key != "brokerage_total_value":
                assert (f.confidence, f.flag) == ("high", None), f.key


def test_every_cross_check_passes_except_the_planted_one(parsed):
    results = {kind: {c.name: c for c in doc.checks} for kind, doc in parsed.items()}
    assert {kind: len(r) for kind, r in results.items()} == {
        "form_1040": 4,
        "brokerage_statement": 3,
        "retirement_401k": 3,
    }
    failed = [(k, c) for k, checks in results.items() for c in checks.values() if not c.passed]
    assert len(failed) == 1
    kind, check = failed[0]
    assert kind == "brokerage_statement"
    assert check.name == "Holdings add up to the statement total"
    assert "brokerage_total_value" in check.keys and "holding_4_value" in check.keys
    assert "$149,999" in check.detail and "$150,000" in check.detail
    assert all(c.detail and c.keys for checks in results.values() for c in checks.values())
    # The checks the brief lists are all there.
    assert set(results["form_1040"]) >= {
        "Total income equals lines 1a, 2b, 3b and 7",
        "AGI equals total income minus adjustments",
        "Taxable income equals AGI minus the standard deduction",
    }
    assert set(results["retirement_401k"]) == {
        "Participant balances add up to the total balance",
        "Fund allocation adds up to the total balance",
        "Allocation percentages add up to 100%",
    }


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        ("form_1040", "agi_11"),
        ("form_1040", "taxpayer_age"),
        ("brokerage_statement", "brokerage_cost_basis"),
        ("retirement_401k", "k401_total_balance"),
    ],
)
def test_a_removed_line_is_low_confidence_with_no_value(kind, key, parsed):
    doc = parse_document(build_documents(omit={key})[kind])
    field = by_key(doc)[key]
    assert_missing(field)
    # Nothing else changes: every other field reads exactly as before.
    reference = by_key(parsed[kind])
    assert {k: reading(f) for k, f in by_key(doc).items() if k != key} == {
        k: reading(f) for k, f in reference.items() if k != key
    }
    # A check that needed the missing line cannot run: it is reported, not silently dropped.
    assert len(doc.checks) == len(parsed[kind].checks)
    for check in doc.checks:
        if key in check.keys:
            assert not check.passed and check.detail.startswith("Not checked")
            assert field.label in check.detail


@pytest.mark.parametrize(
    ("kind", "key", "sibling"),
    [
        ("brokerage_statement", "holding_2_basis", "holding_2_value"),
        ("brokerage_statement", "holding_5_value", "holding_5_basis"),
        ("retirement_401k", "k401_contrib_spouse", "k401_balance_spouse"),
        ("retirement_401k", "alloc_3_pct", "alloc_3_value"),
    ],
)
def test_a_blank_table_cell_is_low_but_the_rest_of_its_row_is_read(kind, key, sibling, parsed):
    got = by_key(parse_document(build_documents(omit={key})[kind]))
    reference = by_key(parsed[kind])
    assert_missing(got[key])
    assert got[key].meta == reference[key].meta  # the row's identity is still known
    assert reading(got[sibling]) == reading(reference[sibling])  # and so is its other cell


@pytest.mark.parametrize("kind", KINDS)
def test_a_blank_document_of_the_right_kind_is_all_low(kind):
    doc = parse_document(make_pdf((48, 740, TITLES[kind])))
    assert doc.doc_kind == kind and doc.title == TITLES[kind]
    keys = {f.key for f in doc.fields}
    # Row-based fields are reported once (holding_1_*, alloc_1_*) as a placeholder.
    assert {k for k in REQUIRED_KEYS[kind] if not re.search(r"_[2-9]_", k)} <= keys
    for f in doc.fields:
        assert_missing(f)
    assert doc.checks
    assert all(not c.passed and c.detail.startswith("Not checked") for c in doc.checks)


def test_a_label_with_no_value_next_to_it_is_low_confidence():
    pdf = make_pdf(
        (48, 740, TITLES["form_1040"]),
        (56, 600, "11 Adjusted gross income (subtract line 10 from line 9)"),
    )
    agi = by_key(parse_document(pdf))["agi_11"]
    assert_missing(agi)
    assert "could not read a value" in agi.flag


def test_losses_in_parentheses_are_read_as_negative_amounts():
    pdf = make_pdf(
        (48, 740, TITLES["form_1040"]),
        (56, 600, "7 Capital gain or (loss)"),
        right=(556, 600, "($1,200)"),
    )
    gain = by_key(parse_document(pdf))["capital_gain_7"]
    assert (gain.value, gain.confidence) == (-1_200.0, "high")


def _rechecked(parsed, kind: str, key: str, delta: float) -> dict[str, ParsedField]:
    """Shift one parsed value, re-run the checks, and return the fields that are not high."""
    fields = [f.model_copy(deep=True) for f in parsed[kind].fields]
    next(f for f in fields if f.key == key).value += delta
    apply_cross_checks(kind, fields)
    return not_high(fields)


@pytest.mark.parametrize(
    ("kind", "shifted", "delta", "flagged", "sentences"),
    [
        # a total or derived line that does not match its parts is the one field flagged
        ("form_1040", "ordinary_dividends_3b", 10, "total_income_9",
         ("$206,310", "$206,300", "difference $10")),
        ("form_1040", "adjustments_10", 25, "agi_11",
         ("$206,275", "$206,300", "difference $25")),
        ("form_1040", "standard_deduction_12", -200, "taxable_income_15",
         ("$174,300", "$174,100", "difference $200")),
        ("form_1040", "w2_wages_spouse", 1, "wages_1a",
         ("$201,001", "$201,000", "difference $1")),
        ("brokerage_statement", "holding_2_basis", 5, "brokerage_cost_basis",
         ("$110,005", "$110,000", "difference $5")),
        ("brokerage_statement", "brokerage_unrealized_gain", 7, "brokerage_unrealized_gain",
         ("$40,000", "$40,007", "difference $7")),
        ("retirement_401k", "k401_balance_spouse", 1_000, "k401_total_balance",
         ("$401,000", "$400,000", "difference $1,000")),
        ("retirement_401k", "alloc_2_value", -500, "k401_total_balance",
         ("$399,500", "$400,000", "difference $500")),
    ],
)
def test_a_failed_check_flags_only_its_total_or_derived_line(
    parsed, kind, shifted, delta, flagged, sentences
):
    bad = _rechecked(parsed, kind, shifted, delta)
    # (the brokerage sample already carries its planted flag on the total value)
    planted = {"brokerage_total_value"} if kind == "brokerage_statement" else set()
    assert set(bad) == {flagged} | planted  # the rows that fed the sum stay high
    assert all(f.confidence == "medium" for f in bad.values())
    assert all(s in bad[flagged].flag for s in sentences), bad[flagged].flag


def test_percentages_that_do_not_add_up_flag_every_percentage(parsed):
    bad = _rechecked(parsed, "retirement_401k", "alloc_4_pct", -3.0)
    assert set(bad) == {f"alloc_{i}_pct" for i in range(1, 5)}  # there is no stated total to blame
    assert "97.0%" in bad["alloc_1_pct"].flag and "not 100%" in bad["alloc_1_pct"].flag
    # A rounding wobble of at most 0.05 per row is not a failure.
    assert _rechecked(parsed, "retirement_401k", "alloc_4_pct", 0.15) == {}


def test_taxable_income_is_floored_at_zero(parsed):
    fields = [f.model_copy(deep=True) for f in parsed["form_1040"].fields]
    low_income = {
        "w2_wages_taxpayer": 10_000, "w2_wages_spouse": 0, "wages_1a": 10_000,
        "taxable_interest_2b": 0, "ordinary_dividends_3b": 0, "capital_gain_7": 0,
        "total_income_9": 10_000, "agi_11": 10_000, "taxable_income_15": 0,
    }
    for f in fields:
        if f.key in low_income:
            f.value = low_income[f.key]
    checks = apply_cross_checks("form_1040", fields)
    assert all(c.passed for c in checks) and not not_high(fields)


def test_apply_cross_checks_can_be_rerun_after_a_correction(parsed):
    fields = [f.model_copy(deep=True) for f in parsed["brokerage_statement"].fields]
    assert set(not_high(fields)) == {"brokerage_total_value"}
    # The user fixes the holding that is $1 off: every check passes and nothing is flagged.
    next(f for f in fields if f.key == "holding_4_value").value += 1
    checks = apply_cross_checks("brokerage_statement", fields)
    assert all(c.passed for c in checks)
    assert all((f.confidence, f.flag) == ("high", None) for f in fields)


# --- source boxes ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_every_bbox_sits_on_its_value(docs, parsed, kind):
    doc = parsed[kind]
    with pdfplumber.open(docs[kind]) as pdf:
        for f in doc.fields:
            b = f.bbox
            assert b is not None and f.page is not None, f.key
            width, height = doc.page_sizes[f.page - 1]
            assert 0 <= b.x0 < b.x1 <= width and 0 <= b.top < b.bottom <= height, f.key
            box = pdf.pages[f.page - 1].within_bbox((b.x0, b.top, b.x1, b.bottom))
            text = box.extract_text() or ""
            if f.kind == "text":
                assert text.strip() == f.value, f.key
            else:
                digits = re.sub(r"\D", "", text)
                if f.kind == "percent":
                    want = f"{f.value:.1f}".replace(".", "")  # 45.0 -> "450", as printed "45.0%"
                else:
                    want = str(int(abs(f.value)))
                assert digits == want, (f.key, text)


# --- input handling -------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_parsing_bytes_equals_parsing_the_path(docs, kind):
    assert parse_document(docs[kind].read_bytes()) == parse_document(docs[kind])


def test_an_unrelated_pdf_is_unknown_and_does_not_raise():
    pdf = make_pdf(
        (72, 700, "Quarterly gardening newsletter"), (72, 680, "11 Adjusted gross income $5")
    )
    doc = parse_document(pdf)
    assert doc.doc_kind == "unknown" and doc.title == "Quarterly gardening newsletter"
    assert doc.fields == [] and doc.checks == []
    assert doc.page_sizes == [(612.0, 792.0)]


def test_a_blank_pdf_is_unknown():
    doc = parse_document(make_pdf())
    assert (doc.doc_kind, doc.fields, doc.checks) == ("unknown", [], [])


@pytest.mark.parametrize("data", [b"", b"this is not a pdf", b"%PDF-1.4\ntruncated"])
def test_unreadable_input_is_unknown_and_does_not_raise(data):
    doc = parse_document(data)
    assert (doc.doc_kind, doc.fields, doc.checks, doc.page_sizes) == ("unknown", [], [], [])


def test_the_omit_hook_rejects_unknown_keys():
    with pytest.raises(ValueError, match="no_such_field"):
        build_documents(omit={"no_such_field"})
