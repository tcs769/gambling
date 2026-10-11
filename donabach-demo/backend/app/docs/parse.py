"""Read the sample documents back into fields with source boxes and rule-based confidence.

Parsing is template-specific on purpose. pdfplumber supplies every word with its bounding box;
words are grouped into text rows, a field is located by the label printed at the start of its
row, and its value is the number to the right of the label. Table cells are assigned to columns
by the x-positions of the table's header cells (words closer together than a few points form one
cell, so multi-word cells and right-aligned numbers both land in the right column).

Confidence (see `ParsedField`) is decided by `apply_cross_checks`: a field is `low` when it is
missing, `medium` when it is the stated total or derived line of a failed cross-check, and
`high` otherwise. A failed check flags only that one field, never the rows that fed it.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import pdfplumber
from pdfminer.psparser import PSException
from pdfplumber.page import Page
from pdfplumber.utils.exceptions import PdfminerException

from app.docs.models import (
    BBox,
    CrossCheck,
    DocKind,
    FieldKind,
    ParsedDocument,
    ParsedField,
)

__all__ = ["apply_cross_checks", "parse_document"]

_ROW_TOLERANCE = 3.0  # points: words whose vertical centres are this close share a text row
_CELL_GAP = 7.0  # points: a wider gap between two words starts a new table cell
_BBOX_PAD = 0.5  # points of breathing room around a value's box
_MONEY_TOLERANCE = 0.005  # half a cent


# =============================================================================================
# Words, rows, cells
# =============================================================================================


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int  # 1-based

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class _Row:
    """The words of one text line, left to right."""

    words: tuple[_Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(frozen=True)
class _Cell:
    """Neighbouring words of one row (no wide gap between them): a table cell."""

    words: tuple[_Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def x1(self) -> float:
        return self.words[-1].x1


@dataclass(frozen=True)
class _Page:
    number: int
    width: float
    height: float
    rows: tuple[_Row, ...]


def _group_rows(words: Sequence[_Word]) -> tuple[_Row, ...]:
    """Cluster words into text lines by vertical centre (steady even when font sizes differ)."""
    lines: list[list[_Word]] = []
    for word in sorted(words, key=lambda w: (w.cy, w.x0)):
        if lines and abs(word.cy - lines[-1][0].cy) <= _ROW_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return tuple(_Row(tuple(sorted(line, key=lambda w: w.x0))) for line in lines)


def _cells(row: _Row) -> list[_Cell]:
    cells: list[list[_Word]] = []
    for word in row.words:
        if cells and word.x0 - cells[-1][-1].x1 <= _CELL_GAP:
            cells[-1].append(word)
        else:
            cells.append([word])
    return [_Cell(tuple(c)) for c in cells]


def _read_page(page: Page, number: int) -> _Page:
    words = [
        _Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"], number)
        for w in page.extract_words(x_tolerance=2, y_tolerance=2)
    ]
    return _Page(number, float(page.width), float(page.height), _group_rows(words))


# =============================================================================================
# Reading values
# =============================================================================================

_MONEY_RE = re.compile(
    r"^(?P<open>\()?(?P<neg>-)?\$(?P<neg2>-)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<cents>\.\d{1,2})?(?P<close>\))?$"
)
_INTEGER_RE = re.compile(r"^\d+$")
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_CHILD_ROW_RE = re.compile(r"^child (\d+) age$", re.IGNORECASE)


def _money(token: str) -> float | None:
    """'$1,234' -> 1234.0; '($1,234)' and '-$1,234' -> -1234.0. Amounts always carry a '$'."""
    m = _MONEY_RE.match(token)
    if m is None or bool(m["open"]) != bool(m["close"]):
        return None
    amount = float(m["num"].replace(",", "") + (m["cents"] or ""))
    return -amount if (m["open"] or m["neg"] or m["neg2"]) else amount


def _integer(token: str) -> float | None:
    return float(token) if _INTEGER_RE.match(token) else None


def _percent(token: str) -> float | None:
    m = _PERCENT_RE.match(token)
    return float(m[1]) if m else None


_NUMBER_PARSERS: dict[str, Callable[[str], float | None]] = {
    "money": _money,
    "integer": _integer,
    "percent": _percent,
}


def _read_value(
    words: Sequence[_Word], kind: FieldKind
) -> tuple[float | str, tuple[_Word, ...]] | None:
    """The value among `words` (the right-hand side of a label, or one table cell), if readable."""
    if not words:
        return None
    if kind == "text":
        return " ".join(w.text for w in words), tuple(words)
    parse = _NUMBER_PARSERS[kind]
    for word in reversed(words):  # amounts sit at the right-hand edge of their line
        value = parse(word.text)
        if value is not None:
            return value, (word,)
    return None


def _norm(token: str) -> str:
    return token.lower().strip(".,;:")


def _find_row(rows: Iterable[_Row], phrase: str) -> tuple[_Row, int] | None:
    """The first row that starts with the phrase, and the number of words the phrase covers."""
    want = [_norm(t) for t in phrase.split()]
    for row in rows:
        if [_norm(w.text) for w in row.words[: len(want)]] == want:
            return row, len(want)
    return None


# =============================================================================================
# Tables
# =============================================================================================


@dataclass(frozen=True)
class _Col:
    key: str
    header: str  # header cell text; matched case-insensitively as a prefix
    align: Literal["left", "right"]  # the cell edge that lines up with the header cell's edge


@dataclass(frozen=True)
class _Table:
    page: _Page
    header_index: int
    header: dict[str, _Cell]
    cols: tuple[_Col, ...]

    def assign(self, cells: Sequence[_Cell]) -> dict[str, _Cell]:
        """Map each cell of a body row to the column whose header edge is nearest."""

        def distance(cell: _Cell, col: _Col) -> float:
            head = self.header[col.key]
            return abs(cell.x1 - head.x1) if col.align == "right" else abs(cell.x0 - head.x0)

        out: dict[str, _Cell] = {}
        for cell in cells:
            out.setdefault(min(self.cols, key=lambda c: distance(cell, c)).key, cell)
        return out

    def body(self) -> Iterator[tuple[list[_Cell], dict[str, _Cell]]]:
        """Rows under the header as (cells, cells by column key), in page order."""
        for row in self.page.rows[self.header_index + 1 :]:
            cells = _cells(row)
            yield cells, self.assign(cells)


# =============================================================================================
# Field construction
# =============================================================================================


@dataclass(frozen=True)
class _Spec:
    key: str
    label: str  # for the UI, and quoted in flags
    group: str
    kind: FieldKind
    phrase: str = ""  # text printed at the start of the field's row (one-line fields)


def _not_found(spec: _Spec, why: str = "on the document") -> str:
    """Flag text for a missing field; it always names the field."""
    return f"Could not find '{spec.label}' {why}."


class _Reader:
    """Finds labelled values and tables in a document's pages and builds `ParsedField`s."""

    def __init__(self, pages: Sequence[_Page]) -> None:
        self.pages = pages
        self.rows = [row for page in pages for row in page.rows]

    # -- one-line fields --------------------------------------------------------------------
    def line(self, spec: _Spec) -> ParsedField:
        """A `label ... value` row, found by its printed label."""
        hit = _find_row(self.rows, spec.phrase)
        if hit is None:
            return self.missing(spec, _not_found(spec))
        return self.from_row(spec, *hit)

    def from_row(self, spec: _Spec, row: _Row, skip: int) -> ParsedField:
        """The value in `row` after its first `skip` words (the label)."""
        read = _read_value(row.words[skip:], spec.kind)
        if read is None:
            return self.missing(
                spec, f"Found '{spec.label}' but could not read a value next to it."
            )
        return self.found(spec, *read)

    # -- tables -----------------------------------------------------------------------------
    def table(self, cols: Sequence[_Col]) -> _Table | None:
        """The table whose header row has exactly these columns, left to right."""
        for page in self.pages:
            for index, row in enumerate(page.rows):
                cells = _cells(row)
                if len(cells) == len(cols) and all(
                    c.text.lower().startswith(col.header.lower()) for c, col in zip(cells, cols, strict=True)
                ):
                    header = {col.key: c for c, col in zip(cells, cols, strict=True)}
                    return _Table(page, index, header, tuple(cols))
        return None

    def cell(
        self, spec: _Spec, cell: _Cell | None, meta: dict[str, str | float] | None = None
    ) -> ParsedField:
        """The value in one table cell (None when the row has no cell in that column)."""
        if cell is None:
            return self.missing(spec, _not_found(spec, "(its table cell is empty)"), meta)
        read = _read_value(cell.words, spec.kind)
        if read is None:
            return self.missing(spec, f"Could not read a value for '{spec.label}'.", meta)
        return self.found(spec, *read, meta=meta)

    # -- results ----------------------------------------------------------------------------
    def found(
        self,
        spec: _Spec,
        value: float | str,
        words: Sequence[_Word],
        meta: dict[str, str | float] | None = None,
    ) -> ParsedField:
        page = self.pages[words[0].page - 1]
        bbox = BBox(
            x0=round(max(0.0, min(w.x0 for w in words) - _BBOX_PAD), 2),
            top=round(max(0.0, min(w.top for w in words) - _BBOX_PAD), 2),
            x1=round(min(page.width, max(w.x1 for w in words) + _BBOX_PAD), 2),
            bottom=round(min(page.height, max(w.bottom for w in words) + _BBOX_PAD), 2),
        )
        return ParsedField(
            key=spec.key,
            label=spec.label,
            group=spec.group,
            kind=spec.kind,
            value=value,
            page=page.number,
            bbox=bbox,
            confidence="high",
            flag=None,
            meta=dict(meta or {}),
        )

    @staticmethod
    def missing(spec: _Spec, why: str, meta: dict[str, str | float] | None = None) -> ParsedField:
        return ParsedField(
            key=spec.key,
            label=spec.label,
            group=spec.group,
            kind=spec.kind,
            value=None,
            page=None,
            bbox=None,
            confidence="low",
            flag=why,
            meta=dict(meta or {}),
        )


