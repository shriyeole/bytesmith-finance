"""Tests for M5 (budget rules), M6 (risk & allocation) and M7 (assumptions + plan versions)."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from app.modules.financial_state.schemas import FinancialSummary
from app.modules.planning import allocation as alloc
from app.modules.planning import assumptions as asm
from app.modules.planning import router as planning_router
from app.modules.planning.budget import compare_rules

TODAY = date(2026, 10, 9)
API = "/api/v1"
A = {"Authorization": "Bearer dev:alice"}
B = {"Authorization": "Bearer dev:bob"}
LAKH = 100_000 * 100


def summary(income=100_000_00, essential=40_000_00, discretionary=30_000_00, premiums=0, emi=0, high_cost=0) -> FinancialSummary:
    surplus = income - essential - discretionary - premiums - emi
    return FinancialSummary(
        monthly_income_paise=income, monthly_essential_expenses_paise=essential, monthly_discretionary_expenses_paise=discretionary,
        monthly_insurance_premiums_paise=premiums, monthly_emi_paise=emi, monthly_surplus_paise=surplus,
        monthly_planned_investments_paise=0, monthly_unallocated_paise=surplus, savings_rate_bps=None, total_assets_paise=0,
        liquid_assets_paise=0, emergency_fund_paise=0, total_liabilities_paise=0, high_cost_debt_paise=high_cost,
        net_worth_paise=0, emergency_runway_months=None, debt_to_income_bps=None, health_cover_paise=0, life_cover_paise=0,
        dependents_count=0, notes=[],
    )


# ================================================================ M5
class TestBudgetRules:
    def test_fixed_rules_on_one_household(self):
        # income 1L, needs 40k, wants 30k -> today saves 30k
        r = {x.id: x for x in compare_rules(summary(), goals_need=20_000_00, emergency_monthly=0, high_cost_debt=0).rules}
        assert r["50_30_20"].feasible and r["50_30_20"].wants_cut_paise == 0
        assert r["50_30_20"].plan.savings_paise == 30_000_00          # leftover needs room goes to savings
        assert r["50_25_25"].wants_cut_paise == 5_000_00 and r["50_25_25"].plan.savings_paise == 35_000_00
        assert r["50_20_30"].wants_cut_paise == 10_000_00 and r["50_20_30"].plan.savings_paise == 40_000_00
        assert all(x.coverage_bps == 10000 for x in r.values())        # all cover the 20k need

    def test_recommends_least_lifestyle_change_when_coverage_equal(self):
        c = compare_rules(summary(), goals_need=20_000_00, emergency_monthly=0, high_cost_debt=0)
        assert c.recommended_id == "50_30_20"

    def test_recommends_rule_that_funds_goals(self):
        c = compare_rules(summary(), goals_need=40_000_00, emergency_monthly=0, high_cost_debt=0)
        r = {x.id: x for x in c.rules}
        assert r["50_30_20"].coverage_bps == 7500 and r["50_20_30"].coverage_bps == 10000
        assert r["goal_first"].plan.savings_paise == 40_000_00 and r["goal_first"].plan.wants_paise == 20_000_00
        assert c.recommended_id in ("50_20_30", "goal_first")

    def test_essentials_above_needs_share(self):
        c = compare_rules(summary(essential=60_000_00, discretionary=10_000_00), goals_need=10_000_00, emergency_monthly=0, high_cost_debt=0)
        r = {x.id: x for x in c.rules}
        assert not r["50_30_20"].feasible and r["50_30_20"].needs_over_paise == 10_000_00
        assert r["goal_first"].feasible and c.recommended_id == "goal_first"

    def test_goal_first_short(self):
        # income 1L, needs 70k, wants 20k, goals need 40k -> 10k short even with zero wants
        c = compare_rules(summary(essential=70_000_00, discretionary=20_000_00), goals_need=40_000_00, emergency_monthly=0, high_cost_debt=0)
        gf = next(x for x in c.rules if x.id == "goal_first")
        assert not gf.feasible and gf.plan.wants_paise == 0 and gf.plan.savings_paise == 30_000_00
        assert gf.coverage_bps == 7500 and "₹10,000 a month short" in gf.tradeoff

    def test_safety_need_includes_emergency_and_expensive_debt(self):
        c = compare_rules(summary(), goals_need=0, emergency_monthly=5_000_00, high_cost_debt=1_20_000_00)
        assert c.safety_need_paise == 5_000_00 + 10_000_00

    def test_custom_rule_and_no_income(self):
        c = compare_rules(summary(), goals_need=0, emergency_monthly=0, high_cost_debt=0, selected="custom", custom_savings_bps=3500, custom_wants_bps=2000)
        custom = next(x for x in c.rules if x.id == "custom")
        assert custom.target.savings_paise == 35_000_00 and custom.target.needs_paise == 45_000_00
        assert custom.selected and custom.wants_cut_paise == 10_000_00
        assert compare_rules(summary(income=0, essential=0, discretionary=0), 0, 0, 0).status == "needs_info"


# ================================================================ M6
ANSWERS = {"market_drop": "hold", "priority": "balance", "experience": "funds", "flexibility": "year"}


class TestRisk:
    def test_strictest_constraint_wins(self):
        brave = {"market_drop": "buy_more", "priority": "growth", "experience": "stocks", "flexibility": "yes"}
        r = alloc.risk_profile(brave, "uncertain", 2, "critical", 0, 30)
        assert r.willingness_band == 5 and r.capacity_band == 1 and r.final_band == 1 and r.limiting_factor == "capacity"
        timid = {"market_drop": "sell_all", "priority": "safety", "experience": "none", "flexibility": "no"}
        r = alloc.risk_profile(timid, "stable", 0, "good", 0, 30)
        assert r.capacity_band == 5 and r.final_band == 1 and r.limiting_factor == "willingness"

    def test_unanswered(self):
        assert not alloc.risk_profile(None, "stable", 0, "good", 0, 30).answered

    def test_short_goal_stays_out_of_equity_even_for_aggressive(self):
        g = alloc.goal_ranges("Car", "g1", 18, "aspirational", 5, "yes")
        eq = next(x for x in g.ranges if x.asset_class == "equity")
        assert eq.max_pct <= 10 and g.horizon_band == "short"

    def test_cap_moves_room_to_fixed_income(self):
        g = alloc.goal_ranges("Retire", "g2", 300, "essential", 1, "no")
        eq = next(x for x in g.ranges if x.asset_class == "equity")
        fi = next(x for x in g.ranges if x.asset_class == "fixed_income")
        assert eq.max_pct == 15 and fi.max_pct == 30 + 65   # cap 25 − 10 for essential+fixed date; 80 → 15 moves 65
        assert sum(r.min_pct for r in g.ranges) <= 100 <= sum(r.max_pct for r in g.ranges)

    def test_answer_validation(self):
        with pytest.raises(ValueError):
            alloc.validate_answers({**ANSWERS, "market_drop": "panic"})
        with pytest.raises(ValueError):
            alloc.validate_answers({k: v for k, v in ANSWERS.items() if k != "priority"})


# ================================================================ M7 assumptions
class TestAssumptions:
    def test_overrides_and_fingerprint(self):
        a = asm.effective({"general_inflation_bps": 700, "return_by_horizon_bps": [500, 700, 900, 1000]})
        assert a.general_inflation_bps == 700 and a.return_for_months(30) == 700 and a.version.endswith("+custom")
        assert asm.fingerprint(a) != asm.fingerprint(asm.DEFAULT)
        assert asm.fingerprint(asm.effective({})) == asm.fingerprint(asm.DEFAULT)

    @pytest.mark.parametrize("bad", [{"general_inflation_bps": 9999}, {"return_by_horizon_bps": [1, 2]},
                                     {"tax_rate_bps": 100}, {"life_expectancy_years": True}])
    def test_validation(self, bad):
        with pytest.raises(ValueError):
            asm.validate_overrides(bad)


# ================================================================ API
@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: Settings(environment="test", auth_mode="dev")
    monkeypatch.setattr(planning_router, "_today", lambda: TODAY)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def seed(client, h=A):
    post = lambda path, body: client.post(f"{API}{path}", json=body, headers=h).raise_for_status().json()
    client.put(f"{API}/household", json={"date_of_birth": "1991-10-09", "retirement_age": 60, "employment_type": "salaried", "income_stability": "stable"}, headers=h).raise_for_status()
    inc = post("/incomes", {"name": "Salary", "kind": "salary", "amount_paise": 100_000_00})
    post("/expenses", {"name": "Rent", "category": "housing", "amount_paise": 40_000_00})
    post("/expenses", {"name": "Fun", "category": "dining", "amount_paise": 30_000_00})
    post("/assets", {"name": "Savings", "asset_type": "savings_account", "current_value_paise": 3 * LAKH, "is_emergency_fund": True})
    post("/assets", {"name": "MF", "asset_type": "mutual_fund", "current_value_paise": 6 * LAKH})
    post("/insurance", {"policy_type": "health", "cover_amount_paise": 5 * LAKH, "annual_premium_paise": 0})
    car = post("/goals", {"name": "Car", "goal_type": "car", "target_date": "2029-10-09", "current_cost_paise": 10 * LAKH})
    post("/goals", {"name": "Retirement", "goal_type": "retirement", "saved_paise": 5 * LAKH})
    return inc, car


class TestApi:
    def test_budget_endpoint_and_choice(self, client):
        seed(client)
        b = client.get(f"{API}/plan/budget", headers=A).json()
        assert b["status"] == "ok" and b["income_paise"] == 100_000_00 and len(b["rules"]) == 4
        assert b["current"]["savings_paise"] == 30_000_00 and b["goals_need_paise"] > 0
        res = client.put(f"{API}/plan/budget", json={"rule": "50_20_30"}, headers=A).json()
        assert res["selected_id"] == "50_20_30"
        assert client.put(f"{API}/plan/budget", json={"rule": "custom"}, headers=A).status_code == 422
        res = client.put(f"{API}/plan/budget", json={"rule": "custom", "custom_savings_bps": 4000, "custom_wants_bps": 2000}, headers=A).json()
        assert res["selected_id"] == "custom" and len(res["rules"]) == 5
        assert client.put(f"{API}/plan/budget", json={"custom_savings_bps": 8000, "custom_wants_bps": 3000}, headers=A).status_code == 422
        assert client.put(f"{API}/plan/budget", json={"rule": "60_20_20"}, headers=A).status_code == 422

    def test_allocation_flow_and_flag(self, client):
        seed(client)
        assert len(client.get(f"{API}/plan/risk-questions", headers=A).json()) == 4
        view = client.get(f"{API}/plan/allocation", headers=A).json()
        assert not view["risk"]["answered"] and view["goals"] == [] and "not investment advice" in view["disclaimer"]
        view = client.put(f"{API}/plan/risk-answers", json=ANSWERS, headers=A).json()
        assert view["risk"]["answered"] and view["risk"]["final_band"] >= 1
        assert {g["name"] for g in view["goals"]} == {"Car", "Retirement"}
        mix = {m["asset_class"]: m for m in view["current_mix"]}
        assert mix["equity"]["current_pct"] == pytest.approx(66.7) and mix["cash"]["current_pct"] == pytest.approx(33.3)
        assert client.put(f"{API}/plan/risk-answers", json={"market_drop": "hold"}, headers=A).status_code == 422
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", auth_mode="dev", feature_allocation=False)
        assert client.get(f"{API}/plan/allocation", headers=A).status_code == 404
        assert client.get(f"{API}/features", headers=A).json() == {"allocation": False}

    def test_assumption_overrides_change_numbers(self, client):
        seed(client)
        before = client.get(f"{API}/plan/goals", headers=A).json()
        car_before = next(g for g in before["goals"] if g["name"] == "Car")
        v = client.put(f"{API}/assumptions", json={"general_inflation_bps": 900}, headers=A).json()
        assert v["effective"]["general_inflation_bps"] == 900 and v["overrides"] == {"general_inflation_bps": 900}
        after = client.get(f"{API}/plan/goals", headers=A).json()
        car_after = next(g for g in after["goals"] if g["name"] == "Car")
        assert car_after["future_cost_paise"] > car_before["future_cost_paise"] and car_after["inflation_bps"] == 900
        assert client.put(f"{API}/assumptions", json={"general_inflation_bps": 5000}, headers=A).status_code == 422
        v = client.put(f"{API}/assumptions", json={"general_inflation_bps": None}, headers=A).json()
        assert v["overrides"] == {}
        client.put(f"{API}/assumptions", json={"home_loan_rate_bps": 900}, headers=A)
        assert client.delete(f"{API}/assumptions", headers=A).json()["overrides"] == {}
        assert client.get(f"{API}/assumptions", headers=B).json()["overrides"] == {}

    def test_versions_are_immutable_reproducible_and_diffable(self, client):
        inc, car = seed(client)
        assert client.get(f"{API}/plan/changes", headers=A).status_code == 404
        v1 = client.post(f"{API}/plan/versions", json={"label": "First plan"}, headers=A).json()
        assert v1["number"] == 1 and v1["label"] == "First plan" and v1["monthly_surplus_paise"] == 30_000_00

        # change data after publishing
        client.patch(f"{API}/incomes/{inc['id']}", json={"amount_paise": 120_000_00}, headers=A)
        client.patch(f"{API}/goals/{car['id']}", json={"monthly_contribution_paise": 40_000_00}, headers=A)
        client.post(f"{API}/liabilities", json={"name": "Card", "liability_type": "credit_card", "outstanding_paise": 20_000_00}, headers=A)
        client.put(f"{API}/assumptions", json={"general_inflation_bps": 700}, headers=A)

        # the saved version did not move
        d1 = client.get(f"{API}/plan/versions/{v1['id']}", headers=A).json()
        assert d1["outputs"]["summary"]["monthly_income_paise"] == 100_000_00
        assert d1["inputs"]["incomes"][0]["amount_paise"] == 100_000_00
        # and recomputing it from its own inputs gives exactly its stored outputs
        ver = client.get(f"{API}/plan/versions/{v1['id']}/verify", headers=A).json()
        assert ver == {"reproducible": True, "model_version_matches": True, "differences": []}

        changes = client.get(f"{API}/plan/changes", headers=A).json()
        texts = " ".join(c["text"] for c in changes["input_changes"])
        assert "Salary: amount ₹1,00,000 → ₹1,20,000." in texts and "Added Card." in texts
        assert any("monthly amount" in c["text"] for c in changes["input_changes"])
        assert any("General inflation" in c for c in changes["assumption_changes"])
        income_delta = next(m for m in changes["metric_changes"] if m["metric"] == "Monthly income")
        assert income_delta["delta"] == 20_000_00 and income_delta["improved"] is True
        owed = next(m for m in changes["metric_changes"] if m["metric"] == "Total owed")
        assert owed["delta"] == 20_000_00 and owed["improved"] is False  # more debt is worse
        assert any(g["name"] == "Car" and g["after_status"] == "on_track" for g in changes["goal_changes"])
        assert changes["to_label"] == "Now" and "change" in changes["summary"]

        v2 = client.post(f"{API}/plan/versions", json={}, headers=A).json()
        assert v2["number"] == 2
        between = client.get(f"{API}/plan/changes", params={"from_id": v1["id"], "to_id": v2["id"]}, headers=A).json()
        assert between["to_label"] == "Version 2" and len(between["input_changes"]) == len(changes["input_changes"])
        listing = client.get(f"{API}/plan/versions", headers=A).json()
        assert [x["number"] for x in listing] == [2, 1]
        assert client.get(f"{API}/plan/versions/{v1['id']}", headers=B).status_code == 404
        assert client.get(f"{API}/plan/overview", headers=A).json()["latest_version"] == 2

    def test_tampered_version_fails_verification(self, client):
        seed(client)
        v = client.post(f"{API}/plan/versions", json={}, headers=A).json()
        from app.modules.planning.models import PlanVersion
        db = next(app.dependency_overrides[get_db]())
        row = db.get(PlanVersion, v["id"])
        row.outputs = {**row.outputs, "summary": {**row.outputs["summary"], "net_worth_paise": 1}}
        db.commit()
        res = client.get(f"{API}/plan/versions/{v['id']}/verify", headers=A).json()
        assert res["reproducible"] is False and "summary" in res["differences"]

    def test_delete_account_removes_planning_data(self, client):
        seed(client)
        client.post(f"{API}/plan/versions", json={}, headers=A)
        client.put(f"{API}/assumptions", json={"general_inflation_bps": 700}, headers=A)
        assert client.delete(f"{API}/me", headers=A).status_code == 204
        assert client.get(f"{API}/plan/versions", headers=A).json() == []
        assert client.get(f"{API}/assumptions", headers=A).json()["overrides"] == {}
        assert client.get(f"{API}/goals", headers=A).json() == []
