"""What does stock-by-stock direct indexing actually harvest, and how does it compare with the 3% assumption?

The simulator used to assume that a direct-indexed account harvests 85% of an equity decline plus 3% of its value a year of
"dispersion" harvest, scaled by the basis ratio (`HARVEST_*` in `app/sim/simulate.py`, the specification's rule). The book in
`app/sim/stocks.py` replaces it: 100 stocks that move with the market and on their own, each with its own lots.

This study runs a sleeve on its own, with the flows of a household (new money bought each year, and sales to pay fees and
taxes), over the model's market futures, and records what the book harvests each year as a share of the sleeve's value.

1. How the harvest depends on the account: by age of the account and by basis ratio, with the old rule's figure beside it.
2. A fit of the aggregate rule (decline share, dispersion, the power of the basis ratio) to the book. The fitted rule is what the
   planner uses where the book is too slow to run for every candidate (screening the menu, the adaptive planner's rollouts);
   everything it reports is measured on the book.

    python -m app.study.harvest_calibration --out ../reports/harvest_calibration.md
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.jit import jit, prange
from app.sim import markets
from app.sim import simulate as sim
from app.sim.state import (
    N_STOCKS,
    NSTATE_DI,
    S_BBASIS,
    S_BE,
    S_STACC,
    S_STCG,
    S_YEAR,
)
from app.sim.stocks import di_buy, di_sell, di_start, di_year_begin

YEARS = 42
PATHS = 600
DIV = markets.DIVIDEND_YIELD


@jit(parallel=True, nogil=True)
def _sleeves(rets, g, basis_ratio, contribution, sale, theta, out_r, out_b, out_h, out_v):
    """One sleeve per path: value 1 at the start. Each year: prices move and dividends are bought back, losses above `theta` are
    harvested, then `sale` of the value is sold (fees and taxes) and `contribution` of it is bought (new money)."""
    n_paths = rets.shape[0]
    for p in prange(n_paths):
        st = np.zeros(NSTATE_DI)
        st[S_BE] = 1.0
        st[S_BBASIS] = basis_ratio
        di_start(st)
        st[S_STCG] = 0.0
        for t in range(rets.shape[1]):
            st[S_YEAR] = t
            r = rets[p, t]
            opening = st[S_BE]
            basis_before = st[S_BBASIS] + DIV * opening
            loss, _ = di_year_begin(st, t, 1.0 + r - DIV, g[p, t], DIV, theta, True)
            st[S_BBASIS] += DIV * opening
            value = st[S_BE]
            out_r[p, t] = r
            out_b[p, t] = min(1.0, basis_before / value) if value > 0.0 else 1.0
            out_h[p, t] = loss / value if value > 0.0 else 0.0
            out_v[p, t] = value
            di_sell(st, sale * value)
            st[S_STACC] = 0.0
            di_buy(st, contribution * st[S_BE])


@dataclass
class Sleeves:
    r: np.ndarray  # (paths, years) the equity return
    basis: np.ndarray  # basis ratio after the year's growth, before harvesting
    harvest: np.ndarray  # share of the sleeve's value harvested as losses that year
    value: np.ndarray


def run_sleeves(
    contribution: float,
    sale: float,
    basis_ratio: float = 1.0,
    idio_vol: float = markets.STOCK_IDIO_VOL,
    theta: float = sim.HARVEST_THRESHOLD,
    paths: int = PATHS,
    years: int = YEARS,
    seed: int = 2026,
) -> Sleeves:
    rets = markets.draw_returns(paths, years, seed)[:, :, markets.EQUITY]
    z = np.random.default_rng(np.random.SeedSequence(seed).spawn(4)[3]).standard_normal((paths, years, N_STOCKS), dtype=np.float32)
    g = np.exp(np.float32(idio_vol) * z - np.float32(0.5 * idio_vol**2)).astype(np.float32)
    shape = (paths, years)
    out = [np.zeros(shape) for _ in range(4)]
    _sleeves(np.ascontiguousarray(rets), g, basis_ratio, contribution, sale, theta, *out)
    return Sleeves(*out)


def aggregate_rule(r: np.ndarray, basis: np.ndarray, decline_share: float, dispersion: float, power: float, cap: float = sim.HARVEST_CAP_OF_VALUE) -> np.ndarray:
    """The aggregate rule as a share of the sleeve's value: `decline_share` of the decline plus `dispersion` x basis ratio ** power."""
    decline = np.maximum(0.0, -r) / (1.0 + r)
    return np.minimum(decline_share * decline + dispersion * basis**power, cap)