# =============================================================================================
# Form 1040 (2026 projection), simplified
# =============================================================================================

_INCOME, _AGI, _TAX = "Income", "AGI and taxable income", "Tax"
_FORM_1040_SPECS: tuple[_Spec, ...] = (
    _Spec("filing_status", "Filing status", "Household", "text", "Filing status"),
    _Spec("taxpayer_age", "Taxpayer age", "Household", "integer", "Taxpayer age"),
    _Spec("spouse_age", "Spouse age", "Household", "integer", "Spouse age"),
    _Spec(
        "children_under_17",
        "Qualifying children under 17",
        "Household",
        "integer",
        "Qualifying children under 17",
    ),
    # child_age_N rows are read separately (see _child_ages): the number of children varies
    _Spec(
        "w2_wages_taxpayer",
        "Taxpayer W-2 wages (box 1)",
        "W-2 wages",
        "money",
        "W-2 wages, taxpayer",
    ),
    _Spec("w2_wages_spouse", "Spouse W-2 wages (box 1)", "W-2 wages", "money", "W-2 wages, spouse"),
    _Spec("wages_1a", "Wages (line 1a)", _INCOME, "money", "1a Wages"),
    _Spec(
        "taxable_interest_2b",
        "Taxable interest (line 2b)",
        _INCOME,
        "money",
        "2b Taxable interest",
    ),
    _Spec(
        "qualified_dividends_3a",
        "Qualified dividends (line 3a)",
        _INCOME,
        "money",
        "3a Qualified dividends",
    ),
    _Spec(
        "ordinary_dividends_3b",
        "Ordinary dividends (line 3b)",
        _INCOME,
        "money",
        "3b Ordinary dividends",
    ),
    _Spec("capital_gain_7", "Capital gain (line 7)", _INCOME, "money", "7 Capital gain"),
    _Spec("total_income_9", "Total income (line 9)", _INCOME, "money", "9 Total income"),
    _Spec(
        "adjustments_10",
        "Adjustments to income (line 10)",
        _AGI,
        "money",
        "10 Adjustments to income",
    ),
    _Spec("agi_11", "Adjusted gross income (line 11)", _AGI, "money", "11 Adjusted gross income"),
    _Spec(
        "standard_deduction_12",
        "Standard deduction (line 12)",
        _AGI,
        "money",
        "12 Standard deduction",
    ),
    _Spec("taxable_income_15", "Taxable income (line 15)", _AGI, "money", "15 Taxable income"),
    _Spec("total_tax_24", "Total tax (line 24)", _TAX, "money", "24 Total tax"),
)


