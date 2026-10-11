"""M6: the HTTP API end to end."""

from __future__ import annotations

import pickle
import time

import pytest
from fastapi.testclient import TestClient
from tests import stubs
from tests.conftest import make_demo_household

from app.docs import generate
from app.main import app
from app.ml import adapters
from app.planner.search import SCREEN_KEEP
from app.schemas import HORIZON_AGE
from app.store import SAMPLE_IDS

client = TestClient(app)
SAMPLE_DOC_IDS = list(SAMPLE_IDS.values())


@pytest.fixture(scope="module")
def sample_docs():
    response = client.post("/documents/sample")
    assert response.status_code == 200
    return response.json()["documents"]


@pytest.fixture(scope="module")
def profile(sample_docs):
    response = client.post("/household", json={"document_ids": [d["id"] for d in sample_docs]})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def household_json():
    return make_demo_household().model_dump(mode="json")


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(adapters.MODELS_DIR_ENV, str(tmp_path))
    return tmp_path


# --- Basics ---------------------------------------------------------------------------------


def test_health_and_openapi():
    assert client.get("/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    for path in [
        "/documents/sample", "/documents/upload", "/documents/{doc_id}/parse", "/documents/{doc_id}/file",
        "/household", "/forecast", "/plan", "/plan/year-detail", "/plan/whatif",
    ]:
        assert path in paths


def test_models_status_reports_not_connected_without_files(models_dir):
    status = client.get("/models/status").json()
    for model in ("recommender", "forecaster", "policy", "value"):
        assert status[model]["connected"] is False and "No model file" in status[model]["reason"]
        assert status[model]["model"] == model


# --- Documents ------------------------------------------------------------------------------


def test_sample_documents_load_and_are_idempotent(sample_docs):
    assert {d["id"] for d in sample_docs} == set(SAMPLE_DOC_IDS)
    assert {d["kind"] for d in sample_docs} == {"form_1040", "brokerage_statement", "retirement_401k"}
    assert all(d["pages"] == 1 and d["size_bytes"] > 1000 for d in sample_docs)
    again = client.post("/documents/sample").json()["documents"]
    assert {d["id"] for d in again} == set(SAMPLE_DOC_IDS)


def test_parse_returns_values_boxes_and_confidence(sample_docs):
    by_kind = {d["kind"]: d["id"] for d in sample_docs}
    body = client.post(f"/documents/{by_kind['brokerage_statement']}/parse").json()
    fields = {f["key"]: f for f in body["parsed"]["fields"]}
    total = fields["brokerage_total_value"]
    assert total["value"] == 150_000 and total["confidence"] == "medium"
    assert "149,999" in total["flag"] and "150,000" in total["flag"]
    assert total["page"] == 1 and total["bbox"]["x1"] > total["bbox"]["x0"]
    assert fields["brokerage_cost_basis"]["confidence"] == "high"
    assert body["document"]["kind"] == "brokerage_statement"
    flagged = [f for f in body["parsed"]["fields"] if f["confidence"] != "high"]
    assert [f["key"] for f in flagged] == ["brokerage_total_value"]


def test_the_pdf_is_served_to_the_viewer(sample_docs):
    doc = sample_docs[0]
    response = client.get(f"/documents/{doc['id']}/file")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "inline" in response.headers["content-disposition"]


def test_unknown_documents_are_404():
    assert client.get("/documents/nope/file").status_code == 404
    assert client.post("/documents/nope/parse").status_code == 404
    assert client.post("/household", json={"document_ids": ["nope"]}).status_code == 404


