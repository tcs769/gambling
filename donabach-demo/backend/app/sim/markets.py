"""Real (inflation-adjusted) annual asset returns.

Correlated normal draws from a fixed seed. Every strategy is evaluated on the identical set of
futures (common random numbers), so differences between strategies are not sampling noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.tax.params_2026 import ASSUMED_INFLATION

EQUITY, BOND, PRIVATE_CREDIT = 0, 1, 2
ASSETS = ("equity", "bond", "private_credit")

MEANS = np.array([0.055, 0.015, 0.035])  # real arithmetic mean returns
SDS = np.array([0.16, 0.05, 0.08])
# Equity-bond 0.1 and equity-private credit 0.5 are specified. The bond-private credit
# correlation is not; 0.1 is assumed (same as equity-bond) and keeps the matrix positive definite.
CORRELATION = np.array(
    [
        [1.0, 0.1, 0.5],
        [0.1, 1.0, 0.1],
        [0.5, 0.1, 1.0],
    ]
)

DIVIDEND_YIELD = 0.018  # equity dividends: qualified, taxed each year in the brokerage account
BOND_INTEREST_YIELD = 0.035  # taxable bond interest, ordinary income, on brokerage bond balances
# The typical advisor's costs (Update 4, 12.1). Sources and what was read of them: reports/final_report.md, "Update 4".
# * Fund expense ratios: Morningstar's US Fund Fee Study puts the asset-weighted average of active US equity funds at 0.60%
#   (data year 2024; 0.58% for 2025) and ICI's at 0.64%; active bond funds 0.45% (ICI: 0.44%; Morningstar's figure was not
#   found, so this one rests on ICI alone). The good RIA and Donabach hold index funds at 0.03% to 0.10%, which the model leaves out.
# * Cash: the typical advisor keeps 3% of the portfolio in cash (an assumption: the ICI liquidity ratio of equity funds is 1.7%).
#   Cash earns the long-run real return on Treasury bills, 0.5% (UBS/Dimson-Marsh-Staunton, USA 1900-2025), or 2.5% a year
#   in interest at the model's 2% inflation, taxed as ordinary income.
ACTIVE_EXPENSE_EQUITY = 0.0060
ACTIVE_EXPENSE_BOND = 0.0045
TYPICAL_CASH_SHARE = 0.03
CASH_REAL_RETURN = 0.005
CASH_INTEREST_YIELD = 0.025
# Taxable income yield of private credit held in the brokerage account, taxed as ordinary interest.
# The model is in real dollars but taxes nominal income. Bonds show the convention: their taxable
# yield (3.5%) exceeds their real return (1.5%) by the 2.0% of inflation that is implied
# (`ASSUMED_INFLATION`). Private credit's return is almost all contractual interest, so its taxable
# yield is its 3.5% real return plus the same 2.0%: 5.5%. (Inside the pre-tax and Roth accounts it
# is not taxed each year.)
PRIVATE_CREDIT_INCOME_YIELD = float(MEANS[PRIVATE_CREDIT]) + ASSUMED_INFLATION

# A stock's own movement beside the market's, in the direct-indexing book (app/sim/stocks.py): the annualized standard
# deviation of its return after the market's part is taken out. Two published estimates bracket it:
#   * Campbell, Lettau, Malkiel and Xu (2022), "Idiosyncratic Equity Risk Two Decades Later", NBER Working Paper 29916
#     (Critical Finance Review 12, 2023): the value-weighted average idiosyncratic volatility of US stocks was 26% a year
#     from 1962 to 1997 and 28% from 1997 to 2021 (market volatility 12% and 18%), net of industry effects.
#   * S&P Dow Jones Indices, "The Dispersion-Correlation Map": the annualized dispersion of S&P 500 constituents' returns sat
#     between 20% and 25% from 1990 to 2015.
# 25% is taken (the top of the second, just under the first: a sleeve of large stocks, and the first's daily-return measure
# includes microstructure noise). With the model's 16% market volatility a stock's total volatility is then 30%.
# `app.study.harvest_calibration` and the report show what 20% and 30% do (reports/final_report.md, Update 4).
STOCK_IDIO_VOL = 0.25

MIN_RETURN = -0.95  # a normal draw can never wipe out more than this in a year

DEFAULT_SEED = 2026


@dataclass(frozen=True)
class Assumptions:
    """Return assumptions. The default is exactly the specification; the others exist for sensitivity runs
    (`app.study.sensitivity`) and are never used by the app.

    pc_mode "normal": private credit is a correlated normal like the other assets (the specification).
    pc_mode "stress": private credit is calm (N(calm_mean, calm_sd), independent of equities) except in a
    stress year, which is any year equities fall more than `stress_trigger` standard deviations below their
    mean (about 1 year in 10); then it is N(stress_mean, stress_sd). This puts fat, equity-linked tails on
    private credit while keeping its overall mean and volatility near the specified 3.5% and 8%.
    """

    means: tuple[float, float, float] = (0.055, 0.015, 0.035)
    sds: tuple[float, float, float] = (0.16, 0.05, 0.08)
    correlation: tuple[tuple[float, ...], ...] = ((1.0, 0.1, 0.5), (0.1, 1.0, 0.1), (0.5, 0.1, 1.0))
    pc_mode: str = "normal"
    stress_trigger: float = -1.28
    calm_mean: float = 0.049
    calm_sd: float = 0.06
    stress_mean: float = -0.10
    stress_sd: float = 0.10


DEFAULT_ASSUMPTIONS = Assumptions()


def draw_returns(
    n_paths: int, n_years: int, seed: int = DEFAULT_SEED, assumptions: Assumptions | None = None
) -> np.ndarray:
    """Return array (paths, years, 3) of real returns for equity, bonds, private credit."""
    a = assumptions or DEFAULT_ASSUMPTIONS
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(2)[0])
    chol = np.linalg.cholesky(np.array(a.correlation))
    means, sds = np.array(a.means), np.array(a.sds)
    z = rng.standard_normal((n_paths, n_years, 3)) @ chol.T
    returns = np.maximum(means + sds * z, MIN_RETURN)
    if a.pc_mode == "stress":
        extra = rng.standard_normal((n_paths, n_years))  # independent draw for the private-credit state
        stress = z[:, :, EQUITY] < a.stress_trigger
        pc = np.where(stress, a.stress_mean + a.stress_sd * extra, a.calm_mean + a.calm_sd * extra)
        returns[:, :, PRIVATE_CREDIT] = np.maximum(pc, MIN_RETURN)
    elif a.pc_mode != "normal":
        raise ValueError(f"unknown private credit mode {a.pc_mode!r}")
    return returns


def expected_returns(n_years: int, assumptions: Assumptions | None = None) -> np.ndarray:
    """One deterministic path at the expected returns, shape (1, years, 3)."""
    means = np.array((assumptions or DEFAULT_ASSUMPTIONS).means)
    return np.broadcast_to(means, (1, n_years, 3)).copy()


def with_equity_shock(returns: np.ndarray, year: int, equity_return: float) -> np.ndarray:
    """Copy of `returns` with the equity return in `year` forced to `equity_return`."""
    shocked = returns.copy()
    if 0 <= year < shocked.shape[1]:
        shocked[:, year, EQUITY] = max(equity_return, MIN_RETURN)
    return shocked
