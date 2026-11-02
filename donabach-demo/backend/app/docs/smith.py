"""Generate fixtures/smith_documents.pdf: John Smith's four fictional documents in one PDF.

Every number comes from fixtures/showcase.json (the Smith household) or, for the 1040, from the
tax engine exactly as `generate.form_1040_values` does. One page per document, in this order:
Form 1040 (2026 projection), brokerage statement, 401(k) statement, Roth IRA statement.

One deliberate flaw, as in the three older samples: the brokerage statement prints one holding
$1.00 below its true value, so the holdings add up to $1.00 less than the stated total and the
parser asks the customer to confirm that total. Everything else passes every cross-check.
Output is byte-for-byte reproducible.

    python -m app.docs.smith [--out PATH]
"""

from __future__ import annotations

import argparse
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from app.docs import generate as g
from app.docs.generate import (
    IN_L,
    IN_R,
    LEFT,
    _boxed_rows,
    _footer,
    _header,
    _info_lines,
    _Sheet,
    _table_header,
    _usd,
)

SHOWCASE_PATH = g.REPO_ROOT / "fixtures" / "showcase.json"
DEFAULT_OUT = g.REPO_ROOT / "fixtures" / "smith_documents.pdf"
NAME = "John Smith"
SSN = "000-00-0000"
ADDRESS = "123 Sample Lane, Anytown, IL 00000"
BROKERAGE_ACCOUNT = "XXXX-1234"
K401_ACCOUNT = "XXXX-2201"
ROTH_ACCOUNT = "XXXX-3301"
CUSTODIAN = "Harborview Sample Brokerage, Inc."
FLAW_TICKER = "SDIN"  # the holding printed $1.00 low
FLAW_DELTA = -1.00
# 1040 income that is not in showcase.json (it only feeds the profile snapshot, never the plan)
INTEREST = 838.00
DIVIDENDS = 11_624.00  # ordinary; all of it qualified


@dataclass(frozen=True)
class Holding:
    name: str
    ticker: str
    asset_class: str
    value: float
    basis: float


# (name, ticker, asset class, share of the account, basis as a share of the value)
_HOLDING_PLAN = (
    ("Sample US Total Market Index Fund", "SUTM", "equity", 0.32, 0.25),
    ("Sample US Large Cap Index Fund", "SULC", "equity", 0.24, 0.30),
    ("Sample US Mid Cap Index Fund", "SUMC", "equity", 0.10, 0.32),
    ("Sample US Small Cap Index Fund", "SUSC", "equity", 0.08, 0.38),
    ("Sample Developed International Index Fund", "SDIN", "equity", 0.15, 0.40),
    ("Sample Emerging Markets Index Fund", "SEME", "equity", 0.03, 0.50),
    ("Sample Total Bond Index Fund", "STBD", "bond", 0.08, 0.90),
)
_K401_PLAN = (  # name, asset class, share of the balance (equity funds: the first two; third is the remainder)
    ("Sample US Stock Index Fund", "equity", 0.36),
    ("Sample International Stock Index Fund", "equity", 0.15),
    ("Sample Small-Cap Stock Index Fund", "equity", None),
    ("Sample Total Bond Index Fund", "bond", None),
)
_ROTH_PLAN = (
    ("Sample US Total Market Index Fund", "equity", 0.70),
    ("Sample Developed International Index Fund", "equity", None),
)


def _cents(x: float) -> int:
    return round(x * 100)


def load_showcase(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or SHOWCASE_PATH).read_text(encoding="utf-8"))["household"]


def holdings(accounts: dict[str, Any]) -> list[Holding]:
    """Holdings whose values and bases add up, to the cent, to the household's brokerage totals."""
    total, basis = _cents(accounts["brokerage_value"]), _cents(accounts["brokerage_basis"])
    values = [round(total * share) for *_, share, _ in _HOLDING_PLAN]
    bases = [round(v * ratio) for v, (*_, ratio) in zip(values, _HOLDING_PLAN, strict=True)]
    values[0] += total - sum(values)  # the first (largest) holding absorbs the rounding
    bases[0] += basis - sum(bases)
    assert all(b <= v for b, v in zip(bases, values, strict=True))
    return [
        Holding(name, ticker, cls, v / 100, b / 100)
        for (name, ticker, cls, *_), v, b in zip(_HOLDING_PLAN, values, bases, strict=True)
    ]


