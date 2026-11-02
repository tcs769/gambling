"""Generate the three fictional sample PDFs from fixtures/demo_household.json.

These are the documents the demo "uploads"; parse.py reads them back. Every amount comes from
the fixture, and every 1040 amount is computed by the tax engine, so nothing is typed in by
hand. Output is byte-for-byte reproducible: fixed PDF dates and IDs, uncompressed streams, and
the standard Helvetica fonts (no embedded font subsets).

    python -m app.docs.generate [--out DIR]        (or `make docs`)

One deliberate flaw: the brokerage statement prints one holding $1 below its true value (see
"intentional_discrepancy" in the fixture), so the holdings add up to $149,999 against a stated
total of $150,000. Everything else in the three documents is consistent.
"""

from __future__ import annotations

import argparse
import io
import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, compute_return

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "fixtures" / "demo_household.json"
DEFAULT_OUT_DIR = REPO_ROOT / "fixtures" / "sample_docs"

# Document kind -> file name. The kinds match the parser's `doc_kind` values.
DOC_FILENAMES: dict[str, str] = {
    "form_1040": "form-1040-2026-projection.pdf",
    "brokerage_statement": "brokerage-statement.pdf",
    "retirement_401k": "401k-statement.pdf",
}
TITLES: dict[str, str] = {
    "form_1040": "Form 1040 (2026 projection), simplified",
    "brokerage_statement": "Brokerage Account Statement",
    "retirement_401k": "401(k) Plan Statement",
}
FOOTER_TEXT = "SAMPLE – FICTIONAL"
FOOTER_NOTE = "Fictional document created for the Waramoug demo. Not a real form, statement or account."
FILING_STATUS_LABELS = {"married_filing_jointly": "Married filing jointly"}

# Form 1040 lines shown, as (field key, line number, description). Lines in BOLD_LINES are totals.
FORM_1040_LINES: tuple[tuple[str, str, str], ...] = (
    ("wages_1a", "1a", "Wages from Form(s) W-2, box 1"),
    ("taxable_interest_2b", "2b", "Taxable interest"),
    ("qualified_dividends_3a", "3a", "Qualified dividends"),
    ("ordinary_dividends_3b", "3b", "Ordinary dividends (includes qualified dividends)"),
    ("capital_gain_7", "7", "Capital gain or (loss)"),
    ("total_income_9", "9", "Total income (add lines 1a, 2b, 3b and 7)"),
    ("adjustments_10", "10", "Adjustments to income"),
    ("agi_11", "11", "Adjusted gross income (subtract line 10 from line 9)"),
    ("standard_deduction_12", "12", "Standard deduction"),
    ("taxable_income_15", "15", "Taxable income (subtract line 12 from line 11)"),
    ("total_tax_24", "24", "Total tax"),
)
BOLD_LINES = frozenset({"9", "11", "15", "24"})

# --- Page geometry (US Letter, points) ----------------------------------------------------------
PAGE_W, PAGE_H = letter
LEFT, RIGHT = 48.0, 564.0  # outer margins: rules and boxes
IN_L, IN_R = 56.0, 556.0  # text inset inside boxes; amounts are right-aligned at IN_R
REG, BOLD = "Helvetica", "Helvetica-Bold"
ROW_H = 14.0  # rows inside a box
TABLE_ROW_H = 20.0  # rows of a table


# =============================================================================================
# Fixture
# =============================================================================================


def load_household(path: Path | None = None) -> dict[str, Any]:
    """Read the demo household fixture and check that its numbers add up."""
    household = json.loads((path or FIXTURE_PATH).read_text(encoding="utf-8"))
    validate_household(household)
    return household


