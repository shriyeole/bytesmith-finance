"""Comprehensive integration tests for Profile, Goal, and Feasibility APIs."""

from datetime import date, timedelta
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.profile import DEFAULT_USER_ID, UserProfile


from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_db_session():
    """Isolated in-memory SQLite database and session with foreign key enforcement."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def client(test_db_session):
    """FastAPI test client with dependency override pointing to isolated in-memory DB."""
    def override_get_db():
        session = test_db_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()



# ==============================================================================
# PROFILE API TESTS
# ==============================================================================


class TestProfileAPI:
    """Verify GET and PUT /profile behavior, nullability, and precision."""

    def test_get_profile_not_found(self, client: TestClient):
        response = client.get("/profile")
        assert response.status_code == 404
        assert response.json()["detail"] == "Financial profile not found."

    def test_put_profile_create_complete_with_decimal_strings(self, client: TestClient):
        payload = {
            "monthly_take_home_income": "150000.00",
            "existing_savings": "600000.00",
            "emergency_reserve": "300000.00",
            "monthly_fixed_commitments": "45000.00",
            "monthly_estimated_living_expenses": "25000.00",
            "monthly_estimated_discretionary": "20000.00",
            "currency": "INR",
        }
        response = client.put("/profile", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == DEFAULT_USER_ID
        assert data["monthly_take_home_income_paise"] == 15000000
        assert data["existing_savings_paise"] == 60000000
        assert data["emergency_reserve_paise"] == 30000000
        assert data["monthly_fixed_commitments_paise"] == 4500000
        assert data["monthly_estimated_living_expenses_paise"] == 2500000
        assert data["monthly_estimated_discretionary_paise"] == 2000000
        assert data["unencumbered_savings_paise"] == 30000000
        # Income (1,50,000) - Fixed (45,000) - Living (25,000) - Disc (20,000) = Surplus (60,000 -> 6000000 paise)
        assert data["manual_baseline_surplus_paise"] == 6000000
        assert data["is_complete"] is True
        assert data["missing_fields"] == []

        # Confirm GET returns the newly created profile
        get_res = client.get("/profile")
        assert get_res.status_code == 200
        assert get_res.json() == data

    def test_put_profile_create_with_integer_paise(self, client: TestClient):
        payload = {
            "monthly_take_home_income_paise": 10000000,
            "existing_savings_paise": 20000000,
            "emergency_reserve_paise": 10000000,
            "monthly_fixed_commitments_paise": 3000000,
            "monthly_estimated_living_expenses_paise": 2000000,
            "monthly_estimated_discretionary_paise": 1000000,
        }
        response = client.put("/profile", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["monthly_take_home_income_paise"] == 10000000
        assert data["is_complete"] is True
        assert data["manual_baseline_surplus_paise"] == 4000000

    def test_put_profile_partial_update_preserves_omitted_fields(self, client: TestClient):
        # 1. Create initial profile
        initial = {
            "monthly_take_home_income": "100000.00",
            "existing_savings": "500000.00",
            "emergency_reserve": "200000.00",
            "monthly_fixed_commitments": "30000.00",
            "monthly_estimated_living_expenses": "20000.00",
            "monthly_estimated_discretionary": "10000.00",
        }
        res = client.put("/profile", json=initial)
        assert res.status_code == 200

        # 2. Update only income; omit all other fields
        update_payload = {
            "monthly_take_home_income": "120000.00",
        }
        res = client.put("/profile", json=update_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["monthly_take_home_income_paise"] == 12000000
        # Preserved values:
        assert data["existing_savings_paise"] == 50000000
        assert data["emergency_reserve_paise"] == 20000000
        assert data["monthly_fixed_commitments_paise"] == 3000000
        assert data["monthly_estimated_living_expenses_paise"] == 2000000
        assert data["monthly_estimated_discretionary_paise"] == 1000000

    def test_put_profile_explicit_null_clears_nullable_field(self, client: TestClient):
        initial = {
            "monthly_take_home_income": "100000.00",
            "existing_savings": "500000.00",
            "monthly_estimated_discretionary": "15000.00",
        }
        client.put("/profile", json=initial)

        # Clear discretionary expenses with explicit null
        res = client.put("/profile", json={"monthly_estimated_discretionary": None})
        assert res.status_code == 200
        data = res.json()
        assert data["monthly_estimated_discretionary_paise"] is None
        assert data["is_complete"] is False
        assert "monthly_estimated_discretionary_paise" in data["missing_fields"]
        assert data["manual_baseline_surplus_paise"] is None

    def test_put_profile_explicit_zero_stores_zero(self, client: TestClient):
        initial = {
            "monthly_take_home_income": "100000.00",
            "existing_savings": "500000.00",
            "emergency_reserve": "200000.00",
            "monthly_fixed_commitments": "30000.00",
            "monthly_estimated_living_expenses": "20000.00",
            "monthly_estimated_discretionary": "10000.00",
        }
        client.put("/profile", json=initial)

        # Explicit zero is valid and distinct from null
        res = client.put(
            "/profile",
            json={
                "monthly_fixed_commitments": "0",
                "monthly_estimated_discretionary": 0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["monthly_fixed_commitments_paise"] == 0
        assert data["monthly_estimated_discretionary_paise"] == 0
        assert data["is_complete"] is True
        # Income (100,000) - Living (20,000) - Fixed (0) - Disc (0) = 80,000
        assert data["manual_baseline_surplus_paise"] == 8000000

    def test_put_profile_rejects_negative_amount(self, client: TestClient):
        res = client.put("/profile", json={"monthly_take_home_income": "-1000.00"})
        assert res.status_code == 422

        res2 = client.put("/profile", json={"monthly_take_home_income_paise": -500})
        assert res2.status_code == 422

    def test_put_profile_rejects_float_amount(self, client: TestClient):
        # Floats must be rejected to prevent binary floating-point rounding bugs
        res = client.put("/profile", json={"monthly_take_home_income": 15000.50})
        assert res.status_code == 422

    def test_put_profile_rejects_boolean_amount(self, client: TestClient):
        res = client.put("/profile", json={"monthly_take_home_income": True})
        assert res.status_code == 422

    def test_put_profile_rejects_malformed_string(self, client: TestClient):
        res = client.put("/profile", json={"monthly_take_home_income": "invalid_number"})
        assert res.status_code == 422

    def test_put_profile_rejects_excessive_fractional_precision(self, client: TestClient):
        res = client.put("/profile", json={"monthly_take_home_income": "123.456"})
        assert res.status_code == 422

    def test_put_profile_rejects_extra_fields(self, client: TestClient):
        res = client.put("/profile", json={"unknown_field": 12345})
        assert res.status_code == 422

    def test_put_profile_rejects_reserve_greater_than_savings_on_creation(self, client: TestClient):
        res = client.put(
            "/profile",
            json={
                "monthly_take_home_income": "100000.00",
                "existing_savings": "100000.00",
                "emergency_reserve": "200000.00",
            },
        )
        assert res.status_code == 422
        assert "Emergency reserve cannot exceed existing savings" in str(res.json()["detail"])

    def test_put_profile_allows_reserve_equal_to_savings(self, client: TestClient):
        res = client.put(
            "/profile",
            json={
                "monthly_take_home_income": "100000.00",
                "existing_savings": "200000.00",
                "emergency_reserve": "200000.00",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["existing_savings_paise"] == 20000000
        assert data["emergency_reserve_paise"] == 20000000
        assert data["unencumbered_savings_paise"] == 0

    def test_put_profile_zero_savings_and_reserve_boundaries(self, client: TestClient):
        # 1. Zero reserve with positive savings -> allowed, unencumbered == savings
        res1 = client.put(
            "/profile",
            json={"existing_savings": "150000.00", "emergency_reserve": "0.00"},
        )
        assert res1.status_code == 200
        assert res1.json()["unencumbered_savings_paise"] == 15000000

        # 2. Both zero -> allowed, unencumbered == 0
        res2 = client.put(
            "/profile",
            json={"existing_savings": 0, "emergency_reserve": 0},
        )
        assert res2.status_code == 200
        assert res2.json()["unencumbered_savings_paise"] == 0

        # 3. Zero savings with positive reserve -> rejected (reserve > savings)
        res3 = client.put(
            "/profile",
            json={"existing_savings": 0, "emergency_reserve": 50000},
        )
        assert res3.status_code == 422
        assert "Emergency reserve cannot exceed existing savings" in str(res3.json()["detail"])

    def test_put_profile_partial_update_rejects_reserve_exceeding_persisted_savings(
        self, client: TestClient
    ):
        # Initial: savings 5L, reserve 2L
        client.put(
            "/profile",
            json={"existing_savings": "500000.00", "emergency_reserve": "200000.00"},
        )

        # Update reserve to 6L (omitting savings) -> rejected against persisted 5L savings
        res = client.put("/profile", json={"emergency_reserve": "600000.00"})
        assert res.status_code == 422
        assert "Emergency reserve cannot exceed existing savings" in res.json()["detail"]

        # Verify DB remained unmodified
        profile = client.get("/profile").json()
        assert profile["emergency_reserve_paise"] == 20000000
        assert profile["existing_savings_paise"] == 50000000

    def test_put_profile_partial_update_rejects_savings_dropping_below_persisted_reserve(
        self, client: TestClient
    ):
        # Initial: savings 5L, reserve 2L
        client.put(
            "/profile",
            json={"existing_savings": "500000.00", "emergency_reserve": "200000.00"},
        )

        # Update savings to 1L (omitting reserve) -> rejected against persisted 2L reserve
        res = client.put("/profile", json={"existing_savings": "100000.00"})
        assert res.status_code == 422
        assert "Emergency reserve cannot exceed existing savings" in res.json()["detail"]

        # Verify DB remained unmodified
        profile = client.get("/profile").json()
        assert profile["existing_savings_paise"] == 50000000
        assert profile["emergency_reserve_paise"] == 20000000

    def test_invalid_profile_update_does_not_corrupt_active_goal(self, client: TestClient):
        # Setup valid profile: savings 5L, reserve 2L (unencumbered 3L)
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "200000.00",
            },
        )
        # Setup goal: requested 2L (permitted 2L, uncapped)
        future_date = (date.today() + timedelta(days=365)).isoformat()
        goal_res = client.put(
            "/goal",
            json={
                "title": "House Fund",
                "target_amount": "1000000.00",
                "target_date": future_date,
                "requested_allocated_savings": "200000.00",
            },
        )
        assert goal_res.status_code == 200
        assert goal_res.json()["permitted_allocated_savings_paise"] == 20000000
        assert goal_res.json()["is_allocation_capped"] is False

        # Attempt invalid profile update: reserve = 8L > savings 5L
        fail_res = client.put("/profile", json={"emergency_reserve": "800000.00"})
        assert fail_res.status_code == 422

        # Verify goal and profile in DB are completely untouched
        get_profile_res = client.get("/profile").json()
        assert get_profile_res["emergency_reserve_paise"] == 20000000

        get_goal_res = client.get("/goal").json()
        assert get_goal_res["permitted_allocated_savings_paise"] == 20000000
        assert get_goal_res["is_allocation_capped"] is False

    def test_goal_sync_when_savings_or_reserve_become_unknown(self, client: TestClient):
        # Setup profile: savings 3L, reserve 1L (unencumbered 2L)
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "300000.00",
                "emergency_reserve": "100000.00",
                "monthly_fixed_commitments": "30000.00",
                "monthly_estimated_living_expenses": "20000.00",
                "monthly_estimated_discretionary": "10000.00",
            },
        )
        future_date = (date.today() + timedelta(days=365)).isoformat()
        # Goal requests 3L -> Capped at unencumbered 2L!
        goal_res = client.put(
            "/goal",
            json={
                "title": "Car Goal",
                "target_amount": "500000.00",
                "target_date": future_date,
                "requested_allocated_savings": "300000.00",
            },
        )
        assert goal_res.json()["permitted_allocated_savings_paise"] == 20000000
        assert goal_res.json()["is_allocation_capped"] is True
        assert goal_res.json()["net_funding_gap_paise"] == 30000000

        # Update profile: clear savings to null (savings becomes unknown)
        sync_res = client.put("/profile", json={"existing_savings": None})
        assert sync_res.status_code == 200

        # Verify active goal does not silently convert permitted to zero or falsely clear capped flag
        goal_after = client.get("/goal").json()
        assert goal_after["requested_allocated_savings_paise"] == 30000000
        assert goal_after["permitted_allocated_savings_paise"] is None  # Unknown, not 0!
        assert goal_after["net_funding_gap_paise"] is None             # Unknown, not fabricated!
        assert goal_after["is_allocation_capped"] is True              # NOT falsely cleared to False!

        # Feasibility also reflects unknown allocation as null
        feas = client.get("/goal/feasibility").json()
        assert feas["feasibility_status"] == "INSUFFICIENT_DATA"
        assert feas["permitted_allocated_savings_paise"] is None
        assert feas["net_funding_gap_paise"] is None

        # Re-supply savings to 5L (unencumbered = 5L - 1L = 4L)
        client.put("/profile", json={"existing_savings": "500000.00"})
        goal_recomputed = client.get("/goal").json()
        assert goal_recomputed["permitted_allocated_savings_paise"] == 30000000  # Fully permitted!
        assert goal_recomputed["is_allocation_capped"] is False                 # Now uncapped!
        assert goal_recomputed["net_funding_gap_paise"] == 20000000


# ==============================================================================
# GOAL API TESTS
# ==============================================================================


class TestGoalAPI:
    """Verify GET and PUT /goal endpoints, validation, and active goal constraints."""

    def test_get_goal_not_found(self, client: TestClient):
        res = client.get("/goal")
        assert res.status_code == 404
        assert res.json()["detail"] == "No active financial goal found."

    def test_put_goal_fails_when_profile_missing(self, client: TestClient):
        future_date = (date.today() + timedelta(days=365)).isoformat()
        res = client.put(
            "/goal",
            json={
                "title": "Dream Vacation",
                "target_amount": "200000.00",
                "target_date": future_date,
            },
        )
        assert res.status_code == 404
        assert "Financial profile not found" in res.json()["detail"]

    def test_put_goal_create_active_goal_success(self, client: TestClient):
        # 1. Create profile
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "200000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        future_date = (date.today() + timedelta(days=365)).isoformat()
        goal_payload = {
            "title": "Emergency Car Fund",
            "target_amount": "1000000.00",
            "target_date": future_date,
            "requested_allocated_savings": "100000.00",
        }
        res = client.put("/goal", json=goal_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Emergency Car Fund"
        assert data["target_amount_paise"] == 100000000
        assert data["requested_allocated_savings_paise"] == 10000000
        assert data["permitted_allocated_savings_paise"] == 10000000
        assert data["is_allocation_capped"] is False
        assert data["net_funding_gap_paise"] == 90000000
        assert data["status"] == "ACTIVE"

        # GET /goal returns the active goal
        get_res = client.get("/goal")
        assert get_res.status_code == 200
        assert get_res.json()["title"] == "Emergency Car Fund"

    def test_put_goal_updates_existing_active_goal_in_place(self, client: TestClient):
        client.put(
            "/profile",
            json={"monthly_take_home_income": "100000.00", "existing_savings": "200000.00"},
        )
        future_date_1 = (date.today() + timedelta(days=180)).isoformat()
        future_date_2 = (date.today() + timedelta(days=365)).isoformat()

        # First PUT creates
        res1 = client.put(
            "/goal",
            json={"title": "First Goal", "target_amount": "100000.00", "target_date": future_date_1},
        )
        assert res1.status_code == 200
        goal_id = res1.json()["id"]

        # Second PUT updates
        res2 = client.put(
            "/goal",
            json={"title": "Updated Goal Title", "target_amount": "150000.00", "target_date": future_date_2},
        )
        assert res2.status_code == 200
        assert res2.json()["id"] == goal_id
        assert res2.json()["title"] == "Updated Goal Title"
        assert res2.json()["target_amount_paise"] == 15000000

    def test_put_goal_caps_allocation_against_profile_reserve(self, client: TestClient):
        # Savings: 5L, Reserve: 3L -> Unencumbered: 2L
        client.put(
            "/profile",
            json={"existing_savings": "500000.00", "emergency_reserve": "300000.00"},
        )
        future_date = (date.today() + timedelta(days=365)).isoformat()

        # User requests 4L allocation (exceeds 2L unencumbered)
        res = client.put(
            "/goal",
            json={
                "title": "Home Down Payment",
                "target_amount": "2000000.00",
                "target_date": future_date,
                "requested_allocated_savings": "400000.00",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["requested_allocated_savings_paise"] == 40000000
        assert data["permitted_allocated_savings_paise"] == 20000000  # Capped at 2L
        assert data["is_allocation_capped"] is True
        assert data["net_funding_gap_paise"] == 180000000

    def test_put_goal_rejects_past_date(self, client: TestClient):
        client.put("/profile", json={"monthly_take_home_income": "100000.00"})
        past_date = (date.today() - timedelta(days=30)).isoformat()
        res = client.put(
            "/goal",
            json={
                "title": "Past Goal",
                "target_amount": "50000.00",
                "target_date": past_date,
            },
        )
        assert res.status_code == 422
        assert "in the past" in res.json()["detail"]

    def test_put_goal_rejects_zero_or_negative_target_amount(self, client: TestClient):
        client.put("/profile", json={"monthly_take_home_income": "100000.00"})
        future_date = (date.today() + timedelta(days=100)).isoformat()

        res_zero = client.put(
            "/goal",
            json={"title": "Zero Goal", "target_amount": "0", "target_date": future_date},
        )
        assert res_zero.status_code == 422

        res_neg = client.put(
            "/goal",
            json={"title": "Neg Goal", "target_amount": "-5000", "target_date": future_date},
        )
        assert res_neg.status_code == 422

    def test_put_goal_rejects_empty_or_whitespace_title(self, client: TestClient):
        client.put("/profile", json={"monthly_take_home_income": "100000.00"})
        future_date = (date.today() + timedelta(days=100)).isoformat()

        res_empty = client.put(
            "/goal",
            json={"title": "   ", "target_amount": "10000", "target_date": future_date},
        )
        assert res_empty.status_code == 422

    def test_put_goal_rejects_negative_requested_allocated_savings(self, client: TestClient):
        client.put("/profile", json={"monthly_take_home_income": "100000.00"})
        future_date = (date.today() + timedelta(days=100)).isoformat()

        res = client.put(
            "/goal",
            json={
                "title": "Test Goal",
                "target_amount": "10000",
                "target_date": future_date,
                "requested_allocated_savings": "-100",
            },
        )
        assert res.status_code == 422

    def test_profile_update_syncs_goal_allocation_capping(self, client: TestClient):
        # 1. Profile with 6L savings, 2L reserve -> 4L unencumbered
        client.put(
            "/profile",
            json={"existing_savings": "600000.00", "emergency_reserve": "200000.00"},
        )
        future_date = (date.today() + timedelta(days=365)).isoformat()

        # 2. Goal requests 3L (within 4L -> uncapped)
        res_g = client.put(
            "/goal",
            json={
                "title": "Bike Purchase",
                "target_amount": "500000.00",
                "target_date": future_date,
                "requested_allocated_savings": "300000.00",
            },
        )
        assert res_g.json()["is_allocation_capped"] is False
        assert res_g.json()["permitted_allocated_savings_paise"] == 30000000

        # 3. User increases reserve to 4L -> unencumbered drops to 2L
        client.put("/profile", json={"emergency_reserve": "400000.00"})

        # 4. Check active goal: permitted allocation was automatically capped at 2L!
        goal_res = client.get("/goal")
        assert goal_res.status_code == 200
        assert goal_res.json()["is_allocation_capped"] is True
        assert goal_res.json()["permitted_allocated_savings_paise"] == 20000000


# ==============================================================================
# FEASIBILITY API TESTS
# ==============================================================================


class TestFeasibilityAPI:
    """Verify GET /goal/feasibility calculations, statuses, and validation."""

    def test_feasibility_missing_profile_returns_404(self, client: TestClient):
        res = client.get("/goal/feasibility")
        assert res.status_code == 404
        assert "Financial profile not configured" in res.json()["detail"]

    def test_feasibility_missing_goal_returns_404(self, client: TestClient):
        client.put("/profile", json={"monthly_take_home_income": "100000.00"})
        res = client.get("/goal/feasibility")
        assert res.status_code == 404
        assert "No active financial goal found" in res.json()["detail"]

    def test_feasibility_complete_profile_feasible(self, client: TestClient):
        # Profile: Income ₹1,50,000; Fixed ₹40,000; Living ₹30,000; Disc ₹20,000 -> Surplus ₹60,000
        # Savings ₹6,00,000; Reserve ₹3,00,000 -> Unencumbered ₹3,00,000
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "600000.00",
                "emergency_reserve": "300000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        ref_date = date(2026, 10, 1)
        target_date = date(2027, 10, 1)  # 12 months ahead
        # Target: ₹7,00,000, Upfront: ₹1,00,000 -> Funding gap: ₹6,00,000
        # Required monthly savings = 6,00,000 / 12 = ₹50,000 <= Surplus ₹60,000 -> FEASIBLE!
        client.put(
            "/goal",
            json={
                "title": "Master's Degree",
                "target_amount": "700000.00",
                "target_date": target_date.isoformat(),
                "requested_allocated_savings": "100000.00",
            },
        )

        res = client.get(f"/goal/feasibility?current_date={ref_date.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Master's Degree"
        assert data["feasibility_status"] == "FEASIBLE"
        assert data["target_amount_paise"] == 70000000
        assert data["requested_allocated_savings_paise"] == 10000000
        assert data["permitted_allocated_savings_paise"] == 10000000
        assert data["is_allocation_capped"] is False
        assert data["net_funding_gap_paise"] == 60000000
        assert data["months_remaining"] == 12
        assert data["required_monthly_savings_paise"] == 5000000
        assert data["baseline_monthly_surplus_paise"] == 6000000
        assert data["monthly_buffer_paise"] == 1000000  # Surplus 60k - Required 50k = 10k
        assert data["monthly_shortfall_paise"] == 0
        assert data["required_discretionary_cut_paise"] == 0
        assert data["timeline_basis"]["saving_cycles_count"] == 12
        assert "feasible" in data["actionable_insight"].lower()

    def test_feasibility_stretch_feasible(self, client: TestClient):
        # Profile Surplus ₹60,000; Discretionary ₹20,000; Max potential = ₹80,000
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "600000.00",
                "emergency_reserve": "300000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        ref_date = date(2026, 10, 1)
        target_date = date(2027, 8, 1)  # 10 months ahead
        # Target: ₹7,00,000 with 0 upfront.
        # Required monthly savings = ₹70,000 (exceeds surplus ₹60,000, but <= surplus + disc ₹80,000)
        # -> STRETCH_FEASIBLE
        client.put(
            "/goal",
            json={
                "title": "Car Upgrade",
                "target_amount": "700000.00",
                "target_date": target_date.isoformat(),
                "requested_allocated_savings": "0",
            },
        )

        res = client.get(f"/goal/feasibility?current_date={ref_date.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["feasibility_status"] == "STRETCH_FEASIBLE"
        assert data["required_monthly_savings_paise"] == 7000000
        assert data["baseline_monthly_surplus_paise"] == 6000000
        assert data["monthly_shortfall_paise"] == 0
        assert data["required_discretionary_cut_paise"] == 1000000
        assert "adjustments" in data["actionable_insight"]

    def test_feasibility_infeasible(self, client: TestClient):
        # Profile Surplus ₹60,000; Discretionary ₹20,000; Max potential = ₹80,000
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "600000.00",
                "emergency_reserve": "300000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        ref_date = date(2026, 10, 1)
        target_date = date(2027, 3, 1)  # 5 months ahead
        # Target: ₹10,00,000 with 0 upfront.
        # Required monthly savings = 10,00,000 / 5 = ₹2,00,000 (exceeds ₹80,000) -> INFEASIBLE
        client.put(
            "/goal",
            json={
                "title": "Apartment Deposit",
                "target_amount": "1000000.00",
                "target_date": target_date.isoformat(),
                "requested_allocated_savings": "0",
            },
        )

        res = client.get(f"/goal/feasibility?current_date={ref_date.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["feasibility_status"] == "INFEASIBLE"
        assert data["required_monthly_savings_paise"] == 20000000
        assert data["monthly_shortfall_paise"] == 12000000
        assert "leaves a monthly shortfall" in data["actionable_insight"]

    def test_feasibility_fully_funded_zero_gap(self, client: TestClient):
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "100000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "100000.00",
                "monthly_fixed_commitments": "30000.00",
                "monthly_estimated_living_expenses": "20000.00",
                "monthly_estimated_discretionary": "10000.00",
            },
        )

        future_date = (date.today() + timedelta(days=60)).isoformat()
        # Goal target ₹3L fully covered by ₹3L permitted allocation
        client.put(
            "/goal",
            json={
                "title": "Laptop",
                "target_amount": "300000.00",
                "target_date": future_date,
                "requested_allocated_savings": "300000.00",
            },
        )

        res = client.get("/goal/feasibility")
        assert res.status_code == 200
        data = res.json()
        assert data["feasibility_status"] == "FEASIBLE"
        assert data["net_funding_gap_paise"] == 0
        assert data["required_monthly_savings_paise"] == 0
        assert "fully funded" in data["actionable_insight"].lower()

    def test_feasibility_incomplete_profile_insufficient_data(self, client: TestClient):
        # Profile only has income and savings; missing reserve, fixed, living, disc
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "100000.00",
                "existing_savings": "200000.00",
            },
        )

        future_date = (date.today() + timedelta(days=180)).isoformat()
        client.put(
            "/goal",
            json={
                "title": "Trip to Japan",
                "target_amount": "300000.00",
                "target_date": future_date,
                "requested_allocated_savings": "50000.00",
            },
        )

        res = client.get("/goal/feasibility")
        assert res.status_code == 200
        data = res.json()
        assert data["feasibility_status"] == "INSUFFICIENT_DATA"
        # Never fabricate values: unavailable calculations are null
        assert data["baseline_monthly_surplus_paise"] is None
        assert data["monthly_shortfall_paise"] is None
        assert data["required_discretionary_cut_paise"] is None
        assert len(data["missing_baseline_inputs"]) > 0
        assert "baseline inputs are missing" in data["actionable_insight"]

    def test_feasibility_timeline_in_past_returns_422(self, client: TestClient):
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "200000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        # Goal is created with future target date
        target_date = date(2027, 5, 1)
        client.put(
            "/goal",
            json={
                "title": "Future Goal",
                "target_amount": "200000.00",
                "target_date": target_date.isoformat(),
            },
        )

        # Evaluated from a reference date in 2028 (deadline is in the past relative to current_date)
        eval_date = date(2028, 1, 1)
        res = client.get(f"/goal/feasibility?current_date={eval_date.isoformat()}")
        assert res.status_code == 422
        assert "is in the past compared to current date" in res.json()["detail"]

    def test_feasibility_current_month_unfunded_gap_returns_422(self, client: TestClient):
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "200000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        ref_date = date(2026, 10, 2)
        current_month_target = date(2026, 10, 25)
        # Upfront ₹1L vs Target ₹2L leaves ₹1L unfunded gap in current month
        client.put(
            "/goal",
            json={
                "title": "Immediate Gadget",
                "target_amount": "200000.00",
                "target_date": current_month_target.isoformat(),
                "requested_allocated_savings": "100000.00",
            },
        )

        res = client.get(f"/goal/feasibility?current_date={ref_date.isoformat()}")
        assert res.status_code == 422
        assert "within the current calendar month with an unfunded gap" in res.json()["detail"]
        assert "0 future saving cycles remain" in res.json()["detail"]

    def test_feasibility_current_month_fully_funded_returns_200(self, client: TestClient):
        client.put(
            "/profile",
            json={
                "monthly_take_home_income": "150000.00",
                "existing_savings": "500000.00",
                "emergency_reserve": "200000.00",
                "monthly_fixed_commitments": "40000.00",
                "monthly_estimated_living_expenses": "30000.00",
                "monthly_estimated_discretionary": "20000.00",
            },
        )

        ref_date = date(2026, 10, 2)
        current_month_target = date(2026, 10, 25)
        # Fully funded upfront
        client.put(
            "/goal",
            json={
                "title": "Immediate Gadget Funded",
                "target_amount": "200000.00",
                "target_date": current_month_target.isoformat(),
                "requested_allocated_savings": "200000.00",
            },
        )

        res = client.get(f"/goal/feasibility?current_date={ref_date.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["feasibility_status"] == "FEASIBLE"
        assert data["net_funding_gap_paise"] == 0
        assert data["months_remaining"] == 0