def _split(total_cents: int, plan: Sequence[tuple[str, str, float | None]], equity_cents: int | None = None) -> list[int]:
    """Fund values in cents: the planned shares, with the funds that have no share taking the rest."""
    values = [round(total_cents * share) if share is not None else 0 for _, _, share in plan]
    if equity_cents is not None:  # the equity funds add up to exactly this much
        eq = [i for i, (_, cls, _) in enumerate(plan) if cls == "equity"]
        open_eq = [i for i in eq if plan[i][2] is None]
        values[open_eq[0]] = equity_cents - sum(values[i] for i in eq if i != open_eq[0])
    rest = [i for i, v in enumerate(values) if v == 0]
    values[rest[0]] = total_cents - sum(values)
    assert len(rest) == 1 and all(v > 0 for v in values)
    return values


def k401_allocation(accounts: dict[str, Any]) -> list[tuple[str, str, float]]:
    total = _cents(accounts["pretax_balance"])
    values = _split(total, _K401_PLAN, equity_cents=round(total * accounts["pretax_equity_share"]))
    return [(name, cls, v / 100) for (name, cls, _), v in zip(_K401_PLAN, values, strict=True)]


def roth_allocation(accounts: dict[str, Any]) -> list[tuple[str, str, float]]:
    values = _split(_cents(accounts["roth_balance"]), _ROTH_PLAN)
    return [(name, cls, v / 100) for (name, cls, _), v in zip(_ROTH_PLAN, values, strict=True)]


def form_1040_values(h: dict[str, Any]) -> dict[str, float]:
    """The 1040's amounts, from the tax engine through the same function the older samples use."""
    person = h["people"][0]
    v = g.form_1040_values(
        {
            "taxpayer": {"wages": person["wages"], "pretax_401k": person["pretax_401k"]},
            "spouse": {"wages": 0.0, "pretax_401k": 0.0},
            "income": {
                "taxable_interest": INTEREST,
                "qualified_dividends": DIVIDENDS,
                "ordinary_dividends": DIVIDENDS,
                "net_long_term_capital_gain": 0.0,
            },
            "children": [{"age": age} for age in h["children_ages"]],
        }
    )
    return {k: round(x, 2) for k, x in v.items()}


# =============================================================================================
# Pages
# =============================================================================================


def _draw_1040(s: _Sheet, h: dict[str, Any]) -> None:
    v = form_1040_values(h)
    person = h["people"][0]
    _header(
        s,
        g.TITLES["form_1040"],
        "U.S. Individual Income Tax Return  |  Tax year 2026 projection  |  For illustration only",
    )
    y = _info_lines(s, 100, [("Taxpayer", f"{NAME}      SSN {SSN}"), ("Address", f"{ADDRESS} (fictional)")])
    y += 8
    s.text(LEFT, y, "Filing status", bold=True)
    s.text(130, y, g.FILING_STATUS_LABELS["married_filing_jointly"])
    y += 22
    children = h["children_ages"]
    under_17 = sum(1 for age in children if age <= g.P.CTC_MAX_CHILD_AGE)
    y = _boxed_rows(
        s,
        y,
        "Household",
        [
            ("taxpayer_age", "Taxpayer age", str(person["age"])),
            ("children_under_17", "Qualifying children under 17", str(under_17)),
            *((f"child_age_{i}", f"Child {i} age", str(a)) for i, a in enumerate(children, start=1)),
        ],
    )
    y = _boxed_rows(
        s,
        y,
        "Wages by W-2 (box 1, after 401(k) deferrals)",
        [("w2_wages_taxpayer", f"W-2 wages, taxpayer ({NAME})", _usd(v["w2_wages_taxpayer"]))],
    )
    y = _table_header(s, y + 8, [("Line", IN_L, "left"), ("Description", 92, "left"), ("Amount", IN_R, "right")])
    for key, line_no, description in g.FORM_1040_LINES:
        bold = line_no in g.BOLD_LINES
        s.text(IN_L, y, line_no, bold=bold)
        s.text(92, y, description, bold=bold)
        s.text(IN_R, y, _usd(v[key]), bold=bold, align="right")
        s.rule(y + 6, gray=0.85)
        y += g.TABLE_ROW_H
    for note in (
        "Simplified layout: only the lines used by this demo are shown. Federal income tax only",
        "(no payroll taxes, itemized deductions or AMT), computed from the 2026 parameters",
        "(IRS Rev. Proc. 2025-32). Total tax (line 24) is after the child tax credit.",
    ):
        y += 10
        s.text(LEFT, y, note, size=7.5, gray=0.4)


