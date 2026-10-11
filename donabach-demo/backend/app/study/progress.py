"""Render `reports/progress.md` from the per-step measurements in `reports/progress/step_*.json`.

    python -m app.study.progress

Each JSON file is written by `python -m app.study.measure` right after a change, so the table shows
which change moved the sample household's recommendation and annualized advantage. Nothing here
is edited by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[3] / "reports"

INTRO = """# Sample household: recommendation and annualized advantage after each change

The sample household is the fictional demo household (two earners aged 38 and 37, $250,000 of wages,
$620,000 invested). For each step the planner searches its whole strategy menu on 400 simulated
futures (seed 2026, the app's defaults) and the winner is scored against the good-RIA baseline.

* **Median advantage**: the difference in median after-tax wealth at the horizon, annualized as a
  growth-rate difference, `(plan / baseline)^(1/years) - 1`.
* **Risk-adjusted advantage**: the same, using certainty-equivalent wealth (CRRA utility, risk
  aversion 3, $50,000 floor), the planner's own objective.
* The headline figures are measured on **held-out futures** (2,000 paths the search never saw), so
  picking the best of many strategies is not scored on the futures it was picked on. The in-sample
  figures (what the app showed before the review) are listed for comparison. "Mean of 5 seeds" repeats
  the whole search-then-score on seeds 2026 to 2030.
* Every step is one change; nothing is tuned toward a target. Rows are cumulative.
"""


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def render(reports: Path = REPORTS) -> str:
    files = sorted((reports / "progress").glob("step_*.json"))
    lines = [INTRO, ""]
    baselines: list[str] = []
    runs = [json.loads(f.read_text()) for f in files]
    for run in runs:
        for name in run["app_seed_run"]["baselines"]:
            if name not in baselines:
                baselines.append(name)
    titles = {"good_ria": "good RIA", "typical_advisor": "typical advisor"}
    for baseline in baselines:
        lines += [
            f"## Against the {titles.get(baseline, baseline)}",
            "",
            "| Step | Years | Recommendation (seed 2026) | Median adv. | Risk-adj. adv. | Mean of 5 seeds (median / risk-adj.) | In-sample (median / risk-adj.) | Chance of a shortfall: plan / baseline |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for run in runs:
            app = run["app_seed_run"]
            if baseline not in app["baselines"]:
                continue
            held = app["baselines"][baseline]["held_out"]
            ins = app["baselines"][baseline]["in_sample"]
            mean = run["mean"][baseline]["held_out"]
            short = app["baselines"][baseline].get("shortfall")
            short_text = f"{short['plan'] * 100:.1f}% / {short['baseline'] * 100:.1f}%" if short else "not recorded"
            lines.append(
                f"| {run['label']} | {app['years']} | {app['strategy_label']} | {_pct(held['median'])} | "
                f"{_pct(held['risk_adjusted'])} | {_pct(mean['median'])} / {_pct(mean['risk_adjusted'])} | "
                f"{_pct(ins['median'])} / {_pct(ins['risk_adjusted'])} | {short_text} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    out = REPORTS / "progress.md"
    out.write_text(render())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