def validate_household(h: Mapping[str, Any]) -> None:
    """Raise ValueError unless the fixture is internally consistent.

    The documents must agree with each other, so the fixture's own totals have to add up. The
    one planted flaw is applied later, when the brokerage statement is drawn.
    """
    b, k = h["brokerage"], h["retirement_401k"]
    holdings, allocation = b["holdings"], k["allocation"]
    problems: list[str] = []

    def require(ok: bool, message: str) -> None:
        if not ok:
            problems.append(message)

    require(sum(x["value"] for x in holdings) == b["total_value"], "holding values != total_value")
    require(sum(x["basis"] for x in holdings) == b["cost_basis"], "holding basis != cost_basis")
    require(len({x["ticker"] for x in holdings}) == len(holdings), "duplicate tickers")
    require(
        sum(p["balance"] for p in k["participants"].values()) == k["total_balance"],
        "participant balances != total_balance",
    )
    require(
        sum(x["value"] for x in allocation) == k["total_balance"],
        "allocation values != total_balance",
    )
    require(
        all(x["asset_class"] in ("equity", "bond") for x in (*holdings, *allocation)),
        "asset_class must be 'equity' or 'bond'",
    )
    require(h["filing_status"] in FILING_STATUS_LABELS, "unsupported filing_status")
    require(h["tax_year"] == P.TAX_YEAR, "tax_year must be the year of the tax engine's parameters")
    flaw = h["intentional_discrepancy"]
    require(flaw["printed_value_delta"] != 0, "the planted discrepancy must be non-zero")
    require(
        flaw["holding_ticker"] in {x["ticker"] for x in holdings},
        "the discrepancy ticker is not a holding",
    )
    if problems:
        raise ValueError("inconsistent demo household: " + "; ".join(problems))


def children_under_17(h: Mapping[str, Any]) -> int:
    """Children who count for the child tax credit (a child is under 17 through age 16)."""
    return sum(1 for child in h["children"] if child["age"] <= P.CTC_MAX_CHILD_AGE)


def form_1040_values(h: Mapping[str, Any]) -> dict[str, float]:
    """Every dollar amount on the 1040 page, computed by the tax engine from the fixture.

    Keyed by the parser's field keys. W-2 box 1 wages are gross wages less the pre-tax 401(k)
    deferral; "total_tax_24" is the engine's federal total (after the child tax credit).
    """
    tp, sp, inc = h["taxpayer"], h["spouse"], h["income"]
    w2 = {
        "w2_wages_taxpayer": tp["wages"] - tp["pretax_401k"],
        "w2_wages_spouse": sp["wages"] - sp["pretax_401k"],
    }
    r = compute_return(
        TaxInputs(
            wages=sum(w2.values()),
            interest=inc["taxable_interest"],
            qualified_dividends=inc["qualified_dividends"],
            ordinary_dividends=inc["ordinary_dividends"],
            net_capital_gain=inc["net_long_term_capital_gain"],
            children_under_17=children_under_17(h),
        )
    )
    return {
        **w2,
        "wages_1a": r.wages,
        "taxable_interest_2b": r.interest,
        "qualified_dividends_3a": r.qualified_dividends,
        "ordinary_dividends_3b": r.ordinary_dividends,
        "capital_gain_7": r.capital_gain_line,
        "total_income_9": r.total_income,
        "adjustments_10": r.total_income - r.agi,  # the engine models no above-the-line items
        "agi_11": r.agi,
        "standard_deduction_12": r.standard_deduction,
        "taxable_income_15": r.taxable_income,
        "total_tax_24": r.federal_total,
    }


def allocation_percent(value: float, total: float) -> float:
    """Share of the 401(k) in one fund, as printed (one decimal)."""
    return round(value / total * 100, 1)


# =============================================================================================
# Drawing helpers
# =============================================================================================


def _usd(amount: float) -> str:
    """Whole dollars as printed on the documents (cents only when the amount has them); losses in parentheses."""
    if abs(amount - round(amount)) < 0.005:
        whole = round(amount)
        return f"${whole:,}" if whole >= 0 else f"(${-whole:,})"
    return f"${amount:,.2f}" if amount >= 0 else f"(${-amount:,.2f})"


class _Omit:
    """Field keys to leave out of the PDFs (a test hook), tracking which keys were ever asked for.

    A one-line field disappears completely (label and value); a table cell is left blank.
    """

    def __init__(self, keys: Iterable[str]) -> None:
        self.keys = frozenset(keys)
        self.seen: set[str] = set()

    def __call__(self, key: str) -> bool:
        self.seen.add(key)
        return key in self.keys


class _Sheet:
    """Drawing helpers over a reportlab canvas. `y` is a text baseline measured down the page."""

    def __init__(self, canvas: Canvas) -> None:
        self.c = canvas

    def text(
        self,
        x: float,
        y: float,
        s: str,
        *,
        size: float = 9.5,
        bold: bool = False,
        align: Align = "left",
        gray: float = 0.0,
    ) -> None:
        c = self.c
        c.setFont(BOLD if bold else REG, size)
        c.setFillGray(gray)
        draw = {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}
        draw[align](x, PAGE_H - y, s)

    def rule(self, y: float, *, gray: float = 0.75, width: float = 0.5) -> None:
        self.c.setStrokeGray(gray)
        self.c.setLineWidth(width)
        self.c.line(LEFT, PAGE_H - y, RIGHT, PAGE_H - y)

    def box(self, top: float, bottom: float) -> None:
        self.c.setStrokeGray(0.55)
        self.c.setLineWidth(0.8)
        self.c.rect(LEFT, PAGE_H - bottom, RIGHT - LEFT, bottom - top, stroke=1, fill=0)

    def band(self, top: float, bottom: float, gray: float = 0.92) -> None:
        self.c.setFillGray(gray)
        self.c.rect(LEFT, PAGE_H - bottom, RIGHT - LEFT, bottom - top, stroke=0, fill=1)