def _draw_brokerage(s: _Sheet, h: dict[str, Any]) -> None:
    a = h["accounts"]
    _header(s, g.TITLES["brokerage_statement"], f"{CUSTODIAN}  |  Statement period: September 1 to September 30, 2026")
    y = _info_lines(
        s,
        100,
        [("Account holder", NAME), ("Account", f"Individual taxable brokerage account  {BROKERAGE_ACCOUNT}")],
    )
    y = _boxed_rows(
        s,
        y + 12,
        "Account summary",
        [
            ("brokerage_total_value", "Total account value", _usd(a["brokerage_value"])),
            ("brokerage_cost_basis", "Total cost basis", _usd(a["brokerage_basis"])),
            ("brokerage_unrealized_gain", "Unrealized gain", _usd(a["brokerage_value"] - a["brokerage_basis"])),
            ("brokerage_cash", "Cash balance (not in total above)", _usd(a["cash"])),
        ],
        bold={"brokerage_total_value"},
    )
    s.text(LEFT, y + 4, "Holdings", size=11, bold=True)
    y = _table_header(
        s,
        y + 26,
        [("Fund", IN_L, "left"), ("Ticker", 270, "left"), ("Asset class", 330, "left"), ("Value", 470, "right"), ("Cost basis", IN_R, "right")],
    )
    for hold in holdings(a):
        printed = hold.value + (FLAW_DELTA if hold.ticker == FLAW_TICKER else 0.0)  # the deliberate $1.00
        s.text(IN_L, y, hold.name, size=9)
        s.text(270, y, hold.ticker, size=9)
        s.text(330, y, hold.asset_class.capitalize(), size=9)
        s.text(470, y, _usd(printed), size=9, align="right")
        s.text(IN_R, y, _usd(hold.basis), size=9, align="right")
        s.rule(y + 6, gray=0.85)
        y += g.TABLE_ROW_H
    s.rule(y - 14, gray=0.4, width=0.8)
    s.text(IN_L, y, "Total", size=9, bold=True)
    s.text(470, y, _usd(a["brokerage_value"]), size=9, bold=True, align="right")
    s.text(IN_R, y, _usd(a["brokerage_basis"]), size=9, bold=True, align="right")
    s.text(
        LEFT,
        y + 34,
        "Index fund holdings are not FDIC insured and may lose value. Values as of statement date.",
        size=7.5,
        gray=0.4,
    )


def _draw_allocation(s: _Sheet, y: float, funds: Sequence[tuple[str, str, float]], total: float) -> float:
    s.text(LEFT, y + 18, "Fund allocation", size=11, bold=True)
    y = _table_header(
        s,
        y + 40,
        [("Fund", IN_L, "left"), ("Asset class", 300, "left"), ("Value", 440, "right"), ("% of total", IN_R, "right")],
    )
    for name, cls, value in funds:
        s.text(IN_L, y, name, size=9)
        s.text(300, y, cls.capitalize(), size=9)
        s.text(440, y, _usd(value), size=9, align="right")
        s.text(IN_R, y, f"{g.allocation_percent(value, total):.1f}%", size=9, align="right")
        s.rule(y + 6, gray=0.85)
        y += g.TABLE_ROW_H
    return y


