# Dropping in the ML models

Four models plug into the demo. **Nothing ships here on purpose.** Until a file exists the app shows
"Model not connected" wherever the model would speak, and it never substitutes a made-up prediction.

| File | What it must unpickle to | Used by |
|---|---|---|
| `models/recommender.pkl` | an object with `recommend(household) -> Recommendation` | Plan screen, `/plan` |
| `models/forecaster.pkl` | an object with `forecast(household, years) -> IncomeForecast` | Forecast screen, `/forecast` |
| `models/policy.pkl` | an object with `propose(state, max_actions) -> ActionProposal` | the year-by-year planner's search (not wired in yet, see below) |
| `models/value.pkl` | an object with `value(state, actions) -> ValueEstimate` | the year-by-year planner's search (not wired in yet) |

`GET /models/status` reports each of the four as connected or not, with the reason.

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
  | `stock_share` | `50`, `60`, `70`, `80`, `90`, `100` |
  | `conversion` | `none`, `fill12_low`, `fill12_every`, `fill22_low`, `fill22_every`, `fill24_low`, `fill24_every` |
  | `private_credit` | `0`, `5`, `10`, `15` |
  | `direct_indexing` | `off`, `on` |
  | `goal_bonds` | `off`, `on` |
  | `k401` | `pretax`, `roth`, `roth_low` |
  | `goal_funding` | `sell`, `borrow` |

* **Forecaster output**: `ages` and per-year quantiles `p10 <= p25 <= p50 <= p75 <= p90` of household income
  in real 2026 dollars for the next `years` years (one value per age), plus `top_factors`.
* A plain `dict` with the same fields is accepted; it is validated against the contract. Anything that
  violates it is reported in the UI as "not connected" with the reason (never papered over).

## How the planner uses the recommender

With a recommender connected, `/plan` scores the model's top recommendation plus its **five nearest
alternatives** (fewest and smallest option changes, ties broken by your joint probability) with the search
engine and shows **"Model recommended"** next to **"Verified by the engine"** with both scores. Without
one it searches all 4,032 strategies (a screening pass on 100 simulated futures, the best 150 scored on 400)
and labels the result "Search planner (model not connected)".

## Training data: the household recommender

```bash
cd backend && . .venv/bin/activate
python export_training_data.py --k 2000 --paths 150 --seed 1 --out data/training_data.parquet
```

Each row is one synthetic household (ranges are configurable: `SamplingRanges` in the script): the 37
features, `label_*` columns for the engine's best strategy, and `best_score`, `ria_score`,
`score_gap_to_second` (how far the best *different* result trailed the winner; near zero means the label is
soft). Exact ties are labelled with the first strategy in menu order (for example "low-income years only"
rather than "every year").

---

# The year-by-year planner's policy and value models

The **year-by-year planner** (`app/sim/adaptive.py`) decides each year, after that year's returns are known,
using only what the household could know then. For each candidate action it simulates **K fresh futures** from
where the household stands (default 32): the candidate is applied for the rest of this year, then the best
fixed strategy is followed to the horizon, and the candidate is scored by the **certainty-equivalent
after-tax wealth** at the horizon (the same objective as everywhere else). It starts from the fixed
strategy's action and improves one decision at a time (coordinate search, two passes), then re-tests the
changes it proposes on fresh futures before keeping them.

That search is expensive and produces exactly what a learned policy and a learned value function train on,
the way AlphaZero's search produces targets for its networks:

* a **policy model** learns *state -> the action the search chose*. Connected, it proposes the few actions
  worth scoring (each with the probability the search would pick it) so the search scores a handful of
  candidates instead of dozens.
* a **value model** learns *(state, action) -> the score the rollouts gave it*. Connected, it estimates a
  candidate's score so the search can skip candidates that are clearly worse.

**Nothing is trained in this repository and the models are not wired into the search yet.** The interfaces
below and the training data are the hand-off; with no model file the app says so
(`GET /models/status` -> `policy` / `value`: `connected: false`, with the reason and the path it looks at).

## The action

`ActionChoice` is the six decisions the planner makes each year (the B3 action space):

| Field | Values | Meaning |
|---|---|---|
| `stock_share` | `0.5, 0.6, 0.7, 0.8, 0.9, 1.0` | share of long-term money in stocks after this year's rebalance |
| `conversion_bracket` | `0, 12, 22, 24` | Roth conversion this year: none, or fill that federal bracket |
| `private_credit` | `0.0, 0.05, 0.10, 0.15` | private credit sleeve, share of long-term money |
| `k401` | `"pretax"`, `"roth"` | type of this year's 401(k) contribution |
| `goal_funding` | `"sell"`, `"borrow"` | how a goal due this year is paid (ignored when none is due) |
| `realize_gains` | `true`, `false` | realize gains up to the top of the 0% capital-gains bracket |

