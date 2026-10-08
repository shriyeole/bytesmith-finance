"""Tests for M0 (auth, settings, account) and M1 (financial state)."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.calc.normalize import monthly_equivalent_paise, ratio_bps
from app.core.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app

API = "/api/v1"
ALICE = {"Authorization": "Bearer dev:alice"}
BOB = {"Authorization": "Bearer dev:bob"}
LAKH = 100_000 * 100  # ₹1 lakh in paise


@pytest.fixture
def client():
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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


# ------------------------------------------------------------------ calc
class TestNormalize:
    @pytest.mark.parametrize("amount,freq,expected", [
        (12000, "monthly", 12000),
        (30000, "quarterly", 10000),
        (10, "quarterly", 3),          # 3.33 -> 3
        (5, "quarterly", 2),           # 1.67 -> 2
        (120000, "yearly", 10000),
        (18, "yearly", 2),             # 1.5 -> 2 (half up)
        (60000, "half_yearly", 10000),
        (999999, "one_time", 0),
    ])
    def test_monthly_equivalent(self, amount, freq, expected):
        assert monthly_equivalent_paise(amount, freq) == expected

    def test_rejects_bad_input(self):
        with pytest.raises(TypeError):
            monthly_equivalent_paise(True, "monthly")
        with pytest.raises(ValueError):
            monthly_equivalent_paise(-1, "monthly")
        with pytest.raises(ValueError):
            monthly_equivalent_paise(1, "weekly")

    def test_ratio_bps(self):
        assert ratio_bps(1, 3) == 3333
        assert ratio_bps(-20, 100) == -2000
        assert ratio_bps(5, 0) is None


# ------------------------------------------------------------------ settings & auth
class TestAuth:
    def test_production_refuses_dev_auth_and_sqlite(self):
        with pytest.raises(ValueError):
            Settings(environment="production", auth_mode="dev", database_url="postgresql+psycopg://x@/db", auto_create_tables=False)
        with pytest.raises(ValueError):
            Settings(environment="production", auth_mode="firebase", database_url="sqlite:///x.db", auto_create_tables=False)
        ok = Settings(environment="production", auth_mode="firebase", database_url="postgresql+psycopg://x@/db", auto_create_tables=False)
        assert ok.auth_mode == "firebase"

    def test_cors_origins_from_comma_string(self):
        assert Settings(cors_origins="https://a.app, https://b.app").cors_origins == ["https://a.app", "https://b.app"]

    def test_dev_header_sets_user(self, client):
        assert client.get(f"{API}/me", headers=ALICE).json()["id"] == "alice"
        assert client.get(f"{API}/me").json()["id"] == "user_default"

    @pytest.mark.parametrize("header", ["Basic abc", "Bearer ", "Bearer notdev", "Bearer dev:"])
    def test_bad_dev_tokens_rejected(self, client, header):
        assert client.get(f"{API}/me", headers={"Authorization": header}).status_code == 401

    def test_firebase_mode_requires_token(self, client):
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", auth_mode="firebase")
        assert client.get(f"{API}/me").status_code == 401
        assert client.get(f"{API}/me", headers={"Authorization": "Bearer garbage"}).status_code == 401

    def test_health_under_api_prefix(self, client):
        assert client.get("/api/health").json()["status"] == "ok"


# ------------------------------------------------------------------ CRUD & validation
INCOME = {"name": "Salary", "kind": "salary", "amount_paise": 150_000_00, "expected_growth_bps": 800}


class TestCrud:
    def test_create_list_get_patch_delete(self, client):
        res = client.post(f"{API}/incomes", json=INCOME, headers=ALICE)
        assert res.status_code == 201, res.text
        item = res.json()
        assert item["frequency"] == "monthly" and item["owner"] == "self"
        assert item["monthly_equivalent_paise"] == 150_000_00

        assert len(client.get(f"{API}/incomes", headers=ALICE).json()) == 1
        res = client.patch(f"{API}/incomes/{item['id']}", json={"amount_paise": 120_000_00, "frequency": "yearly"}, headers=ALICE)
        assert res.status_code == 200
        assert res.json()["monthly_equivalent_paise"] == 10_000_00
        assert res.json()["name"] == "Salary"  # untouched

        assert client.delete(f"{API}/incomes/{item['id']}", headers=ALICE).status_code == 204
        assert client.get(f"{API}/incomes/{item['id']}", headers=ALICE).status_code == 404

    def test_users_are_isolated(self, client):
        item = client.post(f"{API}/incomes", json=INCOME, headers=ALICE).json()
        assert client.get(f"{API}/incomes", headers=BOB).json() == []
        assert client.get(f"{API}/incomes/{item['id']}", headers=BOB).status_code == 404
        assert client.patch(f"{API}/incomes/{item['id']}", json={"name": "x"}, headers=BOB).status_code == 404
        assert client.delete(f"{API}/incomes/{item['id']}", headers=BOB).status_code == 404
        assert len(client.get(f"{API}/incomes", headers=ALICE).json()) == 1

    @pytest.mark.parametrize("bad", [1500.5, "150000", True, -1, 10**15 + 1])
    def test_money_must_be_nonnegative_int_paise(self, client, bad):
        res = client.post(f"{API}/incomes", json={**INCOME, "amount_paise": bad}, headers=ALICE)
        assert res.status_code == 422

    def test_unknown_fields_and_bad_enums_rejected(self, client):
        assert client.post(f"{API}/incomes", json={**INCOME, "amount": 5}, headers=ALICE).status_code == 422
        assert client.post(f"{API}/incomes", json={**INCOME, "kind": "lottery"}, headers=ALICE).status_code == 422
        assert client.post(f"{API}/incomes", json={**INCOME, "name": "   "}, headers=ALICE).status_code == 422

    def test_patch_cannot_null_required_field(self, client):
        item = client.post(f"{API}/incomes", json=INCOME, headers=ALICE).json()
        res = client.patch(f"{API}/incomes/{item['id']}", json={"amount_paise": None}, headers=ALICE)
        assert res.status_code == 422
        # optional fields may be cleared
        res = client.patch(f"{API}/incomes/{item['id']}", json={"expected_growth_bps": None}, headers=ALICE)
        assert res.status_code == 200 and res.json()["expected_growth_bps"] is None

    def test_large_values_fit(self, client):
        ten_crore = 10 * 100 * LAKH  # ₹10 crore — overflowed a 32-bit column before BigInteger
        res = client.post(f"{API}/assets", json={"name": "Flat", "asset_type": "real_estate", "current_value_paise": ten_crore}, headers=ALICE)
        assert res.status_code == 201 and res.json()["current_value_paise"] == ten_crore

    def test_expense_bucket_defaults_and_overrides(self, client):
        rent = client.post(f"{API}/expenses", json={"name": "Rent", "category": "housing", "amount_paise": 25_000_00}, headers=ALICE).json()
        assert rent["bucket"] == "essential"
        gym = client.post(f"{API}/expenses", json={"name": "Gym", "category": "healthcare", "bucket": "discretionary", "amount_paise": 2_000_00}, headers=ALICE).json()
        assert gym["bucket"] == "discretionary"
        moved = client.patch(f"{API}/expenses/{rent['id']}", json={"category": "travel"}, headers=ALICE).json()
        assert moved["bucket"] == "discretionary"
        renamed = client.patch(f"{API}/expenses/{gym['id']}", json={"name": "Gym membership"}, headers=ALICE).json()
        assert renamed["bucket"] == "discretionary"  # user's override kept

    def test_asset_liquidity_defaults(self, client):
        fd = client.post(f"{API}/assets", json={"name": "FD", "asset_type": "fixed_deposit", "current_value_paise": 1}, headers=ALICE).json()
        assert fd["liquidity"] == "short_term"
        ppf = client.post(f"{API}/assets", json={"name": "PPF", "asset_type": "ppf", "current_value_paise": 1}, headers=ALICE).json()
        assert ppf["liquidity"] == "locked"


# ------------------------------------------------------------------ household
def _dob(age: int) -> str:
    today = date.today()
    return date(today.year - age, 1, 1).isoformat()


class TestHousehold:
    def test_upsert_and_derived_fields(self, client):
        assert client.get(f"{API}/household", headers=ALICE).status_code == 404
        res = client.put(f"{API}/household", json={"date_of_birth": _dob(30), "retirement_age": 60, "employment_type": "salaried"}, headers=ALICE)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["age"] in (29, 30) and body["years_to_retirement"] in (30, 31)
        assert body["tax_regime"] == "unknown"
        res = client.put(f"{API}/household", json={"city": "Pune"}, headers=ALICE)
        assert res.json()["retirement_age"] == 60 and res.json()["city"] == "Pune"

    def test_validation(self, client):
        assert client.put(f"{API}/household", json={"date_of_birth": _dob(10)}, headers=ALICE).status_code == 422
        assert client.put(f"{API}/household", json={"date_of_birth": _dob(40), "retirement_age": 35}, headers=ALICE).status_code == 422
        client.put(f"{API}/household", json={"date_of_birth": _dob(50)}, headers=ALICE)
        # retirement age checked against the stored DOB too
        assert client.put(f"{API}/household", json={"retirement_age": 45}, headers=ALICE).status_code == 422

    def test_members(self, client):
        res = client.post(f"{API}/household/members", json={"name": "Asha", "relationship": "child", "date_of_birth": "2018-05-01"}, headers=ALICE)
        assert res.status_code == 201 and res.json()["is_dependent"] is True
        future = {"name": "X", "relationship": "child", "date_of_birth": "2999-01-01"}
        assert client.post(f"{API}/household/members", json=future, headers=ALICE).status_code == 422


# ------------------------------------------------------------------ summary
class TestSummary:
    def test_empty_state(self, client):
        body = client.get(f"{API}/financial-state/summary", headers=ALICE).json()
        assert body["monthly_income_paise"] == 0 and body["savings_rate_bps"] is None
        assert body["emergency_runway_months"] is None and len(body["notes"]) >= 1

    def test_worked_example(self, client):
        h = ALICE
        post = lambda path, data: client.post(f"{API}{path}", json=data, headers=h).raise_for_status()
        post("/incomes", {"name": "Salary", "kind": "salary", "amount_paise": 125_000_00})
        post("/incomes", {"name": "Bonus", "kind": "bonus", "amount_paise": 120_000_00, "frequency": "yearly"})   # +10,000/m
        post("/incomes", {"name": "Old job", "kind": "salary", "amount_paise": 50_000_00, "is_active": False})   # ignored
        post("/expenses", {"name": "Rent", "category": "housing", "amount_paise": 30_000_00})
        post("/expenses", {"name": "Groceries", "category": "groceries", "amount_paise": 12_000_00})
        post("/expenses", {"name": "Dining", "category": "dining", "amount_paise": 8_000_00})
        post("/expenses", {"name": "Holiday", "category": "travel", "amount_paise": 120_000_00, "frequency": "yearly"})  # 10,000/m
        post("/liabilities", {"name": "Car loan", "liability_type": "car_loan", "outstanding_paise": 4 * LAKH, "interest_rate_bps": 900, "emi_paise": 15_000_00})
        post("/liabilities", {"name": "Card", "liability_type": "credit_card", "outstanding_paise": 50_000_00})
        post("/insurance", {"policy_type": "health", "cover_amount_paise": 10 * LAKH, "annual_premium_paise": 24_000_00})  # 2,000/m
        post("/insurance", {"policy_type": "health", "source": "employer", "cover_amount_paise": 5 * LAKH, "annual_premium_paise": 0})
        post("/insurance", {"policy_type": "term_life", "cover_amount_paise": 100 * LAKH, "annual_premium_paise": 12_000_00})  # 1,000/m
        post("/assets", {"name": "Savings", "asset_type": "savings_account", "current_value_paise": 3 * LAKH, "is_emergency_fund": True})
        post("/assets", {"name": "FD", "asset_type": "fixed_deposit", "current_value_paise": 2 * LAKH})
        post("/assets", {"name": "MF", "asset_type": "mutual_fund", "current_value_paise": 6 * LAKH, "monthly_contribution_paise": 20_000_00})
        post("/household/members", {"name": "Spouse", "relationship": "spouse", "is_dependent": False})
        post("/household/members", {"name": "Kid", "relationship": "child"})

        b = client.get(f"{API}/financial-state/summary", headers=h).json()
        assert b["monthly_income_paise"] == 135_000_00
        assert b["monthly_essential_expenses_paise"] == 42_000_00
        assert b["monthly_discretionary_expenses_paise"] == 18_000_00
        assert b["monthly_insurance_premiums_paise"] == 3_000_00
        assert b["monthly_emi_paise"] == 15_000_00
        assert b["monthly_surplus_paise"] == 57_000_00          # 135 - 42 - 18 - 3 - 15
        assert b["monthly_planned_investments_paise"] == 20_000_00
        assert b["monthly_unallocated_paise"] == 37_000_00
        assert b["savings_rate_bps"] == 4222                      # 57/135
        assert b["total_assets_paise"] == 11 * LAKH
        assert b["liquid_assets_paise"] == 5 * LAKH
        assert b["emergency_fund_paise"] == 3 * LAKH
        assert b["total_liabilities_paise"] == 4 * LAKH + 50_000_00
        assert b["high_cost_debt_paise"] == 50_000_00             # card only; 9% car loan is not high-cost
        assert b["net_worth_paise"] == 11 * LAKH - 4 * LAKH - 50_000_00
        assert b["emergency_runway_months"] == 8.3               # 5L / 60k
        assert b["debt_to_income_bps"] == 1111                    # 15/135
        assert b["health_cover_paise"] == 15 * LAKH
        assert b["life_cover_paise"] == 100 * LAKH
        assert b["dependents_count"] == 1

        assert client.get(f"{API}/financial-state/summary", headers=BOB).json()["monthly_income_paise"] == 0


# ------------------------------------------------------------------ onboarding & account
class TestOnboardingAndAccount:
    def test_onboarding_flow(self, client):
        s = client.get(f"{API}/onboarding", headers=ALICE).json()
        assert s["completed_count"] == 0 and s["next_step"] == "profile"
        client.put(f"{API}/household", json={"date_of_birth": _dob(35), "retirement_age": 60, "employment_type": "salaried"}, headers=ALICE)
        s = client.get(f"{API}/onboarding", headers=ALICE).json()
        assert s["steps"][0]["completed"] and s["next_step"] == "income"
        # "I have no loans" — completing a step with zero items is allowed
        s = client.post(f"{API}/onboarding/steps/liabilities/complete", headers=ALICE).json()
        liab = next(x for x in s["steps"] if x["step"] == "liabilities")
        assert liab["completed"] and liab["item_count"] == 0
        client.post(f"{API}/onboarding/steps/liabilities/complete", headers=ALICE)  # idempotent
        assert client.get(f"{API}/onboarding", headers=ALICE).json()["completed_count"] == 2
        assert client.post(f"{API}/onboarding/steps/profile/complete", headers=ALICE).status_code == 422
        assert client.post(f"{API}/onboarding/steps/nonsense/complete", headers=ALICE).status_code == 422

    def test_delete_account_removes_everything(self, client):
        client.post(f"{API}/incomes", json=INCOME, headers=ALICE)
        client.put(f"{API}/household", json={"city": "Pune"}, headers=ALICE)
        client.post(f"{API}/onboarding/steps/income/complete", headers=ALICE)
        client.put(f"{API}/profile", json={"monthly_take_home_income": "1000"}, headers=ALICE)
        client.post(f"{API}/incomes", json=INCOME, headers=BOB)

        assert client.delete(f"{API}/me", headers=ALICE).status_code == 204
        assert client.get(f"{API}/incomes", headers=ALICE).json() == []
        assert client.get(f"{API}/household", headers=ALICE).status_code == 404
        assert client.get(f"{API}/profile", headers=ALICE).status_code == 404
        assert client.get(f"{API}/onboarding", headers=ALICE).json()["completed_count"] == 0
        assert len(client.get(f"{API}/incomes", headers=BOB).json()) == 1
