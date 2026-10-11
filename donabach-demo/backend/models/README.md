# Dropping in the ML models

Two models plug into the demo. **Nothing ships here on purpose.** Until a file exists the app shows
"Model not connected" wherever the model would speak, and it never substitutes a made-up prediction.

| File | What it must unpickle to | Used by |
|---|---|---|
| `models/recommender.pkl` | an object with `recommend(household) -> Recommendation` | Plan screen, `/plan` |
| `models/forecaster.pkl` | an object with `forecast(household, years) -> IncomeForecast` | Forecast screen, `/forecast` |

Use another folder by setting `DONABACH_MODELS_DIR`. Files are re-read when they change on disk, so a new
model needs **no server restart**. Pickle files can run code when loaded: only drop in files you trust.
`*.pkl` / `*.joblib` here are git-ignored so a model is not committed by accident.

The class of the pickled object must be importable when the server starts: define it in a module on the
Python path (for example `backend/app/ml/my_models.py`) and pickle an instance of it.

## The contract (`app/ml/interfaces.py`)

* **Input**: a `Household` (`app/schemas.py`). Build the model's features with
  `household_features(household)`: the exact 37-feature vector (`FEATURE_NAMES`) the app builds, so you
  train on what the app will feed you.
* **Recommender output**: one entry per strategy choice, each with the recommended `option`, your
  `probability` for it (0 to 1) and, optionally, the full `distribution` over options, plus `top_factors`
  (`{feature, direction: "up"|"down", weight: 0..1}`).

  | Choice | Options |
  |---|---|
  | `stock_share` | `70`, `80`, `90`, `100` |
  | `conversion` | `none`, `fill12_low`, `fill12_every`, `fill22_low`, `fill22_every`, `fill24_low`, `fill24_every` |
  | `private_credit` | `off`, `on` |
  | `direct_indexing` | `off`, `on` |
  | `goal_bonds` | `off`, `on` |

* **Forecaster output**: `ages` and per-year quantiles `p10 <= p25 <= p50 <= p75 <= p90` of household income
  in real 2026 dollars for the next `years` years (one value per age), plus `top_factors`.
* A plain `dict` with the same fields is accepted; it is validated against the contract. Anything that
  violates it is reported in the UI as "not connected" with the reason (never papered over).

## How the planner uses the recommender

With a recommender connected, `/plan` scores the model's top recommendation plus its **five nearest
alternatives** (fewest and smallest option changes, ties broken by your joint probability) with the search
engine and shows **"Model recommended"** next to **"Verified by the engine"** with both scores. Without
one it searches all 224 strategies and labels the result "Search planner (model not connected)".

## Training data

```bash
cd backend && . .venv/bin/activate
python export_training_data.py --k 2000 --paths 150 --seed 1 --out data/training_data.parquet
```

Each row is one synthetic household (ranges are configurable: `SamplingRanges` in the script): the 37
features, `label_*` columns for the engine's best strategy, and `best_score`, `ria_score`,
`score_gap_to_second` (how far the best *different* result trailed the winner; near zero means the label is
soft). Exact ties are labelled with the first strategy in menu order (for example "low-income years only"
rather than "every year"). About 15 households a second on 4 cores.

## A minimal recommender

```python
# backend/app/ml/my_models.py
from app.ml.interfaces import (
    ChoiceRecommendation, Factor, OptionProbability, Recommendation, household_features,
)
from app.planner.strategies import CHOICES


class MyRecommender:
    def __init__(self, heads, feature_names):
        self.heads = heads                  # {choice: fitted classifier with predict_proba / classes_}
        self.feature_names = feature_names

    def recommend(self, household):
        f = household_features(household)
        x = [[f[name] for name in self.feature_names]]
        entries = []
        for choice in CHOICES:
            clf = self.heads[choice]
            probs = clf.predict_proba(x)[0]
            dist = [OptionProbability(option=str(c), probability=float(p)) for c, p in zip(clf.classes_, probs)]
            best = max(dist, key=lambda d: d.probability)
            entries.append(ChoiceRecommendation(
                choice=choice, option=best.option, probability=best.probability, distribution=dist))
        # top_factors must come from the model itself (permutation importance, SHAP, linear
        # coefficients, ...). Never hardcode them: the UI presents them as what drove the prediction.
        factors = [Factor(feature=name, direction="up" if w > 0 else "down", weight=min(1.0, abs(w)))
                   for name, w in self.explain(x[0])]
        return Recommendation(choices=entries, top_factors=factors)


# training script
import pickle
from app.ml.my_models import MyRecommender
pickle.dump(MyRecommender(fitted_heads, feature_names), open("models/recommender.pkl", "wb"))
```

`backend/tests/stubs.py` has complete, working test doubles for both interfaces. They exist only to test
the plumbing and must never be placed in this folder.
