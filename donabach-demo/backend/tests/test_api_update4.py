"""The API's Update 4 additions: the two valuations at 80, the annual charitable giving answer and what-if edit, and the showcase's
passed-to-heirs figures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import make_demo_household

from app import showcase
from app.main import app
from app.planner import plan as planner

client = TestClient(app)
SMALL = {"n_eval_paths": 60, "adaptive": False}


@pytest.fixture(scope="module")
def household_json():
    return make_demo_household().model_dump(mode="json")


@pytest.fixture(scope="module")
def plan(household_json):
    response = client.post("/plan", json={"household": household_json, **SMALL})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_plan_carries_both_valuations_with_their_labels_and_the_rate_that_was_assumed(plan):
    settings = plan["settings"]
    assert settings["liquidated_label"] == "Liquidated at 80" and settings["heirs_label"] == "Passed to heirs at 80"
    assert settings["heirs_rate"] == 0.24
    note = settings["heirs_note"]
    assert "24%" in note and "step-up" in note and "ten years" in note
    assert note == planner.heirs_note()


def test_every_baseline_and_the_stat_cards_have_the_second_valuation(plan):
    stats = plan["stats"]
    for key in ("typical_outcome_heirs", "ria_typical_outcome_heirs"):
        assert stats[key]["median"] > 0 and stats[key]["p10"] <= stats[key]["median"] <= stats[key]["p90"]
    ria = next(b for b in plan["baselines"] if b["key"] == "good_ria")
    assert stats["advantage_heirs"] == ria["advantage_heirs"]
    assert stats["ria_typical_outcome_heirs"] == ria["outcome_heirs"]
    for b in plan["baselines"]:
        adv = b["advantage_heirs"]
        # the advantage in dollars is the gap between the two medians the screen shows
        assert adv["median_dollars"] == pytest.approx(stats["typical_outcome_heirs"]["median"] - b["outcome_heirs"]["median"])
        assert adv["median"] != b["advantage"]["median"]  # a different valuation, a different number


def test_the_planner_still_chooses_under_the_liquidated_valuation(plan):
    assert plan["strategy"]["outcome"]["median"] == plan["stats"]["typical_outcome"]["median"]


def test_charitable_giving_is_an_answer_and_reaches_the_household():
    ids = [d["id"] for d in client.post("/documents/sample").json()["documents"]]
    given = client.post("/household", json={"document_ids": ids, "answers": {"charitable_giving": 12_000.0}})
    assert given.status_code == 200 and given.json()["household"]["goals"]["charitable_giving"] == 12_000.0
    assert client.post("/household", json={"document_ids": ids, "answers": {"charitable_giving": -1}}).status_code == 422
    assert client.post("/household", json={"document_ids": ids}).json()["household"]["goals"]["charitable_giving"] == 0.0


def test_the_what_if_can_change_the_giving(household_json):
    r = client.post("/plan/whatif", json={"household": household_json, "edits": {"charitable_giving": 15_000.0}, **SMALL})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["household"]["goals"]["charitable_giving"] == 15_000.0
    assert {"field": "charitable_giving", "label": "Charitable giving a year", "before": "$0", "after": "$15,000"} in body["changes"]
    assert client.post("/plan/whatif", json={"household": household_json, "edits": {"charitable_giving": -5.0}, **SMALL}).status_code == 422


def test_a_household_that_gives_gets_a_plan_that_gives_lots(household_json):
    household = dict(household_json)
    household["accounts"] = {**household["accounts"], "brokerage_value": 600_000.0, "brokerage_basis": 100_000.0}
    household["goals"] = {**household["goals"], "charitable_giving": 20_000.0}
    plan = client.post("/plan", json={"household": household, **SMALL}).json()
    year0 = plan["rows"][0]
    assert year0["total_tax"] > 0
    # the plan's year-by-year table is the engine's: a household that gives shows the deduction in its tax lines
    detail = client.post("/plan/year-detail", json={"household": household, "choices": plan["strategy"]["choices"], "year_index": 0})
    assert detail.status_code == 200, detail.text
    labels = [line["label"] for line in detail.json()["tax_lines"]]
    assert any("deduction" in label.lower() for label in labels)


@pytest.fixture
def served(tmp_path, monkeypatch):
    path = tmp_path / "showcase.json"
    path.write_text(showcase.FIXTURE.read_text())
    monkeypatch.setenv(showcase.FIXTURE_ENV, str(path))
    showcase.reset()
    yield client.get("/showcase").json()
    showcase.reset()


def test_the_showcase_wealth_screen_has_the_second_valuation_median_only(served):
    wealth = served["wealth"]
    assert wealth["liquidated_label"] == "Liquidated at 80"
    heirs = wealth["heirs"]
    assert heirs["label"] == "Passed to heirs at 80" and heirs["rate"] == 0.24 and "24%" in heirs["note"]
    assert set(heirs) == {"label", "note", "rate", "median_rate", "median_dollars", "plan_median_at_horizon", "advisor_median_at_horizon"}
    assert heirs["median_dollars"] == pytest.approx(heirs["plan_median_at_horizon"] - heirs["advisor_median_at_horizon"])
    assert heirs["median_rate"] != wealth["advantage"]["median_rate"]
    # the risk-adjusted advantage appears once: in the liquidated figures only
    assert "risk_adjusted_rate" in wealth["advantage"] and "risk_adjusted_rate" not in heirs