def _extract_form_1040(reader: _Reader) -> list[ParsedField]:
    fields: list[ParsedField] = []
    for spec in _FORM_1040_SPECS:
        fields.append(reader.line(spec))
        if spec.key == "children_under_17":
            fields.extend(_child_ages(reader))
    return fields


def _child_ages(reader: _Reader) -> list[ParsedField]:
    """One field per 'Child N age' row; `child_age_1` is always reported (low when absent)."""
    out: list[ParsedField] = []
    for row in reader.rows:
        m = _CHILD_ROW_RE.match(" ".join(w.text for w in row.words[:3]))
        if m:
            spec = _Spec(f"child_age_{m[1]}", f"Age of child {m[1]}", "Household", "integer")
            out.append(reader.from_row(spec, row, skip=3))
    if not out:
        spec = _Spec("child_age_1", "Age of child 1", "Household", "integer")
        out.append(reader.missing(spec, _not_found(spec)))
    return out


# =============================================================================================
# Brokerage statement
# =============================================================================================

_SUMMARY = "Account summary"
_BROKERAGE_SPECS: tuple[_Spec, ...] = (
    _Spec(
        "brokerage_total_value", "Total account value", _SUMMARY, "money", "Total account value"
    ),
    _Spec("brokerage_cost_basis", "Total cost basis", _SUMMARY, "money", "Total cost basis"),
    _Spec("brokerage_unrealized_gain", "Unrealized gain", _SUMMARY, "money", "Unrealized gain"),
)
_HOLDING_COLS = (
    _Col("name", "Fund", "left"),
    _Col("ticker", "Ticker", "left"),
    _Col("asset_class", "Asset class", "left"),
    _Col("value", "Value", "right"),
    _Col("basis", "Cost basis", "right"),
)


