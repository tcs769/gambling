"""Household earnings process.

PLACEHOLDER until the ML income forecaster is connected (see `app.ml`). It is a simple
life-cycle process, not a learned model, and the UI labels it "Placeholder forecast" whenever the
forecaster is absent.

Each earner has log wages = permanent component + transitory shock:
* real wage growth 2.5%/yr at 38, declining linearly to 0% at 55, then -0.5%/yr
* permanent shocks sd 7%, transitory shocks sd 7%
* job loss 3%/yr per earner, losing 60% of that earner's income that year
* wages stop at retirement age
The first simulated year is the observed income, with no shocks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GROWTH_AT_38 = 0.025
GROWTH_ZERO_AGE = 55
LATE_GROWTH = -0.005
PERMANENT_SD = 0.07
TRANSITORY_SD = 0.07
JOB_LOSS_PROBABILITY = 0.03
JOB_LOSS_SHARE = 0.60


def real_wage_growth(age: float) -> float:
    if age <= 38:
        return GROWTH_AT_38
    if age <= GROWTH_ZERO_AGE:
        return GROWTH_AT_38 * (GROWTH_ZERO_AGE - age) / (GROWTH_ZERO_AGE - 38)
    return LATE_GROWTH


@dataclass(frozen=True)
class IncomeShocks:
    """Common random numbers for the income process, shared by every strategy."""

    permanent: np.ndarray  # (paths, years, earners) log shocks to the permanent component
    transitory: np.ndarray  # (paths, years, earners) log shocks for the year only
    job_loss: np.ndarray  # (paths, years, earners) 1.0 where the earner lost the job

    @property
    def n_paths(self) -> int:
        return self.permanent.shape[0]


def draw_income_shocks(n_paths: int, n_years: int, n_earners: int, seed: int) -> IncomeShocks:
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(2)[1])
    shape = (n_paths, n_years, n_earners)
    permanent = rng.normal(0.0, PERMANENT_SD, shape)
    transitory = rng.normal(0.0, TRANSITORY_SD, shape)
    job_loss = (rng.random(shape) < JOB_LOSS_PROBABILITY).astype(float)
    # Year 0 is the observed income: no shocks.
    permanent[:, 0, :] = 0.0
    transitory[:, 0, :] = 0.0
    job_loss[:, 0, :] = 0.0
    return IncomeShocks(permanent, transitory, job_loss)


def no_shocks(n_years: int, n_earners: int) -> IncomeShocks:
    zeros = np.zeros((1, n_years, n_earners))
    return IncomeShocks(zeros, zeros.copy(), zeros.copy())


def growth_table(age: int, n_years: int) -> np.ndarray:
    """Real wage growth for each simulated year, by the earner's own age that year."""
    return np.array([real_wage_growth(age + t) for t in range(n_years)])


def working_flags(primary_age: int, retirement_age: int, n_years: int) -> np.ndarray:
    """1.0 in the years before the household retires."""
    return np.array([float((primary_age + t) < retirement_age) for t in range(n_years)])


def earner_wage_state(
    base_wage: float,
    age: int,
    primary_age: int,
    retirement_age: int,
    shocks: IncomeShocks,
    earner: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Gross real wages and the log permanent component, both (paths, years), for one earner.

    The permanent component is the only state the income process carries from one year to the
    next (the transitory shock and job loss are fresh each year), so it is all a rollout needs to
    continue an earner's wages from a given year.
    """
    n_paths, n_years, _ = shocks.permanent.shape
    growth = growth_table(age, n_years)
    # Growth from year t to t+1 uses the age in year t; the permanent shock arrives with it.
    steps = np.zeros((n_paths, n_years))
    steps[:, 1:] = growth[None, :-1] + shocks.permanent[:, 1:, earner]
    log_permanent = np.cumsum(steps, axis=1)
    wages = base_wage * np.exp(log_permanent + shocks.transitory[:, :, earner])
    wages = wages * (1.0 - JOB_LOSS_SHARE * shocks.job_loss[:, :, earner])
    working = working_flags(primary_age, retirement_age, n_years)
    return wages * working[None, :], log_permanent


def earner_wages(
    base_wage: float,
    age: int,
    primary_age: int,
    retirement_age: int,
    shocks: IncomeShocks,
    earner: int,
) -> np.ndarray:
    """Gross real wages (paths, years) for one earner. Wages stop at the household retirement age."""
    return earner_wage_state(base_wage, age, primary_age, retirement_age, shocks, earner)[0]


def household_wage_state(
    base_wages: list[float],
    ages: list[int],
    retirement_age: int,
    shocks: IncomeShocks,
) -> tuple[np.ndarray, np.ndarray]:
    """Total gross household wages (paths, years) and each earner's log permanent component
    (paths, years, 2; the second column is zero for a one-earner household)."""
    n_paths, n_years = shocks.permanent.shape[:2]
    total = np.zeros((n_paths, n_years))
    log_permanent = np.zeros((n_paths, n_years, 2))
    for i, (wage, age) in enumerate(zip(base_wages, ages, strict=True)):
        wages, lp = earner_wage_state(wage, age, ages[0], retirement_age, shocks, i)
        total += wages
        log_permanent[:, :, i] = lp
    return total, log_permanent


def household_wages(
    base_wages: list[float],
    ages: list[int],
    retirement_age: int,
    shocks: IncomeShocks,
) -> np.ndarray:
    """Total gross household wages (paths, years). `ages[0]` is the primary earner's age."""
    return household_wage_state(base_wages, ages, retirement_age, shocks)[0]
