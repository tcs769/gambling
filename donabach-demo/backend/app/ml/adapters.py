"""Load the teammates' models if they are present; otherwise report `NotConnected`.

Drop model files in `backend/models/` (or the directory named by `DONABACH_MODELS_DIR`):

    recommender.pkl   a pickled object with  recommend(household) -> Recommendation
    forecaster.pkl    a pickled object with  forecast(household, years) -> IncomeForecast

(`Recommendation` and `IncomeForecast` are in `app.ml.interfaces`; a plain dict or any object
with the same fields is accepted and validated against them.) The class of the pickled object
must be importable when the server starts. Pickle files can run arbitrary code when loaded, so
only drop in files you trust.

If a file is missing, unreadable, does not implement the interface, or returns something that
violates the contract, the adapter returns `NotConnected` with the reason. It never falls back
to a made-up prediction. Files are re-read when they change on disk, so a new model needs no
server restart.
"""

from __future__ import annotations

import os
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.ml.interfaces import (
    IncomeForecast,
    IncomeForecaster,
    Recommendation,
    StrategyRecommender,
)
from app.schemas import Household

MODELS_DIR_ENV = "DONABACH_MODELS_DIR"
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
RECOMMENDER_FILE = "recommender.pkl"
FORECASTER_FILE = "forecaster.pkl"


class NotConnected(BaseModel):
    """What the app shows instead of a prediction when a model is unavailable."""

    connected: Literal[False] = False
    model: Literal["recommender", "forecaster"]
    reason: str
    expected_path: str


class ModelContractError(RuntimeError):
    """A connected model returned something that does not satisfy the interface."""


def models_dir() -> Path:
    override = os.environ.get(MODELS_DIR_ENV)
    return Path(override) if override else DEFAULT_MODELS_DIR


def _coerce(contract: type[BaseModel], raw: Any, who: str) -> Any:
    try:
        if isinstance(raw, BaseModel):
            return contract.model_validate(raw.model_dump())  # re-run the validators
        if isinstance(raw, dict):
            return contract.model_validate(raw)
        return contract.model_validate(raw, from_attributes=True)
    except ValidationError as exc:
        raise ModelContractError(f"{who} returned an invalid {contract.__name__}: {exc}") from exc


class _ValidatedRecommender:
    """Wraps the loaded object so every output is checked against the contract."""

    def __init__(self, model: StrategyRecommender):
        self._model = model

    def recommend(self, household: Household) -> Recommendation:
        return _coerce(Recommendation, self._model.recommend(household), "The recommender")


class _ValidatedForecaster:
    def __init__(self, model: IncomeForecaster):
        self._model = model

    def forecast(self, household: Household, years: int) -> IncomeForecast:
        result = _coerce(IncomeForecast, self._model.forecast(household, years), "The forecaster")
        if len(result.ages) != years:
            raise ModelContractError(
                f"The forecaster returned {len(result.ages)} years but {years} were requested"
            )
        return result


@dataclass
class _Cached:
    mtime_ns: int
    size: int
    result: Any


_cache: dict[Path, _Cached] = {}
_lock = threading.Lock()


def _load(path: Path, model: Literal["recommender", "forecaster"], method: str, wrap: type) -> Any:
    if not path.is_file():
        return NotConnected(model=model, reason=f"No model file at {path}", expected_path=str(path))
    stat = path.stat()
    with _lock:
        cached = _cache.get(path)
        if cached and (cached.mtime_ns, cached.size) == (stat.st_mtime_ns, stat.st_size):
            return cached.result
        try:
            with path.open("rb") as fh:
                loaded = pickle.load(fh)  # noqa: S301 - local, trusted model files (see module docstring)
        except Exception as exc:
            result: Any = NotConnected(
                model=model,
                reason=f"Could not load {path.name}: {type(exc).__name__}: {exc}",
                expected_path=str(path),
            )
        else:
            if callable(getattr(loaded, method, None)):
                result = wrap(loaded)
            else:
                result = NotConnected(
                    model=model,
                    reason=f"{path.name} loaded but the object has no {method}() method",
                    expected_path=str(path),
                )
        _cache[path] = _Cached(stat.st_mtime_ns, stat.st_size, result)
        return result


def load_recommender(directory: Path | None = None) -> StrategyRecommender | NotConnected:
    path = (directory or models_dir()) / RECOMMENDER_FILE
    return _load(path, "recommender", "recommend", _ValidatedRecommender)


def load_forecaster(directory: Path | None = None) -> IncomeForecaster | NotConnected:
    path = (directory or models_dir()) / FORECASTER_FILE
    return _load(path, "forecaster", "forecast", _ValidatedForecaster)


def not_connected(model: Literal["recommender", "forecaster"], reason: str) -> NotConnected:
    """A NotConnected for a model that is installed but failed at call time."""
    path = models_dir() / (RECOMMENDER_FILE if model == "recommender" else FORECASTER_FILE)
    return NotConnected(model=model, reason=reason, expected_path=str(path))
