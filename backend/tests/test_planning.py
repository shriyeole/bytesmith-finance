"""Tests for M4 planning engines and API. 'Today' is pinned to 2026-10-09."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.calc.finance import corpus_for_expenses, emi, future_value, inflate, required_monthly
from app.core.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from app.modules.planning import router as planning_router
from app.modules.planning.assumptions import DEFAULT
from app.modules.planning.goals import GoalInput, PlanContext, add_months, evaluate_goal, months_between, plan_goals

TODAY = date(2026, 10, 9)
API = "/api/v1"
A = {"Authorization": "Bearer dev:alice"}
B = {"Authorization": "Bearer dev:bob"}
LAKH = 100_000 * 100
CRORE = 100 * LAKH


def ctx(**kw) -> PlanContext:
    base = dict(today=TODAY, date_of_birth=date(1991, 10, 9), retirement_age=60, monthly_income_paise=150_000_00,
                monthly_spend_paise=60_000_00, monthly_surplus_paise=50_000_00)
    base.update(kw)
    return PlanContext(**base)


# ---------------------------------------------------------------- date helpers
class TestDates:
    def test_months_between(self):
        assert months_between(date(2026, 10, 9), date(2031, 10, 9)) == 60
        assert months_between(date(2026, 10, 9), date(2031, 10, 8)) == 59
        assert months_between(date(2026, 10, 9), date(2026, 9, 9)) == -1

    def test_add_months_clamps_month_end(self):
        assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
        assert add_months(date(2026, 10, 9), 300) == date(2051, 10, 9)


# ---------------------------------------------------------------- goal engine
class TestGoalEngine:
    def test_car_goal_numbers(self):
        g = GoalInput(name="Car", goal_type="car", priority="aspirational", target_date=date(2029, 10, 9),
                      current_cost_paise=10 * LAKH, saved_paise=2 * LAKH)
        e = evaluate_goal(g, ctx())
        assert e.months_left == 36 and e.inflation_bps == 600 and e.return_bps == 800
        assert e.future_cost_paise == inflate(10 * LAKH, 600, 36)
        assert e.savings_target_paise == e.future_cost_paise
        assert e.required_monthly_paise == required_monthly(e.future_cost_paise, 2 * LAKH, 800, 36)
        assert e.projected_paise == future_value(2 * LAKH, 0, 800, 36)
        assert e.status == "off_track" and e.monthly_gap_paise == e.required_monthly_paise
        assert any("a month" in msg for msg in e.messages)

        on = evaluate_goal(GoalInput(**{**g.__dict__, "monthly_contribution_paise": e.required_monthly_paise}), ctx())
        assert on.status == "on_track" and on.monthly_gap_paise == 0 and on.months_to_reach_at_current <= 36

    def test_at_risk_band(self):
        g = GoalInput(name="Trip", goal_type="travel", priority="aspirational", target_date=date(2027, 10, 9),
                      current_cost_paise=LAKH, inflation_bps=0, expected_return_bps=0, monthly_contribution_paise=7_500_00)
        e = evaluate_goal(g, ctx())  # 12 × 7,500 = 90,000 of 1,00,000 = 90%
        assert e.funded_bps == 9000 and e.status == "at_risk"

    def test_education_uses_education_inflation(self):
        g = GoalInput(name="College", goal_type="child_education", priority="essential",
                      target_date=date(2036, 10, 9), current_cost_paise=20 * LAKH)
        e = evaluate_goal(g, ctx())
        assert e.inflation_bps == 1000 and e.future_cost_paise == inflate(20 * LAKH, 1000, 120)

    def test_home_goal_targets_down_payment_and_checks_emi(self):
        g = GoalInput(name="Flat", goal_type="home", priority="important", target_date=date(2031, 10, 9),
                      current_cost_paise=CRORE)
        e = evaluate_goal(g, ctx())
        price = inflate(CRORE, 600, 60)
        down, extra = price * 2000 // 10000, price * 700 // 10000
        assert e.savings_target_paise == down + extra
        assert e.home_loan.loan_paise == price - down
        assert e.home_loan.emi_paise == emi(price - down, 850, 240)
        assert e.home_loan.affordable is False  # EMI is well above 40% of ₹1.5L
        assert any("stretch" in m for m in e.messages)

    def test_retirement_corpus(self):
        g = GoalInput(name="Retire", goal_type="retirement", priority="essential", saved_paise=10 * LAKH,
                      monthly_contribution_paise=20_000_00)
        e = evaluate_goal(g, ctx())
        assert e.months_left == 300 and e.target_date == date(2051, 10, 9)
        spend_then = inflate(60_000_00, 600, 300)
        assert e.retirement.monthly_spend_at_retirement_paise == spend_then
        assert e.savings_target_paise == corpus_for_expenses(spend_then, 700, 600, 25 * 12)
        assert e.return_bps == 1100

    def test_retirement_needs_profile(self):
        g = GoalInput(name="Retire", goal_type="retirement", priority="essential")
        assert evaluate_goal(g, ctx(date_of_birth=None)).status == "needs_info"
        assert evaluate_goal(g, ctx(monthly_spend_paise=0)).status == "needs_info"

    def test_achieved_and_missing_info(self):
        done = GoalInput(name="Bike", goal_type="big_purchase", priority="aspirational", status="achieved",
                         target_date=date(2027, 1, 1), current_cost_paise=LAKH)
        assert evaluate_goal(done, ctx()).status == "achieved"
        nodate = GoalInput(name="X", goal_type="other", priority="important", current_cost_paise=LAKH)
        assert evaluate_goal(nodate, ctx()).status == "needs_info"

    def test_priority_allocation(self):
        ess = GoalInput(goal_id="e", name="Edu", goal_type="child_education", priority="essential",
                        target_date=date(2027, 10, 9), current_cost_paise=3_30_000_00, inflation_bps=0, expected_return_bps=0)
        asp = GoalInput(goal_id="a", name="Car", goal_type="car", priority="aspirational",
                        target_date=date(2027, 10, 9), current_cost_paise=4_80_000_00, inflation_bps=0, expected_return_bps=0)
        plan = plan_goals([asp, ess], ctx(monthly_surplus_paise=50_000_00))
        alloc = {x.goal_id: x for x in plan.allocation}
        assert [x.goal_id for x in plan.allocation] == ["e", "a"]  # essential first
        assert alloc["e"].required_monthly_paise == 27_500_00 and alloc["e"].fully_funded
        assert alloc["a"].allocated_paise == 22_500_00 and not alloc["a"].fully_funded
        assert plan.unfunded_monthly_paise == 27_500_00 + 40_000_00 - 50_000_00
        assert "Car" in plan.messages[0]

    def test_no_surplus_message(self):
        plan = plan_goals([], ctx(monthly_surplus_paise=-1000))
        assert "no goal can be funded" in plan.messages[0]


# ---------------------------------------------------------------- API
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


def setup_household(client, h=A, income=150_000_00):
    client.put(f"{API}/household", json={"date_of_birth": "1991-10-09", "retirement_age": 60, "employment_type": "salaried", "income_stability": "stable"}, headers=h).raise_for_status()
    client.post(f"{API}/incomes", json={"name": "Salary", "kind": "salary", "amount_paise": income}, headers=h).raise_for_status()
    client.post(f"{API}/expenses", json={"name": "Rent", "category": "housing", "amount_paise": 40_000_00}, headers=h).raise_for_status()
    client.post(f"{API}/expenses", json={"name": "Fun", "category": "dining", "amount_paise": 20_000_00}, headers=h).raise_for_status()


CAR = {"name": "Car", "goal_type": "car", "target_date": "2029-10-09", "current_cost_paise": 10 * LAKH, "saved_paise": 2 * LAKH}


class TestGoalsApi:
    def test_crud_and_plan(self, client):
        setup_household(client)
        res = client.post(f"{API}/goals", json=CAR, headers=A)
        assert res.status_code == 201, res.text
        car = res.json()
        assert car["priority"] == "aspirational"
        ret = client.post(f"{API}/goals", json={"name": "Retirement", "goal_type": "retirement", "saved_paise": 10 * LAKH}, headers=A).json()
        assert ret["priority"] == "essential"

        plan = client.get(f"{API}/plan/goals", headers=A).json()
        assert plan["monthly_surplus_paise"] == 90_000_00
        assert [x["name"] for x in plan["allocation"]] == ["Retirement", "Car"]
        assert len(plan["assumptions"]) >= 3

        res = client.patch(f"{API}/goals/{car['id']}", json={"monthly_contribution_paise": 30_000_00}, headers=A)
        assert res.status_code == 200
        ev = client.get(f"{API}/goals/{car['id']}/evaluation", headers=A).json()
        assert ev["status"] == "on_track"
        assert client.delete(f"{API}/goals/{car['id']}", headers=A).status_code == 204
        assert client.get(f"{API}/goals/{car['id']}", headers=A).status_code == 404

    def test_what_if_does_not_save(self, client):
        setup_household(client)
        car = client.post(f"{API}/goals", json=CAR, headers=A).json()
        later = client.post(f"{API}/goals/{car['id']}/what-if", json={"target_date": "2031-10-09"}, headers=A).json()
        now = client.get(f"{API}/goals/{car['id']}/evaluation", headers=A).json()
        assert later["months_left"] == 60 and now["months_left"] == 36
        assert later["required_monthly_paise"] < now["required_monthly_paise"]
        ret = client.post(f"{API}/goals", json={"name": "R", "goal_type": "retirement"}, headers=A).json()
        early = client.post(f"{API}/goals/{ret['id']}/what-if", json={"retirement_age": 50}, headers=A).json()
        assert early["months_left"] == 180

    def test_preview(self, client):
        setup_household(client)
        ev = client.post(f"{API}/goals/preview", json=CAR, headers=A).json()
        assert ev["goal_id"] is None and ev["months_left"] == 36
        assert client.get(f"{API}/goals", headers=A).json() == []

    @pytest.mark.parametrize("payload,fragment", [
        ({**CAR, "target_date": None}, "target_date is required"),
        ({**CAR, "current_cost_paise": None}, "current_cost_paise"),
        ({**CAR, "target_date": "2026-10-20"}, "at least a month"),
        ({**CAR, "target_date": "2090-01-01"}, "within 50 years"),
        ({**CAR, "down_payment_bps": 2000}, "only applies to home"),
        ({"name": "R", "goal_type": "retirement", "target_date": "2050-01-01"}, "retirement age"),
    ])
    def test_validation(self, client, payload, fragment):
        res = client.post(f"{API}/goals", json=payload, headers=A)
        assert res.status_code == 422 and fragment in res.text

    def test_single_retirement_goal_and_isolation(self, client):
        client.post(f"{API}/goals", json={"name": "R", "goal_type": "retirement"}, headers=A).raise_for_status()
        assert client.post(f"{API}/goals", json={"name": "R2", "goal_type": "retirement"}, headers=A).status_code == 422
        assert client.post(f"{API}/goals", json={"name": "R", "goal_type": "retirement"}, headers=B).status_code == 201
        a_goal = client.get(f"{API}/goals", headers=A).json()[0]
        assert client.get(f"{API}/goals/{a_goal['id']}", headers=B).status_code == 404
        assert client.post(f"{API}/goals/{a_goal['id']}/what-if", json={}, headers=B).status_code == 404

    def test_assumptions_endpoint(self, client):
        body = client.get(f"{API}/assumptions", headers=A).json()
        assert body["effective"]["general_inflation_bps"] == 600 and body["effective"]["version"] == DEFAULT.version


class TestSafetyApi:
    def test_emergency_fund(self, client):
        setup_household(client)
        ef = client.get(f"{API}/plan/emergency-fund", headers=A).json()
        # obligations 40k essential; stable 3–6 months, +1 for no health cover
        assert ef["monthly_obligations_paise"] == 40_000_00
        assert (ef["target_months_low"], ef["target_months_high"]) == (4, 7)
        assert ef["status"] == "critical" and ef["current_paise"] == 0
        client.post(f"{API}/assets", json={"name": "Savings", "asset_type": "savings_account", "current_value_paise": 2 * LAKH, "is_emergency_fund": True}, headers=A)
        client.post(f"{API}/assets", json={"name": "FD", "asset_type": "fixed_deposit", "current_value_paise": 5 * LAKH}, headers=A)
        ef = client.get(f"{API}/plan/emergency-fund", headers=A).json()
        assert ef["uses_flagged_assets"] and ef["current_paise"] == 2 * LAKH
        assert ef["months_covered"] == 5.0 and ef["status"] == "good"

    def test_debts_and_prepay(self, client):
        setup_household(client)
        car = client.post(f"{API}/liabilities", json={"name": "Home", "liability_type": "home_loan", "outstanding_paise": 10 * LAKH, "interest_rate_bps": 900, "emi_paise": 899726}, headers=A).json()
        client.post(f"{API}/liabilities", json={"name": "Card", "liability_type": "credit_card", "outstanding_paise": 50_000_00}, headers=A)
        d = client.get(f"{API}/plan/debts", headers=A).json()
        home = next(x for x in d["loans"] if x["name"] == "Home")
        assert home["months_left"] == 240 and home["interest_remaining_paise"] == 115934212
        assert d["status"] == "critical" and d["high_cost_outstanding_paise"] == 50_000_00
        assert d["payoff_order"][0] != car["id"]  # card first

        p = client.post(f"{API}/plan/debts/{car['id']}/prepay", json={"lump_sum_paise": LAKH}, headers=A).json()
        assert p["months_saved"] > 0 and p["interest_saved_paise"] > 0
        assert p["investment_return_bps"] == 1100 and p["better_option"] in ("invest", "similar")

    def test_prepay_high_rate_short_loan_favours_prepay(self, client):
        setup_household(client)
        pl = client.post(f"{API}/liabilities", json={"name": "PL", "liability_type": "personal_loan", "outstanding_paise": 2 * LAKH, "interest_rate_bps": 1600, "emi_paise": emi(2 * LAKH, 1600, 24)}, headers=A).json()
        p = client.post(f"{API}/plan/debts/{pl['id']}/prepay", json={"extra_monthly_paise": 5_000_00}, headers=A).json()
        assert p["base_months"] == 24 and p["better_option"] == "prepay"

    def test_prepay_validation(self, client):
        setup_household(client)
        card = client.post(f"{API}/liabilities", json={"name": "Card", "liability_type": "credit_card", "outstanding_paise": 50_000_00}, headers=A).json()
        assert client.post(f"{API}/plan/debts/{card['id']}/prepay", json={"lump_sum_paise": 100}, headers=A).status_code == 422
        assert client.post(f"{API}/plan/debts/{card['id']}/prepay", json={}, headers=A).status_code == 422
        assert client.post(f"{API}/plan/debts/{card['id']}/prepay", json={"lump_sum_paise": 100}, headers=B).status_code == 404

    def test_protection(self, client):
        setup_household(client)
        client.post(f"{API}/household/members", json={"name": "Kid", "relationship": "child"}, headers=A)
        client.post(f"{API}/liabilities", json={"name": "Car", "liability_type": "car_loan", "outstanding_paise": 3 * LAKH, "interest_rate_bps": 900, "emi_paise": 10_000_00}, headers=A)
        client.post(f"{API}/assets", json={"name": "MF", "asset_type": "mutual_fund", "current_value_paise": 5 * LAKH}, headers=A)
        client.post(f"{API}/insurance", json={"policy_type": "health", "source": "employer", "cover_amount_paise": 5 * LAKH, "renewal_date": "2026-10-30"}, headers=A)
        p = client.get(f"{API}/plan/protection", headers=A).json()
        # 10 × 18L income + 3L loan − 5L investments = 1.78 Cr
        assert p["life"]["recommended_paise"] == 10 * 18 * LAKH + 3 * LAKH - 5 * LAKH
        assert p["life"]["status"] == "critical"
        assert p["health"]["recommended_paise"] == 10 * LAKH and p["health"]["gap_paise"] == 5 * LAKH
        assert p["health"]["status"] == "attention"
        assert len(p["renewals"]) == 1 and p["renewals"][0]["days_left"] == 21
        assert any("Employer" in m for m in p["messages"])

    def test_protection_no_dependents(self, client):
        setup_household(client)
        p = client.get(f"{API}/plan/protection", headers=A).json()
        assert p["life"]["status"] == "not_needed" and p["health"]["status"] == "critical"

    def test_overview(self, client):
        setup_household(client)
        o = client.get(f"{API}/plan/overview", headers=A).json()
        assert o["emergency_status"] == "critical" and o["debt_status"] == "none"


class TestPrepayFairness:
    @pytest.mark.parametrize("rate,months,lump,extra", [(1600, 24, 0, 5_000_00), (900, 240, LAKH, 0), (850, 180, 50_000_00, 3_000_00)])
    def test_both_options_spend_the_same_cash(self, rate, months, lump, extra):
        """Same money leaves your pocket in both options, so comparing end wealth is fair."""
        from types import SimpleNamespace
        from app.calc.finance import amortize
        from app.modules.planning.safety import prepay_vs_invest

        principal = 20 * LAKH
        lia = SimpleNamespace(id="x", outstanding_paise=principal, interest_rate_bps=rate, emi_paise=emi(principal, rate, months))
        res = prepay_vs_invest(lia, lump, extra)
        base = amortize(principal, rate, lia.emi_paise)
        new = amortize(principal, rate, lia.emi_paise, extra_monthly_paise=extra, lump_sum_now_paise=lump)
        budget = lia.emi_paise + extra
        cash_a = new.total_paid_paise + budget * res.months_saved + max(0, budget * new.months - (new.total_paid_paise - lump))
        cash_b = base.total_paid_paise + lump + extra * base.months
        assert abs(cash_a - cash_b) <= 1000  # equal up to the ₹10 rounding residue settled with the last EMI
        if rate >= 1400 and months <= 24:
            assert res.better_option == "prepay"