Row = tuple[str, str, str]  # (field key, label, printed value)
Align = Literal["left", "right", "center"]


def _header(s: _Sheet, title: str, subtitle: str) -> None:
    s.text(LEFT, 54, title, size=17, bold=True)
    s.text(LEFT, 70, subtitle, size=8.5, gray=0.4)
    s.rule(78, gray=0.2, width=1.2)


def _footer(s: _Sheet) -> None:
    s.rule(PAGE_H - 47)
    s.text(
        PAGE_W / 2,
        PAGE_H - 36,
        FOOTER_NOTE,
        size=7,
        gray=0.45,
        align="center",
    )
    s.text(PAGE_W / 2, PAGE_H - 25, FOOTER_TEXT, size=7.5, bold=True, gray=0.35, align="center")


def _info_lines(s: _Sheet, y: float, lines: Sequence[tuple[str, str]]) -> float:
    """Gray label, value to its right (label and value are one row; the label is the anchor)."""
    for label, value in lines:
        s.text(LEFT, y, label, size=8.5, gray=0.4)
        s.text(130, y, value)
        y += ROW_H
    return y


def _boxed_rows(
    s: _Sheet, top: float, heading: str, rows: Sequence[Row], *, bold: Collection[str] = ()
) -> float:
    """A titled box of label / right-aligned value rows. Returns the y below the box and a gap."""
    bottom = top + 24 + ROW_H * len(rows)
    s.box(top, bottom)
    s.text(IN_L, top + 15, heading, size=10, bold=True)
    y = top + 33
    for key, label, value in rows:
        s.text(IN_L, y, label)
        s.text(IN_R, y, value, align="right", bold=key in bold)
        y += ROW_H
    return bottom + 16


def _table_header(s: _Sheet, y: float, columns: Sequence[tuple[str, float, Align]]) -> float:
    """Shaded header row of (text, x, alignment) cells. Returns the first body row's baseline."""
    s.band(y - 13, y + 6)
    for text, x, align in columns:
        s.text(x, y, text, size=8.5, bold=True, align=align)
    return y + TABLE_ROW_H


# =============================================================================================
# The three documents
# =============================================================================================


def _draw_form_1040(s: _Sheet, h: Mapping[str, Any], omit: _Omit) -> None:
    v = form_1040_values(h)
    tp, sp = h["taxpayer"], h["spouse"]
    _header(
        s,
        TITLES["form_1040"],
        "U.S. Individual Income Tax Return  |  Tax year 2026 projection  |  For illustration only",
    )

    y = _info_lines(
        s,
        100,
        [
            ("Taxpayer", f"{tp['name']}      SSN {tp['ssn']}"),
            ("Spouse", f"{sp['name']}      SSN {sp['ssn']}"),
            ("Address", f"{h['address']} (fictional)"),
        ],
    )
    y += 8
    if not omit("filing_status"):
        s.text(LEFT, y, "Filing status", bold=True)
        s.text(130, y, FILING_STATUS_LABELS[h["filing_status"]])
    y += 22

    household: list[Row] = [
        ("taxpayer_age", "Taxpayer age", str(tp["age"])),
        ("spouse_age", "Spouse age", str(sp["age"])),
        ("children_under_17", "Qualifying children under 17", str(children_under_17(h))),
        *(
            (f"child_age_{i}", f"Child {i} age", str(child["age"]))
            for i, child in enumerate(h["children"], start=1)
        ),
    ]
    y = _boxed_rows(s, y, "Household", [r for r in household if not omit(r[0])])

    w2: list[Row] = [
        ("w2_wages_taxpayer", f"W-2 wages, taxpayer ({tp['name']})", _usd(v["w2_wages_taxpayer"])),
        ("w2_wages_spouse", f"W-2 wages, spouse ({sp['name']})", _usd(v["w2_wages_spouse"])),
    ]
    y = _boxed_rows(
        s, y, "Wages by W-2 (box 1, after 401(k) deferrals)", [r for r in w2 if not omit(r[0])]
    )

    y = _table_header(
        s, y + 8, [("Line", IN_L, "left"), ("Description", 92, "left"), ("Amount", IN_R, "right")]
    )
    for key, line_no, description in FORM_1040_LINES:
        if omit(key):
            continue
        bold = line_no in BOLD_LINES
        s.text(IN_L, y, line_no, bold=bold)
        s.text(92, y, description, bold=bold)
        s.text(IN_R, y, _usd(v[key]), bold=bold, align="right")
        s.rule(y + 6, gray=0.85)
        y += TABLE_ROW_H

    for note in (
        "Simplified layout: only the lines used by this demo are shown. Federal income tax only",
        "(no payroll taxes, itemized deductions or AMT), computed from the 2026 parameters",
        "(IRS Rev. Proc. 2025-32). Total tax (line 24) is after the child tax credit.",
    ):
        y += 10
        s.text(LEFT, y, note, size=7.5, gray=0.4)


