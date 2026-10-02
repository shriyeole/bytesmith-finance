"""Tests for SQLite persistence, UserProfile, and FinancialGoal models."""

from datetime import date
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.goal import FinancialGoal
from app.models.profile import DEFAULT_USER_ID, UserProfile
from app.models.repository import (
    get_active_goal,
    get_profile,
    upsert_active_goal,
    upsert_profile,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database and session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


class TestDatabaseSchema:
    """Verify table creation and schema definitions."""

    def test_tables_created_in_metadata(self, db_session: Session):
        table_names = Base.metadata.tables.keys()
        assert "user_profiles" in table_names
        assert "financial_goals" in table_names


class TestUserProfilePersistence:
    """Verify profile storage, nullable fields, and explicit zeroes."""

    def test_create_complete_profile(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=60000000,
            emergency_reserve_paise=30000000,
            monthly_fixed_commitments_paise=4500000,
            monthly_estimated_living_expenses_paise=2500000,
            monthly_estimated_discretionary_paise=2000000,
            currency="INR",
        )
        db_session.add(profile)
        db_session.commit()

        fetched = db_session.get(UserProfile, DEFAULT_USER_ID)
        assert fetched is not None
        assert fetched.monthly_take_home_income_paise == 15000000
        assert fetched.existing_savings_paise == 60000000
        assert fetched.emergency_reserve_paise == 30000000
        assert fetched.unencumbered_savings_paise == 30000000
        assert fetched.monthly_estimated_living_expenses_paise == 2500000
        assert fetched.monthly_estimated_discretionary_paise == 2000000
        assert fetched.is_complete is True

    def test_partially_completed_profile_only_income(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=15000000,
        )
        db_session.add(profile)
        db_session.commit()

        fetched = db_session.get(UserProfile, DEFAULT_USER_ID)
        assert fetched is not None
        assert fetched.monthly_take_home_income_paise == 15000000
        assert fetched.existing_savings_paise is None
        assert fetched.emergency_reserve_paise is None
        assert fetched.monthly_fixed_commitments_paise is None
        assert fetched.monthly_estimated_living_expenses_paise is None
        assert fetched.monthly_estimated_discretionary_paise is None
        assert fetched.is_complete is False
        assert fetched.unencumbered_savings_paise == 0

    def test_zero_income_profile_not_complete(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=0,  # Zero income is not complete
            existing_savings_paise=50000000,
            emergency_reserve_paise=20000000,
            monthly_fixed_commitments_paise=10000000,
            monthly_estimated_living_expenses_paise=0,
            monthly_estimated_discretionary_paise=0,
        )
        assert profile.is_complete is False

    def test_missing_savings_reserve_fixed_commitments_not_complete(self, db_session: Session):
        # Missing savings
        p1 = UserProfile(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=None,
            emergency_reserve_paise=20000000,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=2000000,
            monthly_estimated_discretionary_paise=1000000,
        )
        assert p1.is_complete is False

        # Missing emergency reserve
        p2 = UserProfile(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=50000000,
            emergency_reserve_paise=None,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=2000000,
            monthly_estimated_discretionary_paise=1000000,
        )
        assert p2.is_complete is False

        # Missing fixed commitments
        p3 = UserProfile(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=50000000,
            emergency_reserve_paise=20000000,
            monthly_fixed_commitments_paise=None,
            monthly_estimated_living_expenses_paise=2000000,
            monthly_estimated_discretionary_paise=1000000,
        )
        assert p3.is_complete is False

    def test_explicit_zero_expenses_preserved_as_zero_and_complete(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=20000000,
            emergency_reserve_paise=10000000,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=0,  # Explicit zero
            monthly_estimated_discretionary_paise=0,    # Explicit zero
            currency="INR",
        )
        db_session.add(profile)
        db_session.commit()

        fetched = db_session.get(UserProfile, DEFAULT_USER_ID)
        assert fetched is not None
        assert fetched.monthly_estimated_living_expenses_paise == 0
        assert fetched.monthly_estimated_discretionary_paise == 0
        assert fetched.is_complete is True

    def test_negative_values_make_profile_incomplete(self, db_session: Session):
        profile = UserProfile(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=20000000,
            emergency_reserve_paise=-1000,  # Negative
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=0,
            monthly_estimated_discretionary_paise=0,
        )
        assert profile.is_complete is False

    def test_unencumbered_savings_floor_at_zero(self, db_session: Session):
        # When existing savings are less than emergency reserve
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=20000000,
            emergency_reserve_paise=30000000,  # reserve > savings
            monthly_fixed_commitments_paise=3000000,
        )
        assert profile.unencumbered_savings_paise == 0

    def test_unencumbered_savings_with_none_savings(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            existing_savings_paise=None,
            emergency_reserve_paise=10000000,
        )
        assert profile.unencumbered_savings_paise == 0

    def test_upsert_profile_updates_in_place_and_preserves_unset_fields(self, db_session: Session):
        # Initial partial creation: income and savings only
        upsert_profile(
            session=db_session,
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=20000000,
        )
        db_session.commit()

        p = get_profile(db_session, DEFAULT_USER_ID)
        assert p is not None
        assert p.monthly_take_home_income_paise == 10000000
        assert p.existing_savings_paise == 20000000
        assert p.emergency_reserve_paise is None
        assert p.is_complete is False

        # Granular update: set emergency reserve and living expenses, leaving income/savings untouched
        upsert_profile(
            session=db_session,
            emergency_reserve_paise=10000000,
            monthly_estimated_living_expenses_paise=2500000,
        )
        db_session.commit()

        p_updated = get_profile(db_session, DEFAULT_USER_ID)
        assert p_updated.monthly_take_home_income_paise == 10000000  # Preserved!
        assert p_updated.existing_savings_paise == 20000000          # Preserved!
        assert p_updated.emergency_reserve_paise == 10000000         # Updated!
        assert p_updated.monthly_estimated_living_expenses_paise == 2500000  # Updated!
        assert p_updated.monthly_estimated_discretionary_paise is None

        # Confirm only one profile exists
        profiles = db_session.scalars(select(UserProfile)).all()
        assert len(profiles) == 1

    def test_upsert_profile_explicit_none_and_zero_behavior(self, db_session: Session):
        """Verify: omitted fields preserve existing values; None clears; 0 stores zero."""
        # 1. Start with full values
        upsert_profile(
            session=db_session,
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=50000000,
            emergency_reserve_paise=20000000,
            monthly_fixed_commitments_paise=4000000,
            monthly_estimated_living_expenses_paise=2500000,
            monthly_estimated_discretionary_paise=2000000,
        )
        db_session.commit()

        # 2. Omitted fields preserve existing values
        upsert_profile(
            session=db_session,
            monthly_take_home_income_paise=18000000,
        )
        db_session.commit()
        p = get_profile(db_session, DEFAULT_USER_ID)
        assert p.monthly_take_home_income_paise == 18000000
        assert p.existing_savings_paise == 50000000
        assert p.monthly_estimated_living_expenses_paise == 2500000
        assert p.monthly_estimated_discretionary_paise == 2000000

        # 3. Explicitly passing None clears a nullable field
        upsert_profile(
            session=db_session,
            monthly_estimated_living_expenses_paise=None,
        )
        db_session.commit()
        p = get_profile(db_session, DEFAULT_USER_ID)
        assert p.monthly_estimated_living_expenses_paise is None
        assert p.monthly_estimated_discretionary_paise == 2000000

        # 4. Explicitly passing 0 stores zero
        upsert_profile(
            session=db_session,
            monthly_estimated_living_expenses_paise=0,
            monthly_estimated_discretionary_paise=0,
        )
        db_session.commit()
        p = get_profile(db_session, DEFAULT_USER_ID)
        assert p.monthly_estimated_living_expenses_paise == 0
        assert p.monthly_estimated_discretionary_paise == 0