def _draw_401k(s: _Sheet, h: dict[str, Any]) -> None:
    a, person = h["accounts"], h["people"][0]
    _header(s, g.TITLES["retirement_401k"], "Acme Sample Corp. 401(k) Savings Plan  |  Recordkeeper: Keystone Sample Retirement Services")
    y = _info_lines(
        s,
        100,
        [("Plan year", "2026 summary  (balances as of September 30, 2026)"), ("Participants", f"{NAME} ({K401_ACCOUNT})")],
    )
    s.text(LEFT, y + 18, "Participant summary", size=11, bold=True)
    y = _table_header(
        s,
        y + 40,
        [("Participant", IN_L, "left"), ("Balance", 330, "right"), ("Contributions, plan year 2026", IN_R, "right")],
    )
    s.text(IN_L, y, f"{NAME} (taxpayer)", size=9)
    s.text(330, y, _usd(a["pretax_balance"]), size=9, align="right")
    s.text(IN_R, y, _usd(person["pretax_401k"]), size=9, align="right")
    s.rule(y + 6, gray=0.85)
    y += g.TABLE_ROW_H
    s.rule(y - 14, gray=0.4, width=0.8)
    s.text(IN_L, y, "Total balance", size=9, bold=True)
    s.text(330, y, _usd(a["pretax_balance"]), size=9, bold=True, align="right")
    y += g.TABLE_ROW_H
    y = _draw_allocation(s, y, k401_allocation(a), a["pretax_balance"])
    s.text(
        LEFT,
        y + 12,
        "Contributions are employee pre-tax deferrals. Fund values are as of the balance date.",
        size=7.5,
        gray=0.4,
    )


def _draw_roth(s: _Sheet, h: dict[str, Any]) -> None:
    a = h["accounts"]
    _header(s, "Roth IRA Statement", f"{CUSTODIAN}  |  Statement period: September 1 to September 30, 2026")
    y = _info_lines(s, 100, [("Account holder", NAME), ("Account", f"Roth IRA  {ROTH_ACCOUNT}")])
    y = _boxed_rows(
        s,
        y + 12,
        "Account summary",
        [
            ("roth_total_balance", "Total balance", _usd(a["roth_balance"])),
            ("roth_contrib_ytd", "Contributions, year to date", _usd(0.0)),
        ],
        bold={"roth_total_balance"},
    )
    y = _draw_allocation(s, y - 16, roth_allocation(a), a["roth_balance"])
    s.text(LEFT, y + 12, "Qualified Roth IRA withdrawals are tax-free. Fund values are as of the statement date.", size=7.5, gray=0.4)


# =============================================================================================
# Public API
# =============================================================================================


def build_bundle(household: dict[str, Any] | None = None) -> bytes:
    """The four-page PDF, in memory."""
    h = household if household is not None else load_showcase()
    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=letter, invariant=1, pageCompression=0)
    canvas.setTitle("John Smith: sample documents (fictional)")
    canvas.setAuthor("Waramoug demo (fictional sample)")
    canvas.setSubject("Fictional sample documents for the Waramoug demo")
    sheet = _Sheet(canvas)
    for draw in (_draw_1040, _draw_brokerage, _draw_401k, _draw_roth):
        draw(sheet, h)
        _footer(sheet)
        canvas.showPage()
    canvas.save()
    return buf.getvalue()


def generate(out: Path | None = None) -> Path:
    target = Path(out) if out is not None else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_bundle())
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.docs.smith", description="Generate John Smith's fictional documents.")
    parser.add_argument("--out", type=Path, default=None, help=f"output file (default: {DEFAULT_OUT})")
    print(generate(parser.parse_args(argv).out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