## The state

`DecisionState` is what a model is shown at one decision:

* `household`: `household_features(household)` of the household **as the plan started** (the 37 `FEATURE_NAMES`);
* `state`: the plan's state at this decision (`STATE_FEATURE_NAMES`, below), built by
  `app.planner.decision_data.state_feature_array`, all in real 2026 dollars;
* `continuation`: the action the best fixed strategy would take this year.

| State feature | Meaning |
|---|---|
| `age`, `year_index`, `years_remaining` | primary earner's age; years since the plan started; years left to the horizon (80) |
| `retired`, `years_to_retirement` | retired flag; years until retirement (0 once retired) |
| `aged_spouses`, `rmds_required` | spouses aged 65+ this year; 1 once required minimum distributions have begun |
| `pretax_equity`, `pretax_bonds`, `pretax_private_credit` | pre-tax account balance by asset class |
| `roth_equity`, `roth_bonds`, `roth_private_credit` | Roth account balance by asset class |
| `brokerage_equity`, `brokerage_basis`, `brokerage_bonds_and_cash`, `brokerage_private_credit` | taxable account, with the cost basis of its stocks |
| `goal_bucket` | money set aside in bonds for goals coming due |
| `total_wealth`, `pretax_share`, `roth_share`, `taxable_share` | all balances; share of each account type |
| `equity_share`, `private_credit_share`, `brokerage_unrealized_gain_share` | share in stocks, in private credit; unrealized gain as a share of brokerage stocks |
| `loss_carryforward`, `loan`, `loan_to_brokerage`, `unfunded_so_far` | capital-loss carryforward; outstanding box-spread loan, and as a share of the brokerage account; spending the plan could not fund so far |
| `wages_this_year`, `wages_expected_this_year`, `wages_vs_expected` | household wages this year; what was expected; the ratio (a job loss shows here) |
| `k401_contribution_room_used`, `social_security_this_year`, `spending_need_from_portfolio` | 401(k) contribution as a share of the limit; Social Security income; spending the portfolio must cover after Social Security |
| `goal_due_this_year`, `goal_amount_this_year`, `goal_amount_next_three_years`, `years_to_next_goal` | goals: due now, how much, due soon, years to the next (99 if none) |
| `equity_return_this_year`, `bond_return_this_year` | this year's returns (known: the planner decides after them) |
| `equity_growth_last_three_years`, `equity_growth_since_start` | cumulative stock growth over the last three years / since the plan started |

Features only ever look at the path up to and including the decision year; a test fails if any of them
reads a later return or wage.

## The contract

```python
class PolicyModel(Protocol):
    def propose(self, state: DecisionState, max_actions: int) -> ActionProposal: ...

class ValueModel(Protocol):
    def value(self, state: DecisionState, actions: Sequence[ActionChoice]) -> ValueEstimate: ...
```

* `ActionProposal.actions`: at least one `ProposedAction(action, probability)`, **ordered from most to least
  probable, distinct, probabilities summing to at most 1**, and no more than `max_actions`. `top_factors`
  as for the other models (never hardcode them).
* `ValueEstimate.values`: one **finite, positive** number per requested action, in the same order: the
  estimated certainty-equivalent after-tax wealth at the horizon, real 2026 dollars.
* Dicts are accepted and validated; anything that violates the contract is reported as "not connected" with
  the reason (`ModelContractError` inside the app), never papered over.

## Training data (`export_training_data.py --decisions`)

```bash
cd backend && . .venv/bin/activate
python export_training_data.py --decisions --k 500 --decision-paths 4 --seed 1 --decisions-dir data/decisions
```

For each of K synthetic households the best fixed strategy is found, then the year-by-year planner runs on a
few fresh futures (`--decision-paths`, default 4) recording every decision. Three parquet files:

**`households.parquet`**: one row per household: `household_id`, the 37 `FEATURE_NAMES` of the household as the
plan started, `label_*` (the best fixed strategy's choices, the continuation policy), `n_paths` and `underfunded`
(the household cannot fund its own plan: its median after-tax wealth at the horizon is below the $50,000 floor of
the objective).

**`decisions.parquet`**: one row per decision (household x path x year), the policy model's table.

| Columns | Meaning |
|---|---|
| `household_id`, `path`, `year` | join keys (`year` counts from 0; `age` is a state feature) |
| `STATE_FEATURE_NAMES` (46) | the state at the decision |
| `chosen_stock_share`, `chosen_conversion_bracket`, `chosen_private_credit`, `chosen_k401_roth`, `chosen_goal_borrow`, `chosen_realize_gains` | **the action the search chose** (the policy model's target); `k401_roth`, `goal_borrow`, `realize_gains` are 0/1 |
| `continuation_*` | the same six columns for the action the best fixed strategy would have taken |
| `departs` | the chosen action differs from the continuation action |
| `n_candidates` | candidates fully scored this year |
| `ce_chosen`, `ce_continuation`, `ce_gain` | the rollouts' score (certainty-equivalent wealth at the horizon, dollars) of the chosen and continuation action, and `ce_chosen / ce_continuation - 1` |
| `ce_at_floor` | the continuation's score sits at the $50,000 floor: every candidate is scored at the floor in such a decision, so it carries no information (see below) |
| `changes_proposed`, `changes_confirmed` | changes the search proposed, and how many survived the re-test on fresh futures |
| `realized_wealth_at_horizon` | **the realized outcome**: after-tax wealth at the horizon that this path actually reached under the year-by-year planner |
| `realized_wealth_fixed_strategy` | the same path's horizon wealth under the best fixed strategy, for comparison |
| `risk_aversion` | the objective's risk aversion (CRRA gamma) |

**`candidates.parquet`**: one row per candidate action the search **fully scored** in a decision, the value
model's table: `household_id`, `path`, `year`, `candidate` (0 is always the continuation action), the six
action columns (`stock_share`, `conversion_bracket`, `private_credit`, `k401_roth`, `goal_borrow`,
`realize_gains`), `ce` (the rollouts' certainty-equivalent score, dollars), `ce_relative_to_continuation`,
`rank` (1 = best score), `is_chosen`, `is_continuation`. Join to `decisions` on (`household_id`, `path`,
`year`) for the state. Candidates are the coordinate search's: the continuation plus one-decision changes from
whichever action was the incumbent, so they are not a random sample of the action space.

Training notes:

* **Policy model**: classify the six `chosen_*` columns from the state (and `household`). Most decisions keep
  the continuation action (`departs` is about 5 to 40% of rows depending on the settings), so weight or
  evaluate on the departures too. `ce_gain` says how much a departure was worth.
* **Value model**: regress `ce` (or its log) on (state, action columns). Scores of one decision share the same
  rollouts, so *differences* between candidates are far more accurate than levels: consider training on
  `ce_relative_to_continuation`.
* **Split by `household_id`, never by row**: all rows of a household share its futures and strategy.
* **Underfunded households carry no information.** The objective counts wealth below $50,000 as $50,000, so for a household
  that runs out of money every candidate scores exactly the floor. The exporter's random households include some
  (retirement spending is drawn without a sustainability check); filter on `ce_at_floor` / `underfunded`, or export with
  `--drop-underfunded`, which leaves them out (ids keep counting them).
* The scores are Monte Carlo estimates (K = 32 rollouts per candidate by default); the label noise is
  documented in `reports/adaptive_decision_quality.md`.
* About 1 household a second on 4 cores with the defaults.

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

## A minimal policy and value model

```python
# backend/app/ml/my_search_models.py
from app.ml.interfaces import ActionChoice, ActionProposal, ProposedAction, ValueEstimate


class MyPolicy:
    def __init__(self, heads, feature_names):
        self.heads = heads                  # one classifier per action column, trained on decisions.parquet
        self.feature_names = feature_names

    def propose(self, state, max_actions):
        x = [[{**state.household, **state.state}[name] for name in self.feature_names]]
        ranked = self.rank_joint_actions(x[0])      # your code: [(ActionChoice, probability), ...] best first
        return ActionProposal(actions=[ProposedAction(action=a, probability=p) for a, p in ranked[:max_actions]])


class MyValue:
    def __init__(self, model, feature_names):
        self.model, self.feature_names = model, feature_names

    def value(self, state, actions):
        base = {**state.household, **state.state}
        rows = [[*[base[n] for n in self.feature_names], a.stock_share, a.conversion_bracket,
                 a.private_credit, a.k401 == "roth", a.goal_funding == "borrow", a.realize_gains]
                for a in actions]
        return ValueEstimate(values=[float(v) for v in self.model.predict(rows)])
```

`backend/tests/stubs.py` has complete, working test doubles for all the interfaces. They exist only to test
the plumbing and must never be placed in this folder.
