"""Tests for M8 (simulation), M9 (health score) and M10 (alerts & actions)."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.database import Base, get_db
from app.jobs.daily_alerts import run as run_daily
from app.jobs.notify import LogNotifier
from app.main import app
from app.modules.planning import router as planning_router
from app.modules.planning.simulation import CareerBreak, ChildEvent, ExtraGoal, WhatIf, Windfall, simulate
from app.modules.planning.snapshot import load_inputs

LAKH = 100_000 * 100
FLAT = {"general_inflation_bps": 0, "portfolio_return_bps": 0, "cash_return_bps": 0, "salary_growth_bps": 0,
        "post_retirement_return_bps": 0, "education_inflation_bps": 0}


def raw(income=100_000_00, essential=40_000_00, discretionary=20_000_00, assets=(), loans=(), goals=(), overrides=FLAT,
        dob="1991-10-09", retirement_age=60):
    return {
        "as_of": "2026-10-09",
        "household": {"date_of_birth": dob, "retirement_age": retirement_age, "income_stability": "stable", "employment_type": "salaried",
                      "marital_status": None, "full_name": None, "city": None, "tax_regime": "unknown"},
        "members": [], "policies": [],
        "incomes": [{"id": "i1", "name": "Salary", "kind": "salary", "owner": "self", "amount_paise": income, "frequency": "monthly",
                     "is_net_of_tax": True, "expected_growth_bps": None, "is_active": True}] if income else [],
        "expenses": [{"id": "e1", "name": "Rent", "category": "housing", "bucket": "essential", "amount_paise": essential, "frequency": "monthly", "inflation_bps": None},
                     {"id": "e2", "name": "Fun", "category": "dining", "bucket": "discretionary", "amount_paise": discretionary, "frequency": "monthly", "inflation_bps": None}],
        "assets": list(assets), "liabilities": list(loans), "goals": list(goals),
        "settings": {"assumption_overrides": dict(overrides)},
    }


def asset(id_, value, liquidity="market_linked"):
    return {"id": id_, "name": id_, "asset_type": "mutual_fund", "owner": "self", "current_value_paise": value, "liquidity": liquidity,
            "is_emergency_fund": False, "monthly_contribution_paise": 0, "value_as_of": None}


def goal(id_, name, gtype, target_date=None, cost=None, status="active"):
    return {"id": id_, "name": name, "goal_type": gtype, "priority": "important", "status": status, "target_date": target_date,
            "current_cost_paise": cost, "saved_paise": 0, "monthly_contribution_paise": 0, "inflation_bps": None,
            "expected_return_bps": None, "down_payment_bps": None, "notes": None}


# ================================================================ M8 simulation
class TestSimulation:
    def test_flat_world_is_simple_arithmetic(self):
        j = simulate(load_inputs(raw()))
        year1 = j.points[1]
        assert year1.month == 12 and year1.net_worth_paise == 12 * 40_000_00
        # surplus first fills a 6-month cash buffer of essentials (6 × 40k), the rest is invested
        assert year1.liquid_paise == 6 * 40_000_00 and year1.invested_paise == 12 * 40_000_00 - 6 * 40_000_00
        assert year1.income_paise == 12 * 100_000_00 and year1.spend_paise == 12 * 60_000_00
        s = j.summary
        assert s.retirement_month == 300 and s.net_worth_at_retirement_paise == 300 * 40_000_00
        # after retirement 60k/month is drawn from 1.2 Cr: lasts 200 months -> runs out at 76
        assert s.depleted_age == 76 and s.money_lasts_to_age == 76
        assert any(m.kind == "depleted" for m in j.milestones) and any(m.kind == "retirement" for m in j.milestones)

    def test_goal_paid_on_its_date(self):
        j = simulate(load_inputs(raw(goals=[goal("g1", "Car", "car", "2029-10-09", 10 * LAKH)])))
        assert j.summary.goals == [j.summary.goals[0]] and j.summary.goals[0].fully_funded
        assert j.summary.goals[0].cost_paise == 10 * LAKH
        assert j.points[3].net_worth_paise == 36 * 40_000_00 - 10 * LAKH
        short = simulate(load_inputs(raw(goals=[goal("g1", "Car", "car", "2027-10-09", 10 * LAKH)])))
        g = short.summary.goals[0]
        assert not g.fully_funded and g.funded_paise == 12 * 40_000_00
        assert any(m.kind == "goal_short" for m in short.milestones)

    def test_loan_closes_and_frees_emi(self):
        loan = {"id": "l1", "name": "Bike loan", "liability_type": "personal_loan", "lender": None, "outstanding_paise": 1_20_000_00,
                "interest_rate_bps": 0, "emi_paise": 10_000_00, "remaining_months": None}
        j = simulate(load_inputs(raw(loans=[loan])))
        closed = next(m for m in j.milestones if m.kind == "loan_closed")
        assert closed.month == 12 and closed.label == "Bike loan paid off"
        # net worth: −1.2L debt + 12 × (40k − 10k) saved + 1.2L repaid = 3.6L at month 12
        assert j.points[1].net_worth_paise == -1_20_000_00 + 12 * 30_000_00 + 1_20_000_00
        assert j.points[2].net_worth_paise - j.points[1].net_worth_paise == 12 * 40_000_00

    def test_scenarios_are_ordered(self):
        inp = load_inputs(raw(assets=[asset("a1", 10 * LAKH)], overrides={}))
        stress, base, up = (simulate(inp, sc).summary for sc in ("stress", "base", "upside"))
        assert stress.net_worth_at_retirement_real_paise < base.net_worth_at_retirement_real_paise < up.net_worth_at_retirement_real_paise

    def test_what_ifs_move_in_the_right_direction(self):
        inp = load_inputs(raw(assets=[asset("a1", 10 * LAKH)], overrides={}))
        base = simulate(inp).summary.net_worth_at_retirement_real_paise
        nw = lambda w: simulate(inp, what_if=w).summary.net_worth_at_retirement_real_paise
        assert nw(WhatIf(career_break=CareerBreak(start_in_months=12, months=12))) < base
        assert nw(WhatIf(spend_change_bps=-2000)) > base
        assert nw(WhatIf(salary_growth_bps=0)) < base
        assert nw(WhatIf(windfall=Windfall(in_months=6, amount_paise=5 * LAKH))) > base
        early = simulate(inp, what_if=WhatIf(retirement_age=50)).summary
        assert early.retirement_month == 180 and early.retirement_age == 50

    def test_home_child_events(self):
        inp = load_inputs(raw(overrides=FLAT))
        j = simulate(inp, what_if=WhatIf(extra_goals=[ExtraGoal(name="Flat", goal_type="home", cost_today_paise=50 * LAKH, in_months=60)],
                                         child=ChildEvent(in_months=24)))
        flat = next(g for g in j.summary.goals if g.name == "Flat")
        assert flat.cost_paise == 50 * LAKH * 27 // 100  # 20% down + 7% costs, no inflation
        assert j.points[5].property_paise == 50 * LAKH and j.points[5].debt_paise > 0
        assert any(m.kind == "child" for m in j.milestones)
        assert any(g.name == "Child's education" for g in j.summary.goals)

    def test_deterministic(self):
        inp = load_inputs(raw(assets=[asset("a1", 10 * LAKH)], overrides={}))
        assert simulate(inp).model_dump() == simulate(load_inputs(raw(assets=[asset("a1", 10 * LAKH)], overrides={}))).model_dump()


# ================================================================ API fixtures
class Clock:
    today = date(2026, 10, 9)


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

    Clock.today = date(2026, 10, 9)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: Settings(environment="test", auth_mode="dev")
    monkeypatch.setattr(planning_router, "_today", lambda: Clock.today)
    c = TestClient(app)
    c.session_factory = Session
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


API = "/api/v1"
A = {"Authorization": "Bearer dev:alice"}


def seed(client, income=100_000_00):
    post = lambda path, body: client.post(f"{API}{path}", json=body, headers=A).raise_for_status().json()
    client.put(f"{API}/household", json={"date_of_birth": "1991-10-09", "retirement_age": 60, "employment_type": "salaried", "income_stability": "stable"}, headers=A).raise_for_status()
    inc = post("/incomes", {"name": "Salary", "kind": "salary", "amount_paise": income})
    rent = post("/expenses", {"name": "Rent", "category": "housing", "amount_paise": 40_000_00})
    fun = post("/expenses", {"name": "Fun", "category": "dining", "amount_paise": 20_000_00})
    return inc, rent, fun


# ================================================================ M8/M9 API
class TestJourneyAndHealthApi:
    def test_journey_and_what_if(self, client):
        seed(client)
        j = client.get(f"{API}/plan/journey", headers=A).json()
        assert {j["base"]["scenario"], j["stress"]["scenario"], j["upside"]["scenario"]} == {"base", "stress", "upside"}
        assert len(j["base"]["points"]) > 30 and j["base"]["summary"]["retirement_age"] == 60
        res = client.post(f"{API}/plan/simulate", json={"what_if": {"career_break": {"start_in_months": 6, "months": 12}}}, headers=A).json()
        assert res["what_if"]["summary"]["net_worth_at_retirement_real_paise"] < res["base"]["summary"]["net_worth_at_retirement_real_paise"]
        assert "falls" in res["lines"][0]
        bad = client.post(f"{API}/plan/simulate", json={"what_if": {"career_break": {"months": 500}}}, headers=A)
        assert bad.status_code == 422
        assert client.post(f"{API}/plan/simulate", json={"scenario": "doom", "what_if": {}}, headers=A).status_code == 422

    def test_health_score(self, client):
        seed(client)
        h = client.get(f"{API}/plan/health", headers=A).json()
        parts = {p["key"]: p for p in h["parts"]}
        assert parts["savings"]["points"] == 20            # 40% saving rate ≥ 30%
        assert parts["emergency"]["points"] == 0           # no cash yet
        assert parts["debt"]["points"] == 20               # no loans
        assert parts["protection"]["points"] == 10         # no dependents (life ok), no health cover
        assert parts["goals"]["points"] == 10              # no goals: half marks
        assert h["score"] == 60 and h["band"] == "good"
        client.post(f"{API}/assets", json={"name": "Cash", "asset_type": "savings_account", "current_value_paise": 3 * LAKH}, headers=A)
        h2 = client.get(f"{API}/plan/health", headers=A).json()
        assert next(p for p in h2["parts"] if p["key"] == "emergency")["points"] > 0 and h2["score"] > 60

    def test_version_still_reproducible_with_new_outputs(self, client):
        seed(client)
        v = client.post(f"{API}/plan/versions", json={}, headers=A).json()
        detail = client.get(f"{API}/plan/versions/{v['id']}", headers=A).json()
        assert "health" in detail["outputs"] and "journey_summary" in detail["outputs"]
        assert client.get(f"{API}/plan/versions/{v['id']}/verify", headers=A).json()["reproducible"] is True


# ================================================================ M10 alerts
def alerts(client, hidden=False):
    return client.get(f"{API}/alerts", params={"include_hidden": hidden}, headers=A).json()


class TestAlerts:
    def test_raised_once_and_ranked(self, client):
        seed(client)
        first = alerts(client)
        keys = [a["rule_id"] for a in first["alerts"]]
        assert "emergency_low" in keys and "health_gap" in keys
        assert first["alerts"][0]["severity"] == "critical"           # ranked: critical first
        assert first["counts"]["critical"] >= 1
        again = alerts(client)
        assert [a["id"] for a in again["alerts"]] == [a["id"] for a in first["alerts"]]  # no duplicates

    def test_dismiss_snooze_resolve_and_escalate(self, client):
        seed(client)
        ef = next(a for a in alerts(client)["alerts"] if a["rule_id"] == "emergency_low")
        assert ef["severity"] == "critical"
        client.post(f"{API}/alerts/{ef['id']}/dismiss", headers=A)
        assert all(a["id"] != ef["id"] for a in alerts(client)["alerts"])           # stays quiet
        # condition improves to "attention" (still below target): stays dismissed (not more severe)
        cash = client.post(f"{API}/assets", json={"name": "Cash", "asset_type": "savings_account", "current_value_paise": 1 * LAKH}, headers=A).json()
        assert all(a["id"] != ef["id"] for a in alerts(client)["alerts"])
        # fully fixed: resolved
        client.patch(f"{API}/assets/{cash['id']}", json={"current_value_paise": 3 * LAKH}, headers=A)
        assert all(a["rule_id"] != "emergency_low" for a in alerts(client, hidden=True)["alerts"])
        # problem comes back: reopens as a fresh open alert, same row
        client.delete(f"{API}/assets/{cash['id']}", headers=A)
        back = next(a for a in alerts(client)["alerts"] if a["rule_id"] == "emergency_low")
        assert back["id"] == ef["id"] and back["status"] == "open"

        hg = next(a for a in alerts(client)["alerts"] if a["rule_id"] == "health_gap")
        client.post(f"{API}/alerts/{hg['id']}/snooze", json={"days": 7}, headers=A)
        assert all(a["id"] != hg["id"] for a in alerts(client)["alerts"])
        Clock.today = date(2026, 10, 17)
        assert any(a["id"] == hg["id"] for a in alerts(client)["alerts"])          # back after the snooze
        assert client.post(f"{API}/alerts/{hg['id']}/snooze", json={"days": 0}, headers=A).status_code == 422

    def test_done_and_actions(self, client):
        seed(client)
        actions = client.get(f"{API}/plan/actions", headers=A).json()
        assert 1 <= len(actions) <= 3 and all(a["action_link"] for a in actions)
        assert actions[0]["severity"] == "critical"
        done = client.post(f"{API}/alerts/{actions[0]['id']}/done", headers=A).json()
        assert done["status"] == "acted"
        assert all(a["id"] != actions[0]["id"] for a in client.get(f"{API}/plan/actions", headers=A).json())

    def test_salary_growth_below_plan(self, client):
        inc, rent, fun = seed(client)
        client.post(f"{API}/plan/versions", json={"label": "Start"}, headers=A)
        Clock.today = date(2028, 4, 9)                                       # 18 months later, no raise
        a = next(x for x in alerts(client)["alerts"] if x["rule_id"] == "salary_below_plan")
        assert a["severity"] == "warning" and "0.0% a year" in a["message"] and "7.0%" in a["message"]
        assert "lower in today's money" in a["message"] and a["impact_paise"] > 0
        assert a["action_link"] == "/journey"

    def test_raise_not_saved_and_loan_closed(self, client):
        inc, rent, fun = seed(client)
        loan = client.post(f"{API}/liabilities", json={"name": "Bike loan", "liability_type": "personal_loan", "outstanding_paise": LAKH, "interest_rate_bps": 1000, "emi_paise": 5_000_00}, headers=A).json()
        client.post(f"{API}/plan/versions", json={}, headers=A)
        client.patch(f"{API}/incomes/{inc['id']}", json={"amount_paise": 120_000_00}, headers=A)
        client.patch(f"{API}/expenses/{fun['id']}", json={"amount_paise": 40_000_00}, headers=A)  # raise all spent
        client.delete(f"{API}/liabilities/{loan['id']}", headers=A)
        rules = {x["rule_id"]: x for x in alerts(client)["alerts"]}
        assert rules["raise_not_saved"]["severity"] == "opportunity"
        assert rules["loan_closed"]["title"] == "Bike loan is paid off"
        assert "lifestyle_creep" in rules

    def test_income_stopped(self, client):
        inc, *_ = seed(client)
        client.post(f"{API}/plan/versions", json={}, headers=A)
        client.patch(f"{API}/incomes/{inc['id']}", json={"is_active": False}, headers=A)
        assert any(a["rule_id"] == "income_stopped" and a["severity"] == "critical" for a in alerts(client)["alerts"])

    def test_daily_job_sends_one_digest(self, client):
        seed(client)
        db = client.session_factory()
        notifier = LogNotifier()
        stats = run_daily(db, Clock.today, notifier)
        assert stats["users"] == 1 and stats["digests"] == 1 and stats["failed"] == 0
        sent = notifier.sent[0]["items"]
        assert all(i["severity"] in ("critical", "warning") for i in sent) and len(sent) >= 2
        again = run_daily(db, Clock.today, notifier)
        assert again["digests"] == 0 and len(notifier.sent) == 1                  # nothing new: no second email
        db.close()

    def test_alerts_deleted_with_account(self, client):
        seed(client)
        before = {a["id"] for a in alerts(client, hidden=True)["alerts"]}
        assert before
        assert client.delete(f"{API}/me", headers=A).status_code == 204
        from app.modules.planning.models import Alert
        db = client.session_factory()
        assert db.query(Alert).filter(Alert.id.in_(before)).count() == 0   # rows gone, not just hidden
        db.close()


class TestNoisePolicy:
    def test_app_list_is_stable_and_digest_is_capped(self, client, monkeypatch):
        seed(client)
        client.post(f"{API}/liabilities", json={"name": "Card", "liability_type": "credit_card", "outstanding_paise": 50_000_00}, headers=A)
        first = alerts(client)["alerts"]
        assert alerts(client)["alerts"] == first          # nothing new appears on refresh
        done = client.post(f"{API}/alerts/{first[0]['id']}/done", headers=A).json()
        assert len(alerts(client)["alerts"]) == len(first) - 1
        import app.jobs.daily_alerts as job
        monkeypatch.setattr(job, "MAX_DIGEST_ITEMS", 1)
        db = client.session_factory()
        n = LogNotifier()
        run_daily(db, Clock.today, n)
        assert len(n.sent[0]["items"]) == 1               # capped email
        run_daily(db, Clock.today, n)
        assert len(n.sent) == 2                           # remaining important ones go next day
        db.close()
