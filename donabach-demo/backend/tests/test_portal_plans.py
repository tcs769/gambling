"""The portal's plans: every figure agrees with every other figure that shows it, for the base plan and for each precomputed change.

The household is John Smith's (`fixtures/showcase.json`). Each test runs over the base plan and the six presets, so a number that is
computed twice and disagrees fails here. Nothing is adjusted to make a check pass: a failure is a defect in how the figure is built.
"""

from __future__ import annotations

import re

import pytest
from app.portal import engine_view as E
from app.portal import presets
from fastapi.testclient import TestClient

TOTAL = 1_860_000  # John Smith's total savings, to the dollar (the deck's figure)


@pytest.fixture(scope="module")
def plans():
    E.reset()
    ids = presets.precompute()
    return {key: E.lookup(pid) for key, pid in ids.items()}


KEYS = ["base", *[p.key for p in presets.PRESETS]]


@pytest.fixture(params=KEYS)
def plan(request, plans):
    return plans[request.param]


def test_the_base_plan_has_the_figures_the_demo_quotes(plans):
    base = plans["base"]
    s = base.portfolio.summary
    assert round(s.projected_wealth) == 3_354_464
    assert s.invested_today == TOTAL
    assert round(base.comparison.advisor.wealth_80) == 1_961_675
    assert round(base.comparison.dollars_more) == 1_392_788
    assert base.comparison.rate_per_year == pytest.approx(0.024686, abs=5e-7)
    assert all(h.name != "Direct-indexed US stocks" for a in base.portfolio.holdings.accounts for h in a.holdings)  # the plan holds funds: direct indexing does not pay once its sale tax is charged
    assert s.fee_rate == 0.0035 and round(s.fee_dollars) == 6_510


def test_the_mix_adds_up_to_total_savings_and_each_class_is_the_sum_over_accounts(plan):
    mix, loc = plan.portfolio.overview.mix, plan.portfolio.overview.location
    assert sum(r.amount for r in mix.rows) == mix.total
    assert round(mix.total) == round(plan.household.liquid_wealth)
    assert plan.household.liquid_wealth > 0
    for row, cells in zip(mix.rows, loc.rows, strict=True):
        assert row.key == cells.key
        assert row.amount == cells.brokerage + cells.pretax + cells.roth == cells.total
    assert loc.total.brokerage == sum(r.brokerage for r in loc.rows)
    assert loc.total.pretax == sum(r.pretax for r in loc.rows)
    assert loc.total.roth == sum(r.roth for r in loc.rows)
    assert loc.total.total == mix.total
    assert sum(r.share for r in mix.rows) == pytest.approx(1.0)


def test_each_accounts_holdings_add_up_to_its_balance_and_the_gains_to_the_unrealized_gain(plan):
    loc = plan.portfolio.overview.location
    balances = {"brokerage": loc.total.brokerage, "pretax": loc.total.pretax, "roth": loc.total.roth}
    for account in plan.portfolio.holdings.accounts:
        assert account.balance == balances[account.key]
        assert sum(h.value for h in account.holdings) == account.balance
        assert sum(h.share for h in account.holdings) == pytest.approx(1.0 if account.balance else 0.0)
    brokerage = next(a for a in plan.portfolio.holdings.accounts if a.key == "brokerage")
    stocks = [h for h in brokerage.holdings if h.gain is not None]
    assert sum(h.gain for h in stocks) == brokerage.unrealized_gain
    assert sum(h.value for h in stocks) - brokerage.cost_basis == brokerage.unrealized_gain


def test_the_stock_split_by_sector_and_region_adds_up_to_the_stocks_held(plan):
    mix = {r.key: r.amount for r in plan.portfolio.overview.mix.rows}
    stocks = mix["us_stocks"] + mix["intl_stocks"]
    for bars in (plan.portfolio.holdings.sectors, plan.portfolio.holdings.regions):
        assert sum(b.share for b in bars) == pytest.approx(1.0)
        assert abs(sum(b.amount for b in bars) - stocks) <= len(bars)  # whole dollars


def test_the_fee_is_the_rate_times_the_managed_balances_on_the_strip_and_the_comparison(plan):
    s = plan.portfolio.summary
    assert s.fee_dollars == pytest.approx(s.fee_rate * plan.household.liquid_wealth, abs=0.01)
    assert plan.comparison.waramoug.fee_dollars == s.fee_dollars
    assert plan.comparison.waramoug.fee_rate == s.fee_rate
    adv = plan.comparison.advisor
    assert adv.fee_rate == pytest.approx(adv.fee_dollars / plan.household.liquid_wealth)


def test_tax_saved_is_one_number(plan):
    assert plan.portfolio.summary.tax_saved == plan.portfolio.taxes.this_year.tax_saved