def _row_meta(cols: dict[str, _Cell], index: int, keys: Sequence[str]) -> dict[str, str | float]:
    """Row metadata for the UI: fund name, plus whichever of `keys` the row printed."""
    meta: dict[str, str | float] = {"name": cols["name"].text if "name" in cols else f"Row {index}"}
    for key in keys:
        if key in cols:
            meta[key] = cols[key].text.strip().lower() if key == "asset_class" else cols[key].text
    return meta


def _extract_brokerage(reader: _Reader) -> list[ParsedField]:
    fields = [reader.line(spec) for spec in _BROKERAGE_SPECS]
    rows: list[dict[str, _Cell]] = []
    table = reader.table(_HOLDING_COLS)
    if table is not None:
        for cells, cols in table.body():
            if len(cells) < 2 or _norm(cells[0].text) == "total":
                break  # the printed Total row, or the end of the table
            rows.append(cols)
    if not rows:
        why = "because the holdings table is missing from the statement"
        for key, what in (("value", "value"), ("basis", "cost basis")):
            spec = _Spec(f"holding_1_{key}", f"Holding 1: {what}", "Holdings", "money")
            fields.append(reader.missing(spec, _not_found(spec, why)))
    for i, cols in enumerate(rows, start=1):
        meta = _row_meta(cols, i, ("ticker", "asset_class"))
        for key, what in (("value", "value"), ("basis", "cost basis")):
            spec = _Spec(f"holding_{i}_{key}", f"{meta['name']}: {what}", "Holdings", "money")
            fields.append(reader.cell(spec, cols.get(key), meta))
    return fields


# =============================================================================================
# 401(k) statement
# =============================================================================================

_PARTICIPANT_COLS = (
    _Col("name", "Participant", "left"),
    _Col("balance", "Balance", "right"),
    _Col("contrib", "Contributions", "right"),
)
_ALLOCATION_COLS = (
    _Col("name", "Fund", "left"),
    _Col("asset_class", "Asset class", "left"),
    _Col("value", "Value", "right"),
    _Col("pct", "% of total", "right"),
)
_BAL, _CON = "Balances", "Contributions"
# (field key, label, group, row of the participant table, column); all are money
_K401_PARTICIPANT_FIELDS = (
    ("k401_balance_taxpayer", "Taxpayer 401(k) balance", _BAL, "taxpayer", "balance"),
    ("k401_balance_spouse", "Spouse 401(k) balance", _BAL, "spouse", "balance"),
    ("k401_total_balance", "Total 401(k) balance", _BAL, "total", "balance"),
    ("k401_contrib_taxpayer", "Taxpayer contributions (plan year)", _CON, "taxpayer", "contrib"),
    ("k401_contrib_spouse", "Spouse contributions (plan year)", _CON, "spouse", "contrib"),
)
_ROW_NAMES = {
    "taxpayer": "the taxpayer's row",
    "spouse": "the spouse's row",
    "total": "the total balance row",
}
_ALLOCATION_FIELDS: tuple[tuple[str, str, FieldKind], ...] = (
    ("value", "value", "money"),
    ("pct", "share of total", "percent"),
)