def test_upload_accepts_a_pdf_and_rejects_everything_else():
    docs = generate.build_documents()
    ok = client.post("/documents/upload", files=[("files", ("my-1040.pdf", docs["form_1040"], "application/pdf"))])
    assert ok.status_code == 200
    uploaded = ok.json()["documents"][0]
    assert uploaded["name"] == "my-1040.pdf" and uploaded["kind"] == "form_1040"
    assert client.get(f"/documents/{uploaded['id']}/file").content == docs["form_1040"]
    bad = client.post("/documents/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert bad.status_code == 422 and "not a PDF" in bad.json()["detail"]
    broken = client.post("/documents/upload", files=[("files", ("x.pdf", b"%PDF-1.4 garbage", "application/pdf"))])
    assert broken.status_code == 422


def test_an_unrecognized_pdf_parses_to_no_fields():
    from reportlab.pdfgen.canvas import Canvas
    import io

    buf = io.BytesIO()
    canvas = Canvas(buf)
    canvas.drawString(100, 700, "A shopping list")
    canvas.save()
    doc = client.post("/documents/upload", files=[("files", ("list.pdf", buf.getvalue(), "application/pdf"))]).json()["documents"][0]
    parsed = client.post(f"/documents/{doc['id']}/parse").json()["parsed"]
    assert parsed["doc_kind"] == "unknown" and parsed["fields"] == []


# --- Household ------------------------------------------------------------------------------


def test_household_is_built_from_the_confirmed_documents(profile):
    h = profile["household"]
    assert [p["age"] for p in h["people"]] == [38, 37]
    assert [p["wages"] for p in h["people"]] == [140_000, 110_000]
    assert [p["pretax_401k"] for p in h["people"]] == [24_500, 24_500]
    assert h["children_ages"] == [8]
    a = h["accounts"]
    assert a["brokerage_value"] == 150_000 and a["brokerage_basis"] == 110_000
    assert a["pretax_balance"] == 400_000 and a["pretax_equity_share"] == pytest.approx(0.75)
    assert a["roth_balance"] == 30_000 and a["cash"] == 40_000
    assert h["goals"]["retirement_age"] == 62 and h["social_security"]["annual_benefit"] == 50_000
    assert profile["total_assets"] == 620_000


def test_the_profile_computes_this_years_tax_and_labels_estimates(profile):
    assert profile["tax_return"]["agi"] == pytest.approx(206_300)
    assert profile["tax_return"]["federal_total"] == pytest.approx(25_232)
    assert profile["tax_return"]["illinois_tax"] == pytest.approx(9_777.4875, abs=0.01)
    assert profile["tax_lines"][-1]["label"] == "Marginal federal rate"
    estimated = {line["label"] for line in profile["accounts"] if line["estimated"]}
    assert estimated == {"Roth IRA", "Cash"}
    assert profile["estimated"] == ["roth_balance", "cash", "social_security"]
    assert {g["label"] for g in profile["goals"]} == {"Home purchase", "College", "Retirement", "Social Security"}
    assert any(g["estimated"] for g in profile["goals"] if g["label"] == "Social Security")


def test_answers_and_corrections_flow_into_the_household(sample_docs):
    ids = [d["id"] for d in sample_docs]
    body = {
        "document_ids": ids,
        "overrides": {"brokerage_total_value": 149_999},
        "answers": {"retirement_age": 60, "retirement_spending": 90_000, "home_purchase_in_years": None, "roth_balance": 55_000},
    }
    h = client.post("/household", json=body).json()["household"]
    assert h["accounts"]["brokerage_value"] == 149_999 and h["accounts"]["roth_balance"] == 55_000
    assert h["goals"]["retirement_age"] == 60 and h["goals"]["home_purchase_in_years"] is None


def test_values_that_could_not_be_read_are_reported_not_defaulted(sample_docs):
    docs = generate.build_documents(omit=["taxpayer_age"])
    up = client.post("/documents/upload", files=[("files", ("1040.pdf", docs["form_1040"], "application/pdf"))]).json()["documents"][0]
    ids = [up["id"], SAMPLE_IDS["brokerage_statement"], SAMPLE_IDS["retirement_401k"]]
    response = client.post("/household", json={"document_ids": ids})
    assert response.status_code == 422
    missing = response.json()["detail"]["missing"]
    assert [m["key"] for m in missing] == ["taxpayer_age"]
    fixed = client.post("/household", json={"document_ids": ids, "overrides": {"taxpayer_age": 38}})
    assert fixed.status_code == 200 and fixed.json()["household"]["people"][0]["age"] == 38


def test_answers_are_validated(sample_docs):
    ids = [d["id"] for d in sample_docs]
    assert client.post("/household", json={"document_ids": ids, "answers": {"retirement_age": 40}}).status_code == 422
    assert client.post("/household", json={"document_ids": []}).status_code == 422
    # A household cannot retire before it is the age it already is.
    older = client.post("/household", json={"document_ids": ids, "overrides": {"taxpayer_age": 65}})
    assert older.status_code == 422 and "retirement age" in older.text


# --- Forecast -------------------------------------------------------------------------------


def test_forecast_without_a_model_is_a_labelled_placeholder(household_json, models_dir):
    r = client.post("/forecast", json={"household": household_json}).json()
    assert r["connected"] is False and r["label"] == "Placeholder forecast"
    assert "Model not connected" in r["note"] and "No model file" in r["reason"]
    f = r["forecast"]
    assert f["ages"] == list(range(38, 62))  # working years until the retirement age of 62
    assert f["p50"][0] == pytest.approx(250_000, rel=0.15)
    assert all(a <= b <= c <= d <= e for a, b, c, d, e in zip(f["p10"], f["p25"], f["p50"], f["p75"], f["p90"], strict=True))
    assert f["p90"][-1] > f["p10"][-1]  # uncertainty fans out
    assert r["top_factors"] == []  # the placeholder never invents explanations


def test_placeholder_is_reproducible_in_demo_mode(household_json, models_dir):
    a = client.post("/forecast", json={"household": household_json}).json()["forecast"]
    b = client.post("/forecast", json={"household": household_json}).json()["forecast"]
    assert a == b


def test_a_connected_forecaster_is_used_and_its_factors_shown(household_json, models_dir):
    (models_dir / "forecaster.pkl").write_bytes(pickle.dumps(stubs.StubForecaster()))
    r = client.post("/forecast", json={"household": household_json}).json()
    assert r["connected"] is True and r["label"] == "Income forecast model"
    assert r["forecast"]["p50"][0] == 250_000
    assert r["top_factors"] == [{"feature": "wages_total", "direction": "up", "weight": 0.9}]


def test_a_forecaster_that_breaks_the_contract_falls_back_to_the_labelled_placeholder(household_json, models_dir):
    (models_dir / "forecaster.pkl").write_bytes(pickle.dumps(stubs.WrongLengthForecaster()))
    r = client.post("/forecast", json={"household": household_json}).json()
    assert r["connected"] is False and "requested" in r["reason"] and r["label"] == "Placeholder forecast"


# --- Plan -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plan(household_json):
    client.post("/plan", json={"household": household_json, "n_paths": 50})  # warm
    response = client.post("/plan", json={"household": household_json})
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_under_two_seconds(household_json):
    client.post("/plan", json={"household": household_json})
    start = time.perf_counter()
    assert client.post("/plan", json={"household": household_json}).status_code == 200
    assert time.perf_counter() - start < 2.0


def test_plan_without_a_recommender_is_the_labelled_search_planner(plan):
    assert plan["planner_label"] == "Search planner (model not connected)"
    assert plan["recommender"]["status"]["connected"] is False
    assert plan["recommender"]["recommendation"] is None and plan["recommender"]["candidates"] == []
    assert plan["settings"]["strategies_searched"] == 1008 and len(plan["searched"]) == SCREEN_KEEP  # the equity-first family
    assert plan["settings"]["planning_style"] == "equity_first"
    assert plan["settings"]["risk_aversion"] == 3.0 and plan["settings"]["wealth_floor"] == 50_000
    assert plan["searched"][0]["is_chosen"] and plan["searched"][0]["rank"] == 1


def test_the_default_plan_is_equity_first_and_the_balanced_style_is_the_original_search(plan, household_json):
    choices = plan["strategy"]["choices"]
    assert choices["reserve"] in ("2", "4", "6") and choices["stock_share"] == "100" and choices["goal_bonds"] == "off"
    assert "everything else in stocks" in plan["strategy"]["sentence"] and "next" in plan["strategy"]["sentence"]
    assert all(r["choices"]["reserve"] != "off" for r in plan["searched"])
    balanced = client.post("/plan", json={"household": household_json, "planning_style": "balanced", "adaptive": False}).json()
    assert balanced["settings"]["planning_style"] == "balanced" and balanced["settings"]["strategies_searched"] == 4032
    assert balanced["strategy"]["choices"]["reserve"] == "off" and "Hold" in balanced["strategy"]["sentence"]
    assert client.post("/plan", json={"household": household_json, "planning_style": "aggressive"}).status_code == 422
    # the what-if endpoint takes the same setting
    whatif = client.post("/plan/whatif", json={"household": household_json, "planning_style": "balanced", "adaptive": False, **SMALL})
    assert whatif.status_code == 200 and whatif.json()["plan"]["settings"]["planning_style"] == "balanced"
    default_whatif = client.post("/plan/whatif", json={"household": household_json, "adaptive": False, **SMALL})
    assert default_whatif.json()["plan"]["settings"]["planning_style"] == "equity_first"


def test_the_equity_first_plan_holds_stocks_outside_a_reserve_in_every_year_of_its_table(plan):
    rows = plan["rows"]
    assert len(rows) == HORIZON_AGE - 38 and all(0.75 <= r["stock_share"] <= 1.0 for r in rows)  # the share the reserve and the sleeve leave
    assert plan["stats"]["shortfall_chance"] < 0.05 and plan["strategy"]["outcome"]["median"] > plan["ria"]["outcome"]["median"]
    assert plan["advantage"][-1]["cumulative_median"] > 0  # the attribution steps end on the strategy itself


def test_plan_contents_are_consistent(plan):
    s, st = plan["strategy"], plan["stats"]
    assert set(s["choices"]) == {
        "stock_share", "conversion", "private_credit", "direct_indexing", "goal_bonds", "k401", "goal_funding", "reserve"
    }
    assert s["sentence"].endswith(".") and "Hold" in s["sentence"] and plan["reason"]
    assert st["typical_outcome"] == s["outcome"] and st["years"] == HORIZON_AGE - 38
    assert st["advantage_total"] == pytest.approx(st["typical_outcome"]["median"] - st["ria_typical_outcome"]["median"])
    assert st["advantage_per_year"] == pytest.approx(st["advantage_total"] / (HORIZON_AGE - 38))
    assert sum(a["delta_median"] for a in plan["advantage"]) == pytest.approx(st["advantage_total"], rel=1e-9)
    assert [a["label"] for a in plan["advantage"]][0] == "Lower fee"
    fan = plan["fan"]
    assert fan["ages"][0] == 38 and fan["ages"][-1] == HORIZON_AGE and len(fan["p50"]) == HORIZON_AGE - 38 + 1
    assert fan["p50"][-1] == pytest.approx(st["typical_outcome"]["median"])
    assert plan["ria_fan"]["p50"][-1] == pytest.approx(st["ria_typical_outcome"]["median"])
    assert fan["p50"][0] == plan["ria_fan"]["p50"][0]  # both start from today's wealth


def test_plan_table_has_every_year_and_ties_out(plan):
    rows = plan["rows"]
    assert [r["age"] for r in rows] == list(range(38, HORIZON_AGE))
    assert rows[0]["wages"] == 250_000 and rows[-1]["wages"] == 0
    assert rows[3]["goal_paid"] == 120_000 and sum(r["goal_paid"] for r in rows) == 260_000
    labels = {r["age"]: r["goal_label"] for r in rows if r["goal_paid"] > 0}
    assert labels == {41: "Home purchase", 48: "College", 49: "College", 50: "College", 51: "College"}
    assert all(r["goal_label"] is None for r in rows if r["goal_paid"] == 0)
    assert all(r["total_tax"] == pytest.approx(r["federal_tax"] + r["illinois_tax"]) for r in rows)
    assert all(0.2 < r["stock_share"] <= 1.0 for r in rows)  # 25 points below the start at the lowest
    assert rows[-1]["wealth"] > rows[0]["wealth"]


def test_plan_is_reproducible_in_demo_mode_and_varies_otherwise(household_json):
    a = client.post("/plan", json={"household": household_json}).json()
    b = client.post("/plan", json={"household": household_json}).json()
    assert a["settings"]["seed"] == b["settings"]["seed"] == 2026
    for r in (a, b):
        r["settings"]["elapsed_seconds"] = 0
    assert a == b
    c = client.post("/plan", json={"household": household_json, "demo_mode": False}).json()
    d = client.post("/plan", json={"household": household_json, "demo_mode": False}).json()
    assert c["settings"]["seed"] != d["settings"]["seed"]
    assert c["stats"]["typical_outcome"]["median"] != d["stats"]["typical_outcome"]["median"]


def test_plan_paths_are_configurable_and_validated(household_json):
    small = client.post("/plan", json={"household": household_json, "n_paths": 100}).json()
    assert small["settings"]["n_paths"] == 100
    assert client.post("/plan", json={"household": household_json, "n_paths": 5}).status_code == 422


def test_a_connected_recommender_is_scored_next_to_the_engine(household_json, models_dir):
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.StubRecommender(with_distribution=True)))
    plan = client.post("/plan", json={"household": household_json}).json()
    assert plan["planner_label"].startswith("Model-guided planner")
    panel = plan["recommender"]
    assert panel["status"]["connected"] is True
    assert len(panel["candidates"]) == 6 and len(plan["searched"]) == 6
    assert panel["model_strategy"]["choices"]["stock_share"] == "90"
    assert panel["recommendation"]["top_factors"][0]["feature"] == "age"
    assert panel["verified_strategy"]["choices"] == plan["strategy"]["choices"]
    assert isinstance(panel["agrees"], bool)
    # Both are scored by the engine, and the verified one is at least as good as the model's pick.
    assert panel["verified_strategy"]["outcome"]["score"] >= panel["model_strategy"]["outcome"]["score"]
    assert sum(1 for c in panel["candidates"] if c["is_model_pick"]) == 1
    assert plan["settings"]["strategies_searched"] == 6


