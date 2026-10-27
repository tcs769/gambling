"""Income forecast: the connected ML forecaster if there is one, else the placeholder process.

The placeholder is the life-cycle income process in `app.sim.income` (real wage growth, permanent
and transitory shocks, job loss). It is a simple process, not a connected forecasting model, and the
response says so. It carries no "top factors": those only exist when a model supplies them.
"""

from __future__ import annotations

import numpy as np

from app.api_models import ForecastResponse
from app.ml import adapters
from app.ml.adapters import ModelContractError, NotConnected
from app.ml.interfaces import QUANTILES, IncomeForecast
from app.schemas import Household
from app.sim import income

PLACEHOLDER_LABEL = "Placeholder forecast"
MODEL_LABEL = "Income forecast model"
PLACEHOLDER_NOTE = (
    "Model not connected. This is a simple life-cycle income process (wage growth, shocks and "
    "job loss), not the output of a connected forecasting model."
)


def forecast_years(household: Household) -> int:
    """Working years ahead: from today until the household retires."""
    return max(1, household.goals.retirement_age - household.primary_age)


def placeholder_forecast(household: Household, n_paths: int, seed: int) -> IncomeForecast:
    years = forecast_years(household)
    people = household.people
    shocks = income.draw_income_shocks(n_paths, years, len(people), seed)
    wages = income.household_wages(
        [p.wages for p in people], [p.age for p in people], household.goals.retirement_age, shocks
    )
    quantiles = np.percentile(wages, [10, 25, 50, 75, 90], axis=0)
    return IncomeForecast(
        ages=[household.primary_age + t for t in range(years)],
        **{name: [float(v) for v in row] for name, row in zip(QUANTILES, quantiles, strict=True)},
    )


def forecast(household: Household, n_paths: int, seed: int) -> ForecastResponse:
    years = forecast_years(household)
    model = adapters.load_forecaster()
    reason = None
    if isinstance(model, NotConnected):
        reason = model.reason
    else:
        try:
            result = model.forecast(household, years)
        except ModelContractError as exc:
            reason = str(exc)
        except Exception as exc:  # a model that crashes is reported, not papered over
            reason = f"The forecaster failed: {type(exc).__name__}: {exc}"
        else:
            return ForecastResponse(
                connected=True,
                label=MODEL_LABEL,
                note="Forecast from the connected income model.",
                forecast=result,
                top_factors=result.top_factors,
            )
    return ForecastResponse(
        connected=False,
        label=PLACEHOLDER_LABEL,
        reason=reason,
        note=PLACEHOLDER_NOTE,
        forecast=placeholder_forecast(household, n_paths, seed),
    )
