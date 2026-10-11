"""Load the teammates' models if they are present; otherwise report `NotConnected`.

Drop model files in `backend/models/` (or the directory named by `DONABACH_MODELS_DIR`):

    recommender.pkl   a pickled object with  recommend(household) -> Recommendation
    forecaster.pkl    a pickled object with  forecast(household, years) -> IncomeForecast
    policy.pkl        a pickled object with  propose(state, max_actions) -> ActionProposal
    value.pkl         a pickled object with  value(state, actions) -> ValueEstimate

(The result types are in `app.ml.interfaces`; a plain dict or any object with the same fields is
accepted and validated against them. The last two serve the year-by-year planner's search.) The class of the pickled object
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
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.ml.interfaces import (
    ActionChoice,
    ActionProposal,
    DecisionState,
    IncomeForecast,
    IncomeForecaster,
    PolicyModel,
    Recommendation,
    StrategyRecommender,
    ValueEstimate,
    ValueModel,
)
from app.schemas import Household

MODELS_DIR_ENV = "DONABACH_MODELS_DIR"
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
RECOMMENDER_FILE = "recommender.pkl"
FORECASTER_FILE = "forecaster.pkl"
POLICY_FILE = "policy.pkl"
VALUE_FILE = "value.pkl"

ModelName = Literal["recommender", "forecaster", "policy", "value"]
MODEL_FILES: dict[str, str] = {
    "recommender": RECOMMENDER_FILE,
    "forecaster": FORECASTER_FILE,
    "policy": POLICY_FILE,
    "value": VALUE_FILE,
}


class NotConnected(BaseModel):
    """What the app shows instead of a prediction when a model is unavailable."""

    connected: Literal[False] = False
    model: ModelName
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


class _ValidatedPolicy:
    def __init__(self, model: PolicyModel):
        self._model = model

    def propose(self, state: DecisionState, max_actions: int) -> ActionProposal:
        result = _coerce(ActionProposal, self._model.propose(state, max_actions), "The policy model")
        if len(result.actions) > max_actions:
            raise ModelContractError(f"The policy model proposed {len(result.actions)} actions but at most {max_actions} were asked for")
        return result


class _ValidatedValue:
    def __init__(self, model: ValueModel):
        self._model = model

    def value(self, state: DecisionState, actions: Sequence[ActionChoice]) -> ValueEstimate:
        result = _coerce(ValueEstimate, self._model.value(state, actions), "The value model")
        if len(result.values) != len(actions):
            raise ModelContractError(f"The value model returned {len(result.values)} values for {len(actions)} actions")
        return result


@dataclass
class _Cached:
    mtime_ns: int
    size: int
    result: Any


_cache: dict[Path, _Cached] = {}
_lock = threading.Lock()


def _load(path: Path, model: ModelName, method: str, wrap: type) -> Any:
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


def load_policy_model(directory: Path | None = None) -> PolicyModel | NotConnected:
    path = (directory or models_dir()) / POLICY_FILE
    return _load(path, "policy", "propose", _ValidatedPolicy)


def load_value_model(directory: Path | None = None) -> ValueModel | NotConnected:
    path = (directory or models_dir()) / VALUE_FILE
    return _load(path, "value", "value", _ValidatedValue)


def not_connected(model: ModelName, reason: str) -> NotConnected:
    """A NotConnected for a model that is installed but failed at call time."""
    path = models_dir() / MODEL_FILES[model]
    return NotConnected(model=model, reason=reason, expected_path=str(path))
