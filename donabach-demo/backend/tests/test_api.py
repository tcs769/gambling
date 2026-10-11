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
    for model in ("recommender", "forecaster"):
        assert status[model]["connected"] is False and "No model file" in status[model]["reason"]


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
    assert plan["settings"]["strategies_searched"] == 224 and len(plan["searched"]) == 224
    assert plan["settings"]["risk_aversion"] == 3.0 and plan["settings"]["wealth_floor"] == 50_000
    assert plan["searched"][0]["is_chosen"] and plan["searched"][0]["rank"] == 1


def test_plan_contents_are_consistent(plan):
    s, st = plan["strategy"], plan["stats"]
    assert set(s["choices"]) == {"stock_share", "conversion", "private_credit", "direct_indexing", "goal_bonds"}
    assert s["sentence"].endswith(".") and "Hold" in s["sentence"] and plan["reason"]
    assert st["typical_outcome"] == s["outcome"] and st["years"] == 32
    assert st["advantage_total"] == pytest.approx(st["typical_outcome"]["median"] - st["ria_typical_outcome"]["median"])
    assert st["advantage_per_year"] == pytest.approx(st["advantage_total"] / 32)
    assert sum(a["delta_median"] for a in plan["advantage"]) == pytest.approx(st["advantage_total"], rel=1e-9)
    assert [a["label"] for a in plan["advantage"]][0] == "Lower fee"
    fan = plan["fan"]
    assert fan["ages"][0] == 38 and fan["ages"][-1] == 70 and len(fan["p50"]) == 33
    assert fan["p50"][-1] == pytest.approx(st["typical_outcome"]["median"])
    assert plan["ria_fan"]["p50"][-1] == pytest.approx(st["ria_typical_outcome"]["median"])
    assert fan["p50"][0] == plan["ria_fan"]["p50"][0]  # both start from today's wealth


def test_plan_table_has_every_year_and_ties_out(plan):
    rows = plan["rows"]
    assert [r["age"] for r in rows] == list(range(38, 70))
    assert rows[0]["wages"] == 250_000 and rows[-1]["wages"] == 0
    assert rows[3]["goal_paid"] == 120_000 and sum(r["goal_paid"] for r in rows) == 260_000
    labels = {r["age"]: r["goal_label"] for r in rows if r["goal_paid"] > 0}
    assert labels == {41: "Home purchase", 48: "College", 49: "College", 50: "College", 51: "College"}
    assert all(r["goal_label"] is None for r in rows if r["goal_paid"] == 0)
    assert all(r["total_tax"] == pytest.approx(r["federal_tax"] + r["illinois_tax"]) for r in rows)
    assert all(0.4 < r["stock_share"] < 1.0 for r in rows)
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


def test_a_recommender_that_fails_is_reported_and_the_full_search_runs(household_json, models_dir):
    (models_dir / "recommender.pkl").write_bytes(pickle.dumps(stubs.BadOptionRecommender()))
    plan = client.post("/plan", json={"household": household_json}).json()
    assert plan["planner_label"] == "Search planner (model not connected)"
    assert plan["recommender"]["status"]["connected"] is False
    assert "invalid Recommendation" in plan["recommender"]["status"]["reason"]
    assert plan["settings"]["strategies_searched"] == 224
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