class TestFinancialGoalPersistence:
    """Verify goal persistence, active goal constraints, and relationships."""

    @pytest.fixture(autouse=True)
    def setup_profile(self, db_session: Session):
        profile = UserProfile(
            id=DEFAULT_USER_ID,
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=60000000,
            emergency_reserve_paise=30000000,
            monthly_fixed_commitments_paise=4500000,
        )
        db_session.add(profile)
        db_session.commit()

    def test_create_and_link_goal_to_profile(self, db_session: Session):
        goal = FinancialGoal(
            id="goal_car",
            user_id=DEFAULT_USER_ID,
            title="Buy Sedan Car",
            target_amount_paise=150000000,
            target_date=date(2027, 10, 31),
            requested_allocated_savings_paise=30000000,
            permitted_allocated_savings_paise=30000000,
            is_allocation_capped=False,
            status="ACTIVE",
        )
        db_session.add(goal)
        db_session.commit()

        fetched_goal = db_session.get(FinancialGoal, "goal_car")
        assert fetched_goal is not None
        assert fetched_goal.title == "Buy Sedan Car"
        assert fetched_goal.net_funding_gap_paise == 120000000
        assert fetched_goal.user.id == DEFAULT_USER_ID

        # Relationship navigation
        profile = db_session.get(UserProfile, DEFAULT_USER_ID)
        assert len(profile.goals) == 1
        assert profile.goals[0].id == "goal_car"

    def test_rejects_multiple_active_goals_via_unique_index(self, db_session: Session):
        goal1 = FinancialGoal(
            id="goal_1",
            user_id=DEFAULT_USER_ID,
            title="First Goal",
            target_amount_paise=50000000,
            target_date=date(2027, 5, 1),
            status="ACTIVE",
        )
        db_session.add(goal1)
        db_session.commit()

        # Attempt to add a second ACTIVE goal for the same user
        goal2 = FinancialGoal(
            id="goal_2",
            user_id=DEFAULT_USER_ID,
            title="Second Active Goal",
            target_amount_paise=80000000,
            target_date=date(2027, 8, 1),
            status="ACTIVE",
        )
        db_session.add(goal2)

        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_allows_multiple_archived_or_completed_goals(self, db_session: Session):
        goal_archived = FinancialGoal(
            id="goal_archived",
            user_id=DEFAULT_USER_ID,
            title="Old Archived Goal",
            target_amount_paise=20000000,
            target_date=date(2025, 1, 1),
            status="ARCHIVED",
        )
        goal_completed = FinancialGoal(
            id="goal_completed",
            user_id=DEFAULT_USER_ID,
            title="Completed Goal",
            target_amount_paise=30000000,
            target_date=date(2026, 1, 1),
            status="COMPLETED",
        )
        goal_active = FinancialGoal(
            id="goal_active",
            user_id=DEFAULT_USER_ID,
            title="Current Active Goal",
            target_amount_paise=150000000,
            target_date=date(2027, 10, 1),
            status="ACTIVE",
        )
        db_session.add_all([goal_archived, goal_completed, goal_active])
        db_session.commit()

        active = get_active_goal(db_session, DEFAULT_USER_ID)
        assert active is not None
        assert active.id == "goal_active"

    def test_upsert_active_goal_maintains_single_active_goal(self, db_session: Session):
        # 1. First upsert
        goal = upsert_active_goal(
            session=db_session,
            title="Initial Goal",
            target_amount_paise=100000000,
            target_date=date(2027, 6, 1),
            requested_allocated_savings_paise=20000000,
            permitted_allocated_savings_paise=20000000,
            is_allocation_capped=False,
        )
        db_session.commit()
        initial_id = goal.id

        # 2. Second upsert updates the existing active goal
        updated_goal = upsert_active_goal(
            session=db_session,
            title="Updated Goal Title",
            target_amount_paise=120000000,
            target_date=date(2027, 9, 1),
            requested_allocated_savings_paise=30000000,
            permitted_allocated_savings_paise=25000000,
            is_allocation_capped=True,
        )
        db_session.commit()

        assert updated_goal.id == initial_id
        assert updated_goal.title == "Updated Goal Title"
        assert updated_goal.target_amount_paise == 120000000
        assert updated_goal.is_allocation_capped is True

        # Confirm only one active goal exists in the table
        all_goals = db_session.scalars(select(FinancialGoal)).all()
        assert len(all_goals) == 1

    def test_foreign_key_constraint_prevents_orphan_goal(self, db_session: Session):
        orphan_goal = FinancialGoal(
            id="orphan_goal",
            user_id="non_existent_user_id",
            title="Orphan Goal",
            target_amount_paise=50000000,
            target_date=date(2027, 5, 1),
            status="ACTIVE",
        )
        db_session.add(orphan_goal)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