def test_a_connected_recommenders_alternatives_come_from_the_planning_styles_menu(household_json, models_dir):
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.StubRecommender(with_distribution=True)))
    default = client.post("/plan", json={"household": household_json}).json()  # the equity-first style
    near = [c for c in default["recommender"]["candidates"] if not c["is_model_pick"]]
    assert len(near) == 5 and all(c["choices"]["reserve"] != "off" for c in near)
    assert default["recommender"]["model_strategy"]["choices"]["reserve"] == "off"  # the model's own pick is scored as given
    balanced = client.post("/plan", json={"household": household_json, "planning_style": "balanced"}).json()
    assert all(c["choices"]["reserve"] == "off" for c in balanced["recommender"]["candidates"])


def test_a_model_that_recommends_a_spending_reserve_is_scored_with_it(household_json, models_dir):
    picks = dict(stubs.StubRecommender().picks, stock_share="100", private_credit="15", conversion="fill24_every", reserve="6")
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.StubRecommender(picks)))
    panel = client.post("/plan", json={"household": household_json}).json()["recommender"]
    assert panel["status"]["connected"] is True
    assert panel["model_strategy"]["choices"]["reserve"] == "6" and panel["model_strategy"]["choices"]["stock_share"] == "100"
    assert "6-year spending reserve" in panel["model_strategy"]["label"]