def test_losses_harvested_are_gains_offset_plus_the_deduction_plus_what_is_carried_forward(plan):
    t = plan.portfolio.taxes.this_year
    assert t.losses_harvested == pytest.approx(t.gains_offset + t.deducted_from_income + t.carried_forward, abs=0.01)


def test_the_roth_conversion_and_its_tax_agree_everywhere(plan):
    t = plan.portfolio.taxes
    moves = {m.key: m for m in plan.portfolio.overview.moves}
    rows = t.conversions
    conv = t.this_year.roth_conversion
    assert plan.comparison.waramoug.roth_conversion == conv
    if conv > 0:
        assert moves["conversion"].amount == conv
        assert moves["conversion"].detail == f"Tax ${t.this_year.conversion_tax:,.0f}"
        assert rows[0].amount == conv and rows[0].tax == t.this_year.conversion_tax and rows[0].age == plan.portfolio.summary.age
        assert t.bracket.conversion == conv
        if "conversion_next" in moves:
            assert moves["conversion_next"].amount == rows[1].amount
            assert moves["conversion_next"].detail == f"Tax ${rows[1].tax:,.0f}"
    else:
        assert "conversion" not in moves and (not rows or rows[0].age > plan.portfolio.summary.age)


def test_the_bracket_numbers_agree(plan):
    b = plan.portfolio.taxes.bracket
    assert b.taxable_before + b.conversion == pytest.approx(b.fills_to, abs=0.01)
    filled = [s for s in b.brackets if s.filled]
    assert len(filled) == 1 and filled[0].rate == b.marginal_rate
    if b.conversion > 0:
        s = filled[0]
        assert s.floor - 1e-6 <= b.fills_to <= (s.ceiling if s.ceiling is not None else float("inf")) + 1e-6


def test_the_comparison_uses_the_same_wealth_as_the_projection_and_the_strip(plan):
    c, s = plan.comparison, plan.portfolio.summary
    projection = plan.portfolio.overview.projection
    assert projection[-1].age == s.horizon_age
    assert projection[-1].wealth == s.projected_wealth == c.waramoug.wealth_80
    assert c.dollars_more == c.waramoug.wealth_80 - c.advisor.wealth_80
    years = s.horizon_age - s.age
    assert c.rate_per_year == pytest.approx((c.waramoug.wealth_80 / c.advisor.wealth_80) ** (1 / years) - 1, abs=1e-12)
    assert max(c.advisor.bar, c.waramoug.bar) == 1.0
    for card in (c.advisor, c.waramoug):
        assert sum(m.share for m in card.mix) == pytest.approx(1.0)
    assert [m.share for m in c.waramoug.mix] == [r.share for r in plan.portfolio.overview.mix.rows]


def test_retirement_income_sources_equal_spending_plus_tax(plan):
    rows = plan.portfolio.retirement.rows
    assert rows
    for r in rows:
        assert r.total_sources == pytest.approx(r.social_security + r.from_pretax + r.from_taxable + r.from_roth)
        assert r.total_uses == pytest.approx(r.spending + r.tax)
        assert abs(r.total_sources - r.total_uses) <= 1.0, f"age {r.age}: sources {r.total_sources:,.2f} vs uses {r.total_uses:,.2f}"


def test_goal_cards_come_from_the_household(plan):
    g = plan.household.goals
    cards = {c.key: c for c in plan.portfolio.goals.cards}
    assert cards["retirement"].target == g.retirement_spending
    assert cards["emergency"].target == g.retirement_spending / 2
    assert cards["retirement"].label == f"Retire at {g.retirement_age}"
    moves = {m.key: m for m in plan.portfolio.overview.moves}
    assert moves["k401"].status == "your_step" and moves["k401"].amount == 24_500  # the engine's contribution against the $0 on the return
    for card in plan.comparison.advisor, plan.comparison.waramoug:
        assert sum(int(p.split("%")[0]) for p in card.mix_text.split(", ")) == 100
    assert ("college" in cards) == (g.college_starts_in_years is not None and g.college_annual_cost > 0)
    assert ("home" in cards) == (g.home_purchase_in_years is not None)
    for c in cards.values():
        assert 0.0 <= c.progress <= 1.0


# --- what changed -----------------------------------------------------------------------------------------------------


def test_what_changed_is_shown_against_the_previous_plan_with_its_own_numbers(plans):
    base = plans["base"]
    assert base.what_changed is None
    for key in KEYS[1:]:
        p = plans[key]
        w = p.what_changed
        assert w is not None and w.changed.strip()
        assert w.wealth_before == base.portfolio.summary.projected_wealth
        assert w.wealth_after == p.portfolio.summary.projected_wealth
        for m in w.mix:
            before = next(r.share for r in base.portfolio.overview.mix.rows if r.key == m.key)
            after = next(r.share for r in p.portfolio.overview.mix.rows if r.key == m.key)
            assert (m.before, m.after) == (before, after)