def spec_rule(r: np.ndarray, basis: np.ndarray) -> np.ndarray:
    return aggregate_rule(r, basis, sim.HARVEST_DECLINE_SHARE, sim.HARVEST_DISPERSION, 1.0)


# The flows the sleeves are run with: (new money bought as a share of the value, share sold for fees and taxes), and the
# basis ratio the account starts with. A household's brokerage account is anywhere in this range.
FLOWS = [(c, s) for c in (0.0, 0.03, 0.08) for s in (0.005, 0.03, 0.08)]
STARTS = (1.0, 0.7, 0.4)


def pooled(idio_vol: float = markets.STOCK_IDIO_VOL, theta: float = sim.HARVEST_THRESHOLD, paths: int = PATHS) -> Sleeves:
    parts = [run_sleeves(c, s, b0, idio_vol, theta, paths) for c, s in FLOWS for b0 in STARTS]
    return Sleeves(*(np.concatenate([getattr(p, f).ravel() for p in parts]) for f in ("r", "basis", "harvest", "value")))


def fit(sleeves: Sleeves) -> tuple[float, float, float, float]:
    """Least squares for (decline share, dispersion, power of the basis ratio) of the aggregate rule, over the pooled years
    (each year weighted equally). The power is searched on a grid, the other two solved exactly. Returns them and the r-squared."""
    r, b, h = sleeves.r, sleeves.basis, sleeves.harvest
    decline = np.maximum(0.0, -r) / (1.0 + r)
    best = (np.inf, 0.0, 0.0, 1.0)
    for power in np.arange(0.5, 12.01, 0.25):
        x = np.column_stack([decline, b**power])
        coef, *_ = np.linalg.lstsq(x, h, rcond=None)
        coef = np.maximum(coef, 0.0)
        sse = float(((x @ coef - h) ** 2).sum())
        if sse < best[0]:
            best = (sse, float(coef[0]), float(coef[1]), float(power))
    sse, share, dispersion, power = best
    r2 = 1.0 - sse / float(((h - h.mean()) ** 2).sum())
    return share, dispersion, power, r2


