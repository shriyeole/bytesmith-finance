"""Pydantic schemas for UserProfile API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.feasibility import get_missing_profile_inputs
from app.domain.money import rupees_to_paise
from app.models.profile import UserProfile
from app.models.repository import _UNSET


def _parse_rupee_or_paise(
    val: Any,
    field_name: str,
    paise_val: Optional[int] = None,
) -> Optional[int]:
    """Convert rupee representation or paise integer to validated integer paise.

    Accepts:
    - None -> None
    - int paise (if paise_val provided) -> non-negative integer paise
    - str / Decimal -> rupees_to_paise(val)
    - int -> rupees_to_paise(str(val)) (interpreted as rupees)

    Rejects:
    - bool -> ValueError
    - float -> ValueError
    - negative values -> ValueError
    - malformed decimal strings -> ValueError
    """
    if paise_val is not None:
        if isinstance(paise_val, bool) or not isinstance(paise_val, int):
            raise ValueError(f"{field_name}_paise must be an integer, got {type(paise_val).__name__}")
        if paise_val < 0:
            raise ValueError(f"{field_name}_paise cannot be negative, got {paise_val}")
        return paise_val

    if val is None:
        return None

    if isinstance(val, bool):
        raise ValueError(f"{field_name} cannot be a boolean value")
    if isinstance(val, float):
        raise ValueError(f"{field_name} must be a decimal string or integer, not float")

    try:
        if isinstance(val, int):
            return rupees_to_paise(str(val))
        return rupees_to_paise(val)
    except Exception as exc:
        raise ValueError(f"Invalid monetary value for {field_name}: {exc}") from exc


class ProfileUpdateRequest(BaseModel):
    """Request payload for creating or partially updating a financial profile.

    Accepts rupee values as decimal strings (e.g. "150000.00") or integer paise.
    Omitted fields preserve existing values; explicit null clears the field; explicit 0 stores zero.
    """

    monthly_take_home_income: Optional[Union[str, int, Decimal]] = None
    monthly_take_home_income_paise: Optional[int] = None

    existing_savings: Optional[Union[str, int, Decimal]] = None
    existing_savings_paise: Optional[int] = None

    emergency_reserve: Optional[Union[str, int, Decimal]] = None
    emergency_reserve_paise: Optional[int] = None

    monthly_fixed_commitments: Optional[Union[str, int, Decimal]] = None
    monthly_fixed_commitments_paise: Optional[int] = None

    monthly_estimated_living_expenses: Optional[Union[str, int, Decimal]] = None
    monthly_estimated_living_expenses_paise: Optional[int] = None

    monthly_estimated_discretionary: Optional[Union[str, int, Decimal]] = None
    monthly_estimated_discretionary_paise: Optional[int] = None

    currency: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "monthly_take_home_income",
        "existing_savings",
        "emergency_reserve",
        "monthly_fixed_commitments",
        "monthly_estimated_living_expenses",
        "monthly_estimated_discretionary",
        mode="before",
    )
    @classmethod
    def validate_rupee_fields(cls, v: Any, info) -> Any:
        if v is not None:
            if isinstance(v, bool):
                raise ValueError(f"{info.field_name} cannot be a boolean")
            if isinstance(v, float):
                raise ValueError(f"{info.field_name} must be a decimal string or integer, not float")
            # Run validation through _parse_rupee_or_paise
            _parse_rupee_or_paise(v, info.field_name)
        return v

    @field_validator(
        "monthly_take_home_income_paise",
        "existing_savings_paise",
        "emergency_reserve_paise",
        "monthly_fixed_commitments_paise",
        "monthly_estimated_living_expenses_paise",
        "monthly_estimated_discretionary_paise",
        mode="before",
    )
    @classmethod
    def validate_paise_fields(cls, v: Any, info) -> Any:
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{info.field_name} must be an integer")
            if v < 0:
                raise ValueError(f"{info.field_name} cannot be negative")
        return v

    @model_validator(mode="after")
    def validate_reserve_le_savings_in_payload(self) -> "ProfileUpdateRequest":
        """Validate emergency_reserve <= existing_savings when both fields are in the payload."""
        savings_set = "existing_savings" in self.model_fields_set or "existing_savings_paise" in self.model_fields_set
        reserve_set = "emergency_reserve" in self.model_fields_set or "emergency_reserve_paise" in self.model_fields_set

        if savings_set and reserve_set:
            savings = (
                self.existing_savings_paise
                if self.existing_savings_paise is not None
                else (
                    _parse_rupee_or_paise(self.existing_savings, "existing_savings")
                    if self.existing_savings is not None
                    else None
                )
            )
            reserve = (
                self.emergency_reserve_paise
                if self.emergency_reserve_paise is not None
                else (
                    _parse_rupee_or_paise(self.emergency_reserve, "emergency_reserve")
                    if self.emergency_reserve is not None
                    else None
                )
            )
            if savings is not None and reserve is not None and reserve > savings:
                raise ValueError("Emergency reserve cannot exceed existing savings.")
        return self

    def extract_paise_updates(self) -> dict[str, Any]:
        """Convert incoming fields into the exact argument dictionary for upsert_profile.

        Preserves:
        - Omitted fields -> _UNSET (keeps current stored value)
        - Explicit null -> None (clears nullable field in database)
        - Explicit 0 / positive -> integer paise
        """
        updates: dict[str, Any] = {}
        field_mappings = [
            ("monthly_take_home_income", "monthly_take_home_income_paise"),
            ("existing_savings", "existing_savings_paise"),
            ("emergency_reserve", "emergency_reserve_paise"),
            ("monthly_fixed_commitments", "monthly_fixed_commitments_paise"),
            ("monthly_estimated_living_expenses", "monthly_estimated_living_expenses_paise"),
            ("monthly_estimated_discretionary", "monthly_estimated_discretionary_paise"),
        ]

        for rupee_field, paise_field in field_mappings:
            is_rupee_set = rupee_field in self.model_fields_set
            is_paise_set = paise_field in self.model_fields_set

            if not is_rupee_set and not is_paise_set:
                updates[paise_field] = _UNSET
            else:
                rupee_val = getattr(self, rupee_field)
                paise_val = getattr(self, paise_field)
                if rupee_val is None and paise_val is None:
                    updates[paise_field] = None
                elif paise_val is not None:
                    updates[paise_field] = paise_val
                else:
                    updates[paise_field] = _parse_rupee_or_paise(rupee_val, rupee_field)

        if "currency" in self.model_fields_set:
            updates["currency"] = self.currency if self.currency is not None else "INR"
        else:
            updates["currency"] = _UNSET

        return updates


class ProfileResponse(BaseModel):
    """Response payload for financial profile endpoints."""

    id: str
    monthly_take_home_income_paise: Optional[int] = None
    existing_savings_paise: Optional[int] = None
    emergency_reserve_paise: Optional[int] = None
    monthly_fixed_commitments_paise: Optional[int] = None
    monthly_estimated_living_expenses_paise: Optional[int] = None
    monthly_estimated_discretionary_paise: Optional[int] = None
    unencumbered_savings_paise: int
    manual_baseline_surplus_paise: Optional[int] = None
    is_complete: bool
    missing_fields: List[str]
    currency: str = "INR"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, profile: UserProfile) -> "ProfileResponse":
        """Build ProfileResponse from UserProfile ORM instance with derived baseline surplus."""
        surplus: Optional[int] = None
        if profile.is_complete:
            # Guaranteed non-None when is_complete is True
            income = profile.monthly_take_home_income_paise or 0
            fixed = profile.monthly_fixed_commitments_paise or 0
            living = profile.monthly_estimated_living_expenses_paise or 0
            disc = profile.monthly_estimated_discretionary_paise or 0
            surplus = income - (fixed + living + disc)

        return cls(
            id=profile.id,
            monthly_take_home_income_paise=profile.monthly_take_home_income_paise,
            existing_savings_paise=profile.existing_savings_paise,
            emergency_reserve_paise=profile.emergency_reserve_paise,
            monthly_fixed_commitments_paise=profile.monthly_fixed_commitments_paise,
            monthly_estimated_living_expenses_paise=profile.monthly_estimated_living_expenses_paise,
            monthly_estimated_discretionary_paise=profile.monthly_estimated_discretionary_paise,
            unencumbered_savings_paise=profile.unencumbered_savings_paise,
            manual_baseline_surplus_paise=surplus,
            is_complete=profile.is_complete,
            missing_fields=get_missing_profile_inputs(profile),
            currency=profile.currency,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