def _extract_401k(reader: _Reader) -> list[ParsedField]:
    # Participant rows are recognised by their printed marker, whatever the person's name.
    by_role: dict[str, dict[str, _Cell]] = {}
    table = reader.table(_PARTICIPANT_COLS)
    if table is not None:
        for _, cols in table.body():
            name = cols["name"].text.lower() if "name" in cols else ""
            for role, hit in (
                ("taxpayer", "(taxpayer)" in name),
                ("spouse", "(spouse)" in name),
                ("total", name.startswith("total balance")),
            ):
                if hit:
                    by_role.setdefault(role, cols)

    fields: list[ParsedField] = []
    for key, label, group, role, column in _K401_PARTICIPANT_FIELDS:
        spec = _Spec(key, label, group, "money")
        if role in by_role:
            fields.append(reader.cell(spec, by_role[role].get(column)))
        else:
            why = (
                "because the participant summary table is missing from the statement"
                if table is None
                else f"because {_ROW_NAMES[role]} is missing from the participant summary"
            )
            fields.append(reader.missing(spec, _not_found(spec, why)))

    rows: list[dict[str, _Cell]] = []
    allocation = reader.table(_ALLOCATION_COLS)
    if allocation is not None:
        for cells, cols in allocation.body():
            if len(cells) < 2:
                break  # a note or the footer: the table is over
            rows.append(cols)
    if not rows:
        why = "because the fund allocation table is missing from the statement"
        for key, what, kind in _ALLOCATION_FIELDS:
            spec = _Spec(f"alloc_1_{key}", f"Fund 1: {what}", "Fund allocation", kind)
            fields.append(reader.missing(spec, _not_found(spec, why)))
    for i, cols in enumerate(rows, start=1):
        meta = _row_meta(cols, i, ("asset_class",))
        for key, what, kind in _ALLOCATION_FIELDS:
            spec = _Spec(f"alloc_{i}_{key}", f"{meta['name']}: {what}", "Fund allocation", kind)
            fields.append(reader.cell(spec, cols.get(key), meta))
    return fields


# =============================================================================================
# Cross-checks
# =============================================================================================


def _usd(amount: float) -> str:
    """$149,999, or $1,234.50 when there are cents."""
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if abs(amount - round(amount)) < _MONEY_TOLERANCE:
        return f"{sign}${round(amount):,}"
    return f"{sign}${amount:,.2f}"


def _close(a: float, b: float) -> bool:
    return abs(a - b) < _MONEY_TOLERANCE


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


@dataclass(frozen=True)
class _Check:
    name: str
    keys: tuple[str, ...]  # every field the check reads
    flag: tuple[str, ...]  # fields marked `medium` when the check fails
    run: Callable[[dict[str, float]], tuple[bool, str]]  # values by key -> (passed, sentence)


def _sum_check(
    name: str, parts: Sequence[str], total: str, subject: str, total_name: str
) -> _Check:
    """The parts must add up to the stated total; the total is the field flagged on failure."""

    def run(v: dict[str, float]) -> tuple[bool, str]:
        got, stated = sum(v[k] for k in parts), v[total]
        if _close(got, stated):
            return True, f"{subject} add up to {_usd(got)}, matching {total_name}."
        return False, (
            f"{subject} add up to {_usd(got)} but {total_name} is {_usd(stated)} "
            f"(difference {_usd(abs(got - stated))})."
        )

    return _Check(name, (*parts, total), (total,), run)