def by_age(c: float, s: float, b0: float, **kwargs) -> dict[str, float]:
    sl = run_sleeves(c, s, b0, **kwargs)
    mean = sl.harvest.mean(axis=0)
    old = spec_rule(sl.r, sl.basis).mean(axis=0)
    out = {}
    for label, lo, hi in (("year 1", 0, 1), ("years 2 to 5", 1, 5), ("years 6 to 15", 5, 15), ("years 16 to 42", 15, 42)):
        out[label] = float(mean[lo:hi].mean())
        out[label + " (old rule)"] = float(old[lo:hi].mean())
    out["basis ratio, year 1"] = float(sl.basis[:, 0].mean())
    out["basis ratio, year 15"] = float(sl.basis[:, 14].mean())
    out["basis ratio, year 40"] = float(sl.basis[:, 39].mean())
    return out


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def render(idio_vol: float, theta: float, seconds: float | None = None) -> str:
    sleeves = pooled(idio_vol, theta)
    share, dispersion, power, r2 = fit(sleeves)
    lines = [
        "# Stock-by-stock direct indexing: what it harvests, against the 3% assumption",
        "",
        "Generated by `python -m app.study.harvest_calibration`. A sleeve of 100 synthetic stocks on its own, run over the model's "
        f"market futures ({PATHS} per row, {YEARS} years), with the stocks' own volatility {idio_vol:.0%} a year "
        f"(`markets.STOCK_IDIO_VOL`) and losses harvested when a lot costs {theta:.0%} more than its stock's price. "
        "'Harvest' is the loss realized each year as a share of the sleeve's value. 'Old rule' is the specification's: 85% of an "
        "equity decline plus 3% of the value a year, scaled by the basis ratio.",
        "",
        "## Harvest by age of the account",
        "",
        "Flows are new money bought each year and the share sold for fees and taxes, both as a share of the value. "
        "Every row starts at value 1.",
        "",
        "| Start (basis ratio) | New money a year | Sold a year | Year 1 | Years 2 to 5 | Years 6 to 15 | Years 16 to 42 | Basis ratio at year 1 / 15 / 40 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b0 in STARTS:
        for c, s in ((0.0, 0.03), (0.03, 0.03), (0.08, 0.03)):
            d = by_age(c, s, b0, idio_vol=idio_vol, theta=theta)
            cells = " | ".join(f"{_pct(d[k])} (old {_pct(d[k + ' (old rule)'])})" for k in ("year 1", "years 2 to 5", "years 6 to 15", "years 16 to 42"))
            lines.append(
                f"| {b0:.1f} | {c:.0%} | {s:.0%} | {cells} | {d['basis ratio, year 1']:.2f} / {d['basis ratio, year 15']:.2f} / {d['basis ratio, year 40']:.2f} |"
            )
    lines += [
        "",
        "## Pooled over every flow and start",
        "",
        f"Across {len(FLOWS) * len(STARTS)} combinations of new money (0%, 3%, 8% of the value), sales (0.5%, 3%, 8%) and starting basis "
        f"ratio (1.0, 0.7, 0.4):",
        "",
        f"* the book harvests **{_pct(float(sleeves.harvest.mean()))}** of the sleeve's value a year on average; the old rule gives "
        f"**{_pct(float(spec_rule(sleeves.r, sleeves.basis).mean()))}** for the same years and states;",
        f"* in years the market rises the book harvests {_pct(float(sleeves.harvest[sleeves.r >= 0].mean()))} (old rule: "
        f"{_pct(float(spec_rule(sleeves.r, sleeves.basis)[sleeves.r >= 0].mean()))}), in years it falls "
        f"{_pct(float(sleeves.harvest[sleeves.r < 0].mean()))} (old rule: {_pct(float(spec_rule(sleeves.r, sleeves.basis)[sleeves.r < 0].mean()))}).",
        "",
        "## The aggregate rule fitted to the book",
        "",
        "The planner cannot run the book for every candidate (it takes about thirty times as long as a fund), so it screens the menu "
        "and imagines the future in the adaptive planner's rollouts with the specification's rule of the same form, its constants fitted "
        "to the pooled book (least squares over every year of every sleeve above):",
        "",
        "| | Share of a decline harvested | Dispersion harvest (share of value a year) | Power of the basis ratio |",
        "|---|---|---|---|",
        f"| The specification's rule | {sim.HARVEST_DECLINE_SHARE:.2f} | {sim.HARVEST_DISPERSION:.3f} | 1 |",
        f"| Fitted to the book (R squared {r2:.2f}) | {share:.2f} | {dispersion:.3f} | {power:g} |",
        "",
        f"`HARVEST_CAL_DECLINE`, `HARVEST_CAL_DISPERSION` and `HARVEST_CAL_POWER` in `app/sim/simulate.py` hold the fitted values "
        f"(now {sim.HARVEST_CAL_DECLINE}, {sim.HARVEST_CAL_DISPERSION}, {sim.HARVEST_CAL_POWER}). A test checks them against this fit.",
    ]
    if seconds is not None:
        lines += ["", f"_Computed in {seconds:,.0f} seconds._"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--idio-vol", type=float, default=markets.STOCK_IDIO_VOL)
    parser.add_argument("--theta", type=float, default=sim.HARVEST_THRESHOLD)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    text = render(args.idio_vol, args.theta, time.perf_counter() - started)
    text = text.replace("_Computed in 0 seconds._", f"_Computed in {time.perf_counter() - started:,.0f} seconds._")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
