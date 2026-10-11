"""Real (inflation-adjusted) annual asset returns.

Correlated normal draws from a fixed seed. Every strategy is evaluated on the identical set of
futures (common random numbers), so differences between strategies are not sampling noise.
"""

from __future__ import annotations

import numpy as np

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

MIN_RETURN = -0.95  # a normal draw can never wipe out more than this in a year

DEFAULT_SEED = 2026


def draw_returns(n_paths: int, n_years: int, seed: int = DEFAULT_SEED) -> np.ndarray:
    """Return array (paths, years, 3) of real returns for equity, bonds, private credit."""
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(2)[0])
    chol = np.linalg.cholesky(CORRELATION)
    z = rng.standard_normal((n_paths, n_years, 3)) @ chol.T
    return np.maximum(MEANS + SDS * z, MIN_RETURN)


def expected_returns(n_years: int) -> np.ndarray:
    """One deterministic path at the expected returns, shape (1, years, 3)."""
    return np.broadcast_to(MEANS, (1, n_years, 3)).copy()


def with_equity_shock(returns: np.ndarray, year: int, equity_return: float) -> np.ndarray:
    """Copy of `returns` with the equity return in `year` forced to `equity_return`."""
    shocked = returns.copy()
    if 0 <= year < shocked.shape[1]:
        shocked[:, year, EQUITY] = max(equity_return, MIN_RETURN)
    return shocked