def _draw_brokerage(s: _Sheet, h: Mapping[str, Any], omit: _Omit) -> None:
    b, tp, sp = h["brokerage"], h["taxpayer"], h["spouse"]
    flaw = h["intentional_discrepancy"]
    _header(
        s,
        TITLES["brokerage_statement"],
        f"{b['custodian']}  |  Statement period: {b['statement_period']}",
    )
    y = _info_lines(
        s,
        100,
        [
            ("Account holders", f"{tp['name']} and {sp['name']}"),
            ("Account", f"{b['account_type']}  {b['account_number']}"),
        ],
    )

    summary: list[Row] = [
        ("brokerage_total_value", "Total account value", _usd(b["total_value"])),
        ("brokerage_cost_basis", "Total cost basis", _usd(b["cost_basis"])),
        ("brokerage_unrealized_gain", "Unrealized gain", _usd(b["total_value"] - b["cost_basis"])),
    ]
    y = _boxed_rows(
        s,
        y + 12,
        "Account summary",
        [r for r in summary if not omit(r[0])],
        bold={"brokerage_total_value"},
    )

    s.text(LEFT, y + 4, "Holdings", size=11, bold=True)
    y = _table_header(
        s,
        y + 26,
        [
            ("Fund", IN_L, "left"),
            ("Ticker", 270, "left"),
            ("Asset class", 330, "left"),
            ("Value", 470, "right"),
            ("Cost basis", IN_R, "right"),
        ],
    )
    for i, holding in enumerate(b["holdings"], start=1):
        value = holding["value"]
        if holding["ticker"] == flaw["holding_ticker"]:
            value += flaw["printed_value_delta"]  # the deliberate $1 rounding difference
        s.text(IN_L, y, holding["name"], size=9)
        s.text(270, y, holding["ticker"], size=9)
        s.text(330, y, holding["asset_class"].capitalize(), size=9)
        if not omit(f"holding_{i}_value"):
            s.text(470, y, _usd(value), size=9, align="right")
        if not omit(f"holding_{i}_basis"):
            s.text(IN_R, y, _usd(holding["basis"]), size=9, align="right")
        s.rule(y + 6, gray=0.85)
        y += TABLE_ROW_H
    # The printed Total row shows the stated totals, as a statement computed from unrounded
    # figures would; it is the rows above that carry the rounding difference.
    s.rule(y - 14, gray=0.4, width=0.8)
    s.text(IN_L, y, "Total", size=9, bold=True)
    s.text(470, y, _usd(b["total_value"]), size=9, bold=True, align="right")
    s.text(IN_R, y, _usd(b["cost_basis"]), size=9, bold=True, align="right")
    s.text(
        LEFT,
        y + 34,
        "Index fund holdings are not FDIC insured and may lose value. Values as of statement date.",
        size=7.5,
        gray=0.4,
    )