def _difference_check(
    name: str,
    minuend: tuple[str, str],
    subtrahend: tuple[str, str],
    result: tuple[str, str],
    *,
    floor_at_zero: bool = False,
) -> _Check:
    """minuend - subtrahend must equal the derived line; the derived line is flagged on failure.

    Each argument is (field key, how the sentence names it).
    """
    (mk, mn), (sk, sn), (rk, rn) = minuend, subtrahend, result

    def run(v: dict[str, float]) -> tuple[bool, str]:
        expected = v[mk] - v[sk]
        if floor_at_zero:
            expected = max(0.0, expected)
        stated = v[rk]
        if _close(expected, stated):
            return True, f"{_cap(mn)} minus {sn} is {_usd(expected)}, matching {rn}."
        return False, (
            f"{_cap(mn)} minus {sn} is {_usd(expected)} but {rn} is {_usd(stated)} "
            f"(difference {_usd(abs(expected - stated))})."
        )

    return _Check(name, (mk, sk, rk), (rk,), run)


def _percent_check(keys: Sequence[str]) -> _Check:
    """Printed percentages (one decimal) may be off by rounding, at most 0.05 per row."""

    def run(v: dict[str, float]) -> tuple[bool, str]:
        got = sum(v[k] for k in keys)
        if abs(got - 100.0) <= 0.05 * len(keys) + 1e-6:
            return True, f"Allocation percentages add up to {got:.1f}%."
        return False, f"Allocation percentages add up to {got:.1f}%, not 100%."

    # There is no stated total to blame, so every percentage is flagged on failure.
    return _Check("Allocation percentages add up to 100%", tuple(keys), tuple(keys), run)


def _numbered(by_key: dict[str, ParsedField], pattern: str) -> list[str]:
    """Keys 'holding_1_value', 'holding_2_value', ... for as long as they exist."""
    keys: list[str] = []
    while pattern.format(len(keys) + 1) in by_key:
        keys.append(pattern.format(len(keys) + 1))
    return keys


def _form_1040_checks(by_key: dict[str, ParsedField]) -> list[_Check]:
    return [
        _sum_check(
            "Total income equals lines 1a, 2b, 3b and 7",
            ["wages_1a", "taxable_interest_2b", "ordinary_dividends_3b", "capital_gain_7"],
            "total_income_9",
            "Lines 1a, 2b, 3b and 7",
            "total income (line 9)",
        ),
        _difference_check(
            "AGI equals total income minus adjustments",
            ("total_income_9", "total income"),
            ("adjustments_10", "adjustments"),
            ("agi_11", "AGI (line 11)"),
        ),
        _difference_check(
            "Taxable income equals AGI minus the standard deduction",
            ("agi_11", "AGI"),
            ("standard_deduction_12", "the standard deduction"),
            ("taxable_income_15", "taxable income (line 15)"),
            floor_at_zero=True,
        ),
        _sum_check(
            "W-2 wages add up to line 1a",
            ["w2_wages_taxpayer", "w2_wages_spouse"],
            "wages_1a",
            "W-2 wages",
            "line 1a wages",
        ),
    ]


def _brokerage_checks(by_key: dict[str, ParsedField]) -> list[_Check]:
    return [
        _sum_check(
            "Holdings add up to the statement total",
            _numbered(by_key, "holding_{}_value"),
            "brokerage_total_value",
            "Holdings",
            "the statement total",
        ),
        _sum_check(
            "Holding cost bases add up to the total cost basis",
            _numbered(by_key, "holding_{}_basis"),
            "brokerage_cost_basis",
            "Holding cost bases",
            "the total cost basis",
        ),
        _difference_check(
            "Unrealized gain equals value minus cost basis",
            ("brokerage_total_value", "total value"),
            ("brokerage_cost_basis", "cost basis"),
            ("brokerage_unrealized_gain", "the unrealized gain"),
        ),
    ]


def _k401_checks(by_key: dict[str, ParsedField]) -> list[_Check]:
    return [
        _sum_check(
            "Participant balances add up to the total balance",
            ["k401_balance_taxpayer", "k401_balance_spouse"],
            "k401_total_balance",
            "Participant balances",
            "the total balance",
        ),
        _sum_check(
            "Fund allocation adds up to the total balance",
            _numbered(by_key, "alloc_{}_value"),
            "k401_total_balance",
            "Fund values",
            "the total balance",
        ),
        _percent_check(_numbered(by_key, "alloc_{}_pct")),
    ]