def test_job_loss_changes_the_conversion_at_59(plans):
    w = plans["job_loss"].what_changed
    assert w.conversion_age == 59
    assert round(w.conversion_before) == 156_515 and round(w.conversion_after) == 430_518
    added = {m.title: m for m in w.moves}
    assert added["Roth conversion at 59"].after.endswith("Needs your OK")
    assert plans["job_loss"].event == "job_loss"
    # the household itself is unchanged; the event is applied to the simulated futures
    assert plans["job_loss"].household == plans["base"].household


def test_a_raise_and_the_edits_change_the_household_as_asked(plans):
    base = plans["base"].household
    assert plans["raise"].household.people[0].wages == pytest.approx(base.people[0].wages * 1.1, abs=0.01)
    assert plans["retire_65"].household.goals.retirement_age == 65
    assert plans["home_1y"].household.goals.home_purchase_in_years == 1 and plans["home_1y"].household.goals.home_down_payment == 150_000
    assert plans["spending_120k"].household.goals.retirement_spending == 120_000
    assert plans["wages_minus_20"].household.people[0].wages == pytest.approx(base.people[0].wages * 0.8, abs=0.01)


# --- the API -----------------------------------------------------------------------------------------------------------


def test_the_api_serves_precomputed_plans_at_once_and_an_unchanged_household_returns_the_same_plan(plans):
    from app.main import app

    client = TestClient(app)
    base = plans["base"]
    body = {"household": base.household.model_dump(mode="json")}
    first = client.post("/portal/invest", json=body)
    assert first.status_code == 200 and first.json()["plan_id"] == base.plan_id
    again = client.post("/portal/invest", json={**body, "previous_plan_id": base.plan_id})
    assert again.json()["plan_id"] == base.plan_id and again.json()["what_changed"] is None
    job = client.post("/portal/invest", json={**body, "event": "job_loss", "previous_plan_id": base.plan_id, "change_label": "Income: job loss next year"})
    assert job.status_code == 200 and job.json()["plan_id"] == plans["job_loss"].plan_id
    assert job.elapsed.total_seconds() < 1.0
    assert client.get(f"/portal/plan/{base.plan_id}").json()["plan_id"] == base.plan_id
    assert client.get("/portal/plan/nope").status_code == 404
    assert re.fullmatch(r"[0-9a-f]{12}", base.plan_id)


# --- from the documents to the precomputed plans ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


def _household_from(client, document_id, overrides=None, **answers):
    body = client.get("/portal/defaults").json() | answers
    r = client.post("/portal/household", json={"document_id": document_id, "overrides": overrides or {}, "answers": body})
    assert r.status_code == 200, r.text
    return r.json()["household"]


def test_the_sample_documents_and_a_dropped_copy_give_the_precomputed_base_plan_at_once(plans, client):
    from app.docs import smith

    sample = client.post("/portal/documents/sample").json()
    with open(smith.DEFAULT_OUT, "rb") as f:
        dropped = client.post("/portal/documents/upload", files={"file": ("smith_documents.pdf", f.read(), "application/pdf")}).json()
    assert [d["doc_kind"] for d in sample["documents"]] == [d["doc_kind"] for d in dropped["documents"]]
    assert sample["documents"] == dropped["documents"]
    ids = set()
    for doc in (sample, dropped):
        household = _household_from(client, doc["id"])
        r = client.post("/portal/invest", json={"household": household})
        assert r.status_code == 200 and r.elapsed.total_seconds() < 1.0
        ids.add(r.json()["plan_id"])
    assert ids == {plans["base"].plan_id}


def test_changes_made_through_the_review_and_goals_screens_hit_the_precomputed_plans(plans, client):
    sample = client.post("/portal/documents/sample").json()
    base = plans["base"].plan_id
    cases = {
        "retire_65": ({}, {"retirement_age": 65}, "none"),
        "spending_120k": ({}, {"retirement_spending": 120_000.0}, "none"),
        "home_1y": ({}, {"home_purchase_in_years": 1, "home_down_payment": 150_000.0}, "none"),
        "wages_minus_20": ({"w2_wages_taxpayer": 240_000.0}, {}, "none"),
        "job_loss": ({}, {}, "job_loss"),
        "raise": ({}, {}, "raise"),
    }
    for key, (overrides, answers, event) in cases.items():
        household = _household_from(client, sample["id"], overrides, **answers)
        r = client.post("/portal/invest", json={"household": household, "event": event, "previous_plan_id": base})
        assert r.status_code == 200 and r.elapsed.total_seconds() < 1.0, key
        assert r.json()["plan_id"] == plans[key].plan_id, key
        assert r.json()["what_changed"]["changed"] == next(p.label for p in presets.PRESETS if p.key == key)