def _draw_401k(s: _Sheet, h: Mapping[str, Any], omit: _Omit) -> None:
    k, tp, sp = h["retirement_401k"], h["taxpayer"], h["spouse"]
    parts = k["participants"]
    _header(
        s,
        TITLES["retirement_401k"],
        f"{k['plan_name']}  |  Recordkeeper: {k['recordkeeper']}",
    )
    people = ", ".join(
        f"{person['name']} ({parts[role]['account']})"
        for role, person in (("taxpayer", tp), ("spouse", sp))
    )
    y = _info_lines(
        s,
        100,
        [
            ("Plan year", f"{k['plan_year']} summary  (balances as of {k['balances_as_of']})"),
            ("Participants", people),
        ],
    )

    s.text(LEFT, y + 18, "Participant summary", size=11, bold=True)
    y = _table_header(
        s,
        y + 40,
        [
            ("Participant", IN_L, "left"),
            ("Balance", 330, "right"),
            (f"Contributions, plan year {k['plan_year']}", IN_R, "right"),
        ],
    )
    for role, person in (("taxpayer", tp), ("spouse", sp)):
        s.text(IN_L, y, f"{person['name']} ({role})", size=9)
        if not omit(f"k401_balance_{role}"):
            s.text(330, y, _usd(parts[role]["balance"]), size=9, align="right")
        if not omit(f"k401_contrib_{role}"):  # contributions are the 401(k) deferrals on the W-2
            s.text(IN_R, y, _usd(person["pretax_401k"]), size=9, align="right")
        s.rule(y + 6, gray=0.85)
        y += TABLE_ROW_H
    if not omit("k401_total_balance"):
        s.rule(y - 14, gray=0.4, width=0.8)
        s.text(IN_L, y, "Total balance", size=9, bold=True)
        s.text(330, y, _usd(k["total_balance"]), size=9, bold=True, align="right")
        y += TABLE_ROW_H

    s.text(LEFT, y + 18, "Combined fund allocation", size=11, bold=True)
    y = _table_header(
        s,
        y + 40,
        [
            ("Fund", IN_L, "left"),
            ("Asset class", 300, "left"),
            ("Value", 440, "right"),
            ("% of total", IN_R, "right"),
        ],
    )
    for i, fund in enumerate(k["allocation"], start=1):
        s.text(IN_L, y, fund["name"], size=9)
        s.text(300, y, fund["asset_class"].capitalize(), size=9)
        if not omit(f"alloc_{i}_value"):
            s.text(440, y, _usd(fund["value"]), size=9, align="right")
        if not omit(f"alloc_{i}_pct"):
            pct = allocation_percent(fund["value"], k["total_balance"])
            s.text(IN_R, y, f"{pct:.1f}%", size=9, align="right")
        s.rule(y + 6, gray=0.85)
        y += TABLE_ROW_H
    s.text(
        LEFT,
        y + 12,
        "Contributions are employee pre-tax deferrals. Fund values are as of the balance date.",
        size=7.5,
        gray=0.4,
    )


_DRAWERS = {
    "form_1040": _draw_form_1040,
    "brokerage_statement": _draw_brokerage,
    "retirement_401k": _draw_401k,
}


# =============================================================================================
# Public API
# =============================================================================================


def build_documents(
    household: Mapping[str, Any] | None = None, *, omit: Collection[str] = ()
) -> dict[str, bytes]:
    """Render the three PDFs in memory, keyed by document kind.

    `household` defaults to the fixture. `omit` lists parser field keys to leave out of the
    pages (a one-line field loses its label and value, a table cell goes blank); it exists so
    tests can build documents with missing data, and unknown keys raise ValueError.
    """
    if household is None:
        household = load_household()
    else:
        validate_household(household)
    skip = _Omit(omit)
    out: dict[str, bytes] = {}
    for kind, draw in _DRAWERS.items():
        buf = io.BytesIO()
        canvas = Canvas(buf, pagesize=letter, invariant=1, pageCompression=0)
        canvas.setTitle(TITLES[kind])
        canvas.setAuthor("Waramoug demo (fictional sample)")
        canvas.setSubject("Fictional sample document for the Waramoug demo")
        sheet = _Sheet(canvas)
        draw(sheet, household, skip)
        _footer(sheet)
        canvas.showPage()
        canvas.save()
        out[kind] = buf.getvalue()
    unknown = skip.keys - skip.seen
    if unknown:
        raise ValueError(f"unknown field keys in omit: {sorted(unknown)}")
    return out


def generate_all(out_dir: Path | None = None) -> dict[str, Path]:
    """Write the three PDFs (default: fixtures/sample_docs/) and return their paths by kind."""
    target = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for kind, data in build_documents().items():
        paths[kind] = target / DOC_FILENAMES[kind]
        paths[kind].write_bytes(data)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.docs.generate", description="Generate the fictional sample PDFs."
    )
    parser.add_argument(
        "--out", type=Path, default=None, help=f"output directory (default: {DEFAULT_OUT_DIR})"
    )
    args = parser.parse_args(argv)
    for kind, path in generate_all(args.out).items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