_CHECKS: dict[str, Callable[[dict[str, ParsedField]], list[_Check]]] = {
    "form_1040": _form_1040_checks,
    "brokerage_statement": _brokerage_checks,
    "retirement_401k": _k401_checks,
}


def apply_cross_checks(doc_kind: str, fields: Sequence[ParsedField]) -> list[CrossCheck]:
    """Run the document's cross-checks and set each field's confidence and flag, in place.

    Found fields start from `high`. When a check fails, only its stated-total / derived field
    becomes `medium`, with the check's sentence as the flag; the rows that fed the sum stay
    `high`. A check that cannot run because an input is missing is reported as not passed
    ("Not checked"); the missing field is already `low`, and nothing else is downgraded.
    Safe to call again after editing field values (it resets found fields first).
    """
    by_key = {f.key: f for f in fields}
    for f in fields:
        if f.value is not None:
            f.confidence, f.flag = "high", None
    results: list[CrossCheck] = []
    build = _CHECKS.get(doc_kind)
    for check in build(by_key) if build else []:
        keys = list(check.keys)
        absent = [by_key[k] for k in check.keys if by_key[k].value is None]
        if absent:
            detail = f"Not checked: could not read {', '.join(f.label for f in absent)}."
            results.append(CrossCheck(name=check.name, passed=False, detail=detail, keys=keys))
            continue
        passed, detail = check.run({k: cast(float, by_key[k].value) for k in check.keys})
        results.append(CrossCheck(name=check.name, passed=passed, detail=detail, keys=keys))
        if not passed:
            for key in check.flag:
                field = by_key[key]
                field.confidence = "medium"
                field.flag = detail if field.flag is None else f"{field.flag} {detail}"
    return results


# =============================================================================================
# Public API
# =============================================================================================

_KIND_TITLES: tuple[tuple[DocKind, re.Pattern[str]], ...] = (
    ("form_1040", re.compile(r"Form 1040 \(2026 projection\), simplified", re.IGNORECASE)),
    ("brokerage_statement", re.compile(r"Brokerage Account Statement", re.IGNORECASE)),
    ("retirement_401k", re.compile(r"401\(k\) Plan Statement", re.IGNORECASE)),
)
_EXTRACTORS: dict[str, Callable[[_Reader], list[ParsedField]]] = {
    "form_1040": _extract_form_1040,
    "brokerage_statement": _extract_brokerage,
    "retirement_401k": _extract_401k,
}


def _detect_kind(first_page: _Page | None) -> tuple[DocKind, str]:
    """Document kind and printed title, from the title text near the top of page 1."""
    if first_page is None or not first_page.rows:
        return "unknown", "Unrecognised document"
    for row in first_page.rows[:6]:
        for kind, pattern in _KIND_TITLES:
            m = pattern.search(row.text)
            if m:
                return kind, m.group(0)
    return "unknown", first_page.rows[0].text[:80]  # the first line is the best hint


def parse_document(source: Path | bytes) -> ParsedDocument:
    """Parse a sample PDF given as a path or as raw bytes.

    Unrecognised or unreadable PDFs come back as kind "unknown" with no fields and no checks
    instead of raising. Only page 1 is read to decide the kind, so an unrelated PDF costs
    almost nothing however long it is.
    """
    stream = (
        io.BytesIO(bytes(source))
        if isinstance(source, (bytes, bytearray, memoryview))
        else Path(source)
    )
    try:
        with pdfplumber.open(stream) as pdf:
            sizes = [(float(p.width), float(p.height)) for p in pdf.pages]
            first = _read_page(pdf.pages[0], 1) if pdf.pages else None
            kind, title = _detect_kind(first)
            if first is None or kind == "unknown":
                return ParsedDocument(
                    doc_kind="unknown", title=title, page_sizes=sizes, fields=[], checks=[]
                )
            pages = [first, *(_read_page(p, n) for n, p in enumerate(pdf.pages[1:], start=2))]
    except (PdfminerException, PSException):
        return ParsedDocument(
            doc_kind="unknown", title="Unreadable file", page_sizes=[], fields=[], checks=[]
        )
    fields = _EXTRACTORS[kind](_Reader(pages))
    return ParsedDocument(
        doc_kind=kind,
        title=title,
        page_sizes=sizes,
        fields=fields,
        checks=apply_cross_checks(kind, fields),
    )