def test_a_recommender_that_proposes_an_impossible_reserve_is_reported_not_connected(household_json, models_dir):
    picks = dict(stubs.StubRecommender().picks, reserve="6")  # its stock share is 90, and a reserve needs 100
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.StubRecommender(picks)))
    plan = client.post("/plan", json={"household": household_json}).json()
    assert plan["recommender"]["status"]["connected"] is False
    assert "spending reserve" in plan["recommender"]["status"]["reason"]
    assert plan["planner_label"] == "Search planner (model not connected)" and plan["settings"]["strategies_searched"] == 1008


def test_a_recommender_that_fails_is_reported_and_the_full_search_runs(household_json, models_dir):
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.BadOptionRecommender()))
    plan = client.post("/plan", json={"household": household_json}).json()
    assert plan["planner_label"] == "Search planner (model not connected)"
    assert plan["recommender"]["status"]["connected"] is False
    assert "invalid Recommendation" in plan["recommender"]["status"]["reason"]
    assert plan["settings"]["strategies_searched"] == 1008
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.RaisingRecommender()))
    again = client.post("/plan", json={"household": household_json}).json()
    assert "model blew up" in again["recommender"]["status"]["reason"]


# --- Year detail ----------------------------------------------------------------------------


def test_year_detail_returns_decisions_values_and_the_tax_return(household_json, plan):
    choices = plan["strategy"]["choices"]
    r = client.post("/plan/year-detail", json={"household": household_json, "choices": choices, "year_index": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["age"] == 48 and body["year_index"] == 10
    keys = [d["key"] for d in body["decisions"]]
    assert "location" in keys and keys[-1] == "stock_share"
    assert all(d["value"] is not None for d in body["decisions"] if d["valued"])
    assert body["tax_return"]["grand_total"] == pytest.approx(plan["rows"][10]["total_tax"])
    assert body["tax_lines"][0]["label"].startswith("Wages")


def test_year_detail_validates_its_input(household_json, plan):
    choices = plan["strategy"]["choices"]
    assert client.post("/plan/year-detail", json={"household": household_json, "choices": {"stock_share": "90"}, "year_index": 1}).status_code == 422
    bad = {**choices, "conversion": "fill99"}
    assert client.post("/plan/year-detail", json={"household": household_json, "choices": bad, "year_index": 1}).status_code == 422
    assert client.post("/plan/year-detail", json={"household": household_json, "choices": choices, "year_index": -1}).status_code == 422


# --- What-if --------------------------------------------------------------------------------


def whatif(household_json, **kw):
    return client.post("/plan/whatif", json={"household": household_json, **kw})


def test_whatif_home_purchase_next_year(household_json, plan):
    r = whatif(household_json, presets=["home_next_year"])
    assert r.status_code == 200
    body = r.json()
    assert body["changes"] == [{"field": "home_purchase_in_years", "label": "Home purchase", "before": "in 3 years", "after": "in 1 year"}]
    rows = body["plan"]["rows"]
    assert rows[1]["goal_paid"] == 120_000 and rows[3]["goal_paid"] == 0
    assert rows[1]["goal_label"] == "Home purchase" and rows[3]["goal_label"] is None
    assert body["household"]["goals"]["home_purchase_in_years"] == 1


def test_whatif_spouse_income_cut(household_json):
    body = whatif(household_json, presets=["spouse_b_income_cut"]).json()
    assert body["household"]["people"][1]["wages"] == pytest.approx(88_000)
    assert body["changes"][0]["before"] == "$110,000" and body["changes"][0]["after"] == "$88,000"
    assert body["plan"]["rows"][0]["wages"] == pytest.approx(228_000)


def test_whatif_retire_at_57_and_market_drop(household_json, plan):
    early = whatif(household_json, presets=["retire_57"]).json()
    assert early["household"]["goals"]["retirement_age"] == 57
    assert early["plan"]["rows"][19]["wages"] == 0 and early["plan"]["rows"][18]["wages"] > 0  # age 57 retired
    assert early["plan"]["stats"]["typical_outcome"]["median"] < plan["stats"]["typical_outcome"]["median"]
    drop = whatif(household_json, presets=["market_drop_30"]).json()
    assert drop["shock"] == {"year": 1, "equity_return": -0.30}
    assert drop["plan"]["settings"]["market_shock"]["equity_return"] == -0.30
    assert drop["plan"]["stats"]["typical_outcome"]["median"] < plan["stats"]["typical_outcome"]["median"]
    assert drop["changes"][0]["after"] == "down 30% next year"


def test_whatif_edits_and_stacked_presets(household_json):
    body = whatif(
        household_json,
        presets=["home_next_year", "market_drop_30"],
        edits={"retirement_spending": 90_000, "remove_college": True},
    ).json()
    fields = [c["field"] for c in body["changes"]]
    assert fields == ["home_purchase_in_years", "market_shock", "retirement_spending", "college_starts_in_years"]
    assert body["household"]["goals"]["college_starts_in_years"] is None
    assert sum(r["goal_paid"] for r in body["plan"]["rows"]) == 120_000
    kept = whatif(household_json, edits={"retirement_age": 60}, shock={"year": 1, "equity_return": -0.30}).json()
    assert kept["shock"]["equity_return"] == -0.30  # an earlier shock is preserved


def test_whatif_rejects_impossible_scenarios(household_json):
    old = make_demo_household(people=[
        make_demo_household().people[0].model_copy(update={"age": 58}),
        make_demo_household().people[1],
    ]).model_dump(mode="json")
    assert whatif(old, presets=["retire_57"]).status_code == 422
    single = make_demo_household(people=[make_demo_household().people[0]]).model_dump(mode="json")
    assert whatif(single, presets=["spouse_b_income_cut"]).status_code == 422
    assert whatif(household_json, edits={"retirement_age": 38}).status_code == 422
    assert whatif(household_json, presets=["teleport"]).status_code == 422


def test_whatif_uses_the_same_futures_so_changes_are_the_scenario(household_json, plan):
    nothing = whatif(household_json).json()
    assert nothing["changes"] == []
    for key in ("typical_outcome", "ria_typical_outcome"):
        assert nothing["plan"]["stats"][key] == plan["stats"][key]


def test_whatif_merges_a_preset_and_an_edit_to_the_same_field(household_json):
    body = whatif(household_json, presets=["retire_57"], edits={"retirement_age": 58}).json()
    assert body["changes"] == [{"field": "retirement_age", "label": "Retirement age", "before": "62", "after": "58"}]
    assert body["household"]["goals"]["retirement_age"] == 58


def test_whatif_drops_a_change_that_nets_to_nothing(household_json):
    body = whatif(household_json, presets=["retire_57"], edits={"retirement_age": 62}).json()
    assert body["changes"] == []
    assert body["household"]["goals"]["retirement_age"] == 62


def test_without_a_tax_form_the_missing_values_are_named_and_the_tax_picture_is_an_estimate(sample_docs):
    ids = [SAMPLE_IDS["brokerage_statement"], SAMPLE_IDS["retirement_401k"]]
    response = client.post("/household", json={"document_ids": ids})
    assert response.status_code == 422
    missing = {m["key"]: m["label"] for m in response.json()["detail"]["missing"]}
    assert missing == {"taxpayer_age": "Taxpayer age", "w2_wages_taxpayer": "Taxpayer W-2 wages (box 1)"}

    typed = {"taxpayer_age": 38, "spouse_age": 37, "w2_wages_taxpayer": 115_500, "w2_wages_spouse": 85_500}
    profile = client.post("/household", json={"document_ids": ids, "overrides": typed}).json()
    assert profile["tax_estimated"] is True
    assert [p["wages"] for p in profile["household"]["people"]] == [140_000, 110_000]
    assert profile["household"]["snapshot"] is None
    assert profile["tax_return"]["agi"] > 150_000  # estimated from wages and balances, not zero
    assert profile["tax_return"]["grand_total"] > 0


def test_a_tax_form_makes_the_tax_picture_reported_not_estimated(profile):
    assert profile["tax_estimated"] is False


def test_starting_the_app_warms_the_simulation_kernels(monkeypatch):
    """The first plan after a cold start must not pay for compilation: the app warms up before serving."""
    from app import warmup

    calls = []
    monkeypatch.setattr(warmup, "warm", lambda *a, **k: calls.append(1) or 0.0)
    with TestClient(app) as started:
        assert started.get("/health").json() == {"status": "ok"}
    assert calls == [1]


# --- Both advisors and both measures (spec A7, A9) ------------------------------------------


def test_the_plan_is_measured_against_both_advisors_with_their_definitions(plan):
    baselines = plan["baselines"]
    assert [b["key"] for b in baselines] == ["good_ria", "typical_advisor"]
    assert [b["label"] for b in baselines] == ["Good RIA", "Typical advisor"]
    assert "breakpoint fees" in baselines[0]["definition"]
    assert "flat 1.0% fee" in baselines[1]["definition"] and "no tax-loss harvesting" in baselines[1]["definition"]
    for b in baselines:
        assert b["fan"]["ages"][0] == 38 and b["fan"]["ages"][-1] == HORIZON_AGE
        assert b["fan"]["p50"][-1] == pytest.approx(b["outcome"]["median"])
        assert 0.0 <= b["shortfall_chance"] <= 1.0 and b["lifetime_taxes"] > 0
    assert plan["ria_fan"] == baselines[0]["fan"] and plan["ria"]["outcome"] == baselines[0]["outcome"]
    # the typical advisor is the weaker baseline: more fee, no harvesting
    assert baselines[1]["outcome"]["median"] < baselines[0]["outcome"]["median"]
    assert baselines[1]["advantage"]["median"] > baselines[0]["advantage"]["median"]


def test_each_advantage_is_reported_two_ways_and_annualized_consistently(plan):
    years = plan["stats"]["years"]
    plan_outcome = plan["strategy"]["outcome"]
    for b in plan["baselines"]:
        adv = b["advantage"]
        assert adv["median"] == pytest.approx((plan_outcome["median"] / b["outcome"]["median"]) ** (1 / years) - 1)
        assert adv["risk_adjusted"] == pytest.approx((plan_outcome["score"] / b["outcome"]["score"]) ** (1 / years) - 1)
        assert adv["median_dollars"] == pytest.approx(plan_outcome["median"] - b["outcome"]["median"])
        assert adv["risk_adjusted_dollars"] == pytest.approx(plan_outcome["score"] - b["outcome"]["score"])
        assert adv["median_low"] <= adv["median"] <= adv["median_high"]
        assert adv["risk_adjusted_low"] <= adv["risk_adjusted"] <= adv["risk_adjusted_high"]
    assert plan["stats"]["advantage"] == plan["baselines"][0]["advantage"]  # the stat cards use the good RIA


def test_results_are_measured_on_futures_the_search_never_saw(plan):
    s = plan["settings"]
    assert s["eval_seed"] != s["seed"] and s["n_eval_paths"] == 200 and s["n_paths"] == 400
    chosen_in_search = next(r for r in plan["searched"] if r["is_chosen"])
    # the search table is scored on the search futures, the outcome cards on the held-out ones
    assert chosen_in_search["median"] != plan["strategy"]["outcome"]["median"]
    assert chosen_in_search["median"] == pytest.approx(plan["strategy"]["outcome"]["median"], rel=0.35)


def test_risk_aversion_is_a_request_parameter(household_json):
    def run(ra):
        r = client.post("/plan", json={"household": household_json, "risk_aversion": ra})
        assert r.status_code == 200, r.text
        return r.json()

    low, high = run(1.5), run(8.0)
    assert low["settings"]["risk_aversion"] == 1.5 and high["settings"]["risk_aversion"] == 8.0
    assert low["strategy"]["outcome"]["score"] != high["strategy"]["outcome"]["score"]
    # a more risk-averse household is steered to a safer portfolio
    assert int(high["strategy"]["choices"]["stock_share"]) <= int(low["strategy"]["choices"]["stock_share"])
    assert client.post("/plan", json={"household": household_json, "risk_aversion": 0.0}).status_code == 422


def test_demo_mode_results_are_identical_across_runs(household_json):
    a = client.post("/plan", json={"household": household_json}).json()
    b = client.post("/plan", json={"household": household_json}).json()
    a["settings"].pop("elapsed_seconds"), b["settings"].pop("elapsed_seconds")
    assert a == b


# --- The adaptive plan (spec part B) ------------------------------------------------------------

SMALL = {"n_eval_paths": 60, "adaptive_rollouts": 8}


def _adaptive(household_json, **extra):
    from app.planner import adaptive_service

    r = client.post("/plan", json={"household": household_json, **SMALL, **extra})
    assert r.status_code == 200, r.text
    body = r.json()
    if body["adaptive"] is not None:
        return body, body["adaptive"]
    job = adaptive_service.service.wait(body["adaptive_job"], timeout=300)
    assert job.status == "done", job.error
    return body, job.result.model_dump()


def test_the_fixed_plan_returns_at_once_and_the_adaptive_plan_follows_in_the_background(household_json):
    from app.planner import adaptive_service

    adaptive_service.service.clear()
    start = time.perf_counter()
    r = client.post("/plan", json={"household": household_json, **SMALL, "seed": 77, "demo_mode": False})
    assert r.status_code == 200 and time.perf_counter() - start < 3.0
    body = r.json()
    assert body["adaptive"] is None and body["adaptive_job"]  # not ready yet, but a job is computing it
    job = client.get(f"/plan/adaptive/{body['adaptive_job']}").json()
    assert job["status"] in ("running", "done") and 0.0 <= job["progress"] <= 1.0
    done = adaptive_service.service.wait(body["adaptive_job"], timeout=300)
    assert done.status == "done" and done.progress == 1.0 and done.result is not None
    assert client.get("/plan/adaptive/nonexistent").status_code == 404


def test_a_plan_can_skip_the_adaptive_planner(household_json):
    r = client.post("/plan", json={"household": household_json, "adaptive": False}).json()
    assert r["adaptive"] is None and r["adaptive_job"] is None


def test_the_adaptive_section_compares_four_strategies_on_the_same_futures(household_json):
    body, a = _adaptive(household_json)
    keys = [s["key"] for s in a["strategies"]]
    assert keys == ["typical_advisor", "good_ria", "best_fixed", "adaptive"]
    assert a["n_eval_paths"] == 60 and a["k"] == 8 and a["z_min"] == 1.0
    by = {s["key"]: s for s in a["strategies"]}
    for s in a["strategies"]:
        assert s["fan"]["ages"][-1] == HORIZON_AGE and s["fan"]["p50"][-1] == pytest.approx(s["outcome"]["median"])
        assert 0 <= s["shortfall_chance"] <= 1 and s["lifetime_taxes"] > 0
        for adv in (s["advantage_vs_typical"], s["advantage_vs_ria"]):
            assert adv["median_low"] <= adv["median"] <= adv["median_high"]
    # the best fixed strategy here is the plan's own; the baselines are the same ones the Compare screen shows
    plan_outcome = body["strategy"]["outcome"]
    assert by["best_fixed"]["outcome"]["median"] != plan_outcome["median"] or a["n_eval_paths"] == body["settings"]["n_eval_paths"]
    ria = next(b for b in body["baselines"] if b["key"] == "good_ria")
    assert by["best_fixed"]["advantage_vs_ria"]["median"] == pytest.approx(ria["advantage"]["median"])
    assert by["good_ria"]["outcome"]["median"] == pytest.approx(ria["outcome"]["median"])
    assert by["typical_advisor"]["advantage_vs_typical"]["median"] == pytest.approx(0.0)
    # the value of judgment over time is the adaptive plan against the best fixed strategy
    v = a["value_of_judgment"]
    assert v["median_dollars"] == pytest.approx(by["adaptive"]["outcome"]["median"] - by["best_fixed"]["outcome"]["median"])
    assert v["risk_adjusted_dollars"] == pytest.approx(by["adaptive"]["outcome"]["score"] - by["best_fixed"]["outcome"]["score"])


def test_the_adaptive_plan_table_marks_the_years_it_departs_from_the_fixed_strategy(household_json):
    _, a = _adaptive(household_json)
    rows, decisions = a["rows"], a["decisions"]
    assert [r["age"] for r in rows] == list(range(38, HORIZON_AGE)) == [d["age"] for d in decisions]
    # every year has its full tax return (for the year detail panel) and agrees with the table
    details = a["year_details"]
    assert [x["age"] for x in details] == [r["age"] for r in rows]
    for row, detail in zip(rows, details, strict=True):
        assert detail["wealth_at_year_end"] == pytest.approx(row["wealth"]) and detail["tax_lines"] and detail["tax_return"]["grand_total"] >= 0
        assert detail["decisions"] and all(not x["valued"] for x in detail["decisions"])
    for row, d in zip(rows, decisions, strict=True):
        assert row["departs"] == d["departs"] == bool(d["departures"])
        assert d["why"] and d["candidates_scored"] >= 1 and len(d["alternatives"]) <= 2
        assert d["ce_chosen"] >= d["ce_fixed"] - 1e-6  # never worse than the fixed action in the rollouts
        assert all(alt["ce_gap"] == pytest.approx(d["ce_chosen"] - alt["ce"]) for alt in d["alternatives"])
        assert all(alt["differs_in"] for alt in d["alternatives"])
    assert any(d["departs"] for d in decisions) and not all(d["departs"] for d in decisions)
    assert 0 < a["departure_share"] < 1 and set(a["departure_by_decision"]) == {
        "conversion", "realize_gains", "goal_funding", "k401", "private_credit", "stock_share"
    }
    # a year that departs says what it did and why, from computed numbers
    departing = next(d for d in decisions if d["departs"])
    assert "The rollouts scored this" in departing["why"] and departing["facts"]["market_return"] == pytest.approx(0.055)
    steady = next(d for d in decisions if not d["departs"])
    assert steady["why"].startswith("No change from the fixed strategy")


def test_the_market_drop_preset_visibly_changes_the_plan_and_the_decisions_after_it(household_json):
    """A 30% fall next year changes the recommended plan and the year-by-year plan; the planner sees the fall in its year.
    (The balanced style: its search answers a fall by holding the home purchase's money in goal bonds.)"""
    from app.planner import adaptive_service

    adaptive_service.service.clear()
    calm_body = client.post("/plan", json={"household": household_json, "planning_style": "balanced"}).json()
    calm = calm_body["adaptive"] or adaptive_service.service.wait(calm_body["adaptive_job"], timeout=600).result.model_dump()
    r = client.post("/plan/whatif", json={"household": household_json, "presets": ["market_drop_30"], "planning_style": "balanced"})
    assert r.status_code == 200, r.text
    whatif = r.json()
    body = whatif["plan"]
    assert whatif["shock"]["year"] == 1 and whatif["shock"]["equity_return"] == pytest.approx(-0.30)
    assert body["adaptive"] is None and body["adaptive_job"]  # the fast plan is here; the year-by-year plan is refining
    job = adaptive_service.service.wait(body["adaptive_job"], timeout=600)
    assert job.status == "done"
    shocked = job.result.model_dump()
    # the planner sees the fall in the year it happens, and the balances are lower from then on
    year1 = shocked["decisions"][1]
    assert year1["facts"]["market_return"] == pytest.approx(-0.30) and calm["decisions"][1]["facts"]["market_return"] == pytest.approx(0.055)
    assert shocked["rows"][1]["wealth"] < 0.95 * calm["rows"][1]["wealth"]
    # what the fixed search recommends changes: after the fall it holds the home purchase's money in bonds
    assert calm_body["strategy"]["choices"] != body["strategy"]["choices"]
    assert body["strategy"]["choices"]["goal_bonds"] == "on" and calm_body["strategy"]["choices"]["goal_bonds"] == "off"
    # and the year-by-year plan changes with it: money moves into the goal bond bucket ahead of the home purchase
    assert max(r["goal_bonds_balance"] for r in calm["rows"]) == 0.0 < max(r["goal_bonds_balance"] for r in shocked["rows"])
    assert any(r["goal_bonds_flow"] > 0 for r in shocked["rows"][:3])
    # how often the planner changes things is reported by year, for both plans (the fall itself does not move it much:
    # with returns that do not mean-revert a lower balance does not change what is worth doing)
    for section in (calm, shocked):
        assert len(section["departure_by_year"]) == len(section["rows"]) and all(0 <= x <= 1 for x in section["departure_by_year"])
        assert set(section["departure_by_year_and_decision"]) == set(section["departure_by_decision"])
    assert [d["age"] for d in shocked["year_details"]] == [r["age"] for r in shocked["rows"]]


def test_demo_mode_adaptive_results_are_identical_across_runs(household_json):
    from app.planner import adaptive_service

    adaptive_service.service.clear()
    _, first = _adaptive(household_json)
    adaptive_service.service.clear()
    _, second = _adaptive(household_json)
    for a in (first, second):
        a.pop("elapsed_seconds"), a.pop("seconds_per_path"), a.pop("from_cache")
    assert first == second  # same seed, same plan, to the last digit


def test_a_repeat_request_is_served_from_the_cache(household_json):
    from app.planner import adaptive_service

    adaptive_service.service.clear()
    _adaptive(household_json)
    r = client.post("/plan", json={"household": household_json, **SMALL}).json()
    assert r["adaptive"] is not None and r["adaptive"]["from_cache"] is True and r["adaptive_job"] is None
    other = client.post("/plan", json={"household": household_json, **SMALL, "risk_aversion": 5.0}).json()
    assert other["adaptive"] is None and other["adaptive_job"]  # different settings: not a hit


def test_an_adaptive_job_can_be_cancelled_over_the_api():
    import threading

    from app.planner import adaptive_service

    gate = threading.Event()

    def slow(progress):
        gate.wait(10.0)
        progress(0.5)  # a cancelled job stops here
        raise AssertionError("a cancelled job must not run on")

    _, job_id = adaptive_service.service.request("cancel-me", slow)
    assert client.delete("/plan/adaptive/nonexistent").status_code == 404
    response = client.delete(f"/plan/adaptive/{job_id}")
    assert response.status_code == 204 and response.content == b""
    gate.set()
    done = adaptive_service.service.wait(job_id, timeout=10.0)
    assert done.status == "cancelled"
    assert client.get(f"/plan/adaptive/{job_id}").json()["status"] == "cancelled"


def test_a_failing_adaptive_job_is_reported_not_swallowed():
    from app.planner import adaptive_service

    def broken(progress):
        raise RuntimeError("kernel exploded")

    _, job_id = adaptive_service.service.request("broken-key", broken)
    done = adaptive_service.service.wait(job_id)
    assert done.status == "error" and "kernel exploded" in done.error and done.result is None


# --- Demo mode: the adaptive plan is precomputed -------------------------------------------------


def test_the_demo_households_adaptive_plan_is_precomputed_and_the_plan_screen_gets_it_at_once(profile, monkeypatch):
    """What the app does at startup: plan the household the sample documents make, in the background, so the
    Plan screen finds the finished year-by-year plan when it asks."""
    from app import warmup
    from app.planner import adaptive_service

    monkeypatch.delenv("DONABACH_NO_PRECOMPUTE", raising=False)
    adaptive_service.service.clear()
    warmup.precompute_demo()
    jobs = [j for j in adaptive_service.service._jobs.values()]
    assert len(jobs) == 1  # one job, started by the precompute
    done = adaptive_service.service.wait(jobs[0].id, timeout=600)
    assert done.status == "done"
    # the Plan screen's own request for that household, with the app's defaults, is a cache hit
    start = time.perf_counter()
    response = client.post("/plan", json={"household": profile["household"]})
    body = response.json()
    assert response.status_code == 200 and body["adaptive"] is not None and body["adaptive_job"] is None
    assert body["adaptive"]["from_cache"] is True and time.perf_counter() - start < 3.0
    assert body["adaptive"]["n_eval_paths"] == 200 and body["adaptive"]["k"] == 32
    # and nothing is precomputed when it is switched off
    adaptive_service.service.clear()
    monkeypatch.setenv("DONABACH_NO_PRECOMPUTE", "1")
    warmup.precompute_demo()
    assert not adaptive_service.service._jobs
