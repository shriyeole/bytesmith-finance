"""Pydantic schemas for FinancialGoal API requests and responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Union
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.money import rupees_to_paise
from app.models.goal import FinancialGoal


class GoalUpdateRequest(BaseModel):
    """Request payload for creating or updating the single active financial goal."""

    title: str
    target_date: date
    target_amount: Optional[Union[str, int, Decimal]] = None
    target_amount_paise: Optional[int] = None
    requested_allocated_savings: Optional[Union[str, int, Decimal]] = None
    requested_allocated_savings_paise: Optional[int] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Goal title cannot be empty or whitespace only")
        return trimmed

    @field_validator("target_amount", "requested_allocated_savings", mode="before")
    @classmethod
    def validate_rupee_inputs(cls, v: Any, info) -> Any:
        if v is not None:
            if isinstance(v, bool):
                raise ValueError(f"{info.field_name} cannot be a boolean")
            if isinstance(v, float):
                raise ValueError(f"{info.field_name} must be a decimal string or integer, not float")
        return v

    @field_validator("target_amount_paise", "requested_allocated_savings_paise", mode="before")
    @classmethod
    def validate_paise_inputs(cls, v: Any, info) -> Any:
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{info.field_name} must be an integer")
            if v < 0:
                raise ValueError(f"{info.field_name} cannot be negative")
        return v

    @model_validator(mode="after")
    def validate_amounts(self) -> "GoalUpdateRequest":
        # Validate target_amount
        target_paise = self.get_target_amount_paise()
        if target_paise <= 0:
            raise ValueError("Target amount must be strictly positive")

        # Validate requested_allocated_savings
        req_paise = self.get_requested_allocated_savings_paise()
        if req_paise < 0:
            raise ValueError("Requested allocated savings cannot be negative")

        return self

    def get_target_amount_paise(self) -> int:
        """Resolve target amount into integer paise."""
        if self.target_amount_paise is not None:
            if isinstance(self.target_amount_paise, bool) or not isinstance(self.target_amount_paise, int):
                raise ValueError("target_amount_paise must be an integer")
            return self.target_amount_paise

        if self.target_amount is None:
            raise ValueError("Either target_amount or target_amount_paise must be provided")

        if isinstance(self.target_amount, bool):
            raise ValueError("target_amount cannot be a boolean")
        if isinstance(self.target_amount, float):
            raise ValueError("target_amount must be a decimal string or integer, not float")

        try:
            if isinstance(self.target_amount, int):
                return rupees_to_paise(str(self.target_amount))
            return rupees_to_paise(self.target_amount)
        except Exception as exc:
            raise ValueError(f"Invalid target amount: {exc}") from exc

    def get_requested_allocated_savings_paise(self) -> int:
        """Resolve requested upfront savings allocation into integer paise."""
        if self.requested_allocated_savings_paise is not None:
            if (
                isinstance(self.requested_allocated_savings_paise, bool)
                or not isinstance(self.requested_allocated_savings_paise, int)
            ):
                raise ValueError("requested_allocated_savings_paise must be an integer")
            return self.requested_allocated_savings_paise

        if self.requested_allocated_savings is None:
            return 0

        if isinstance(self.requested_allocated_savings, bool):
            raise ValueError("requested_allocated_savings cannot be a boolean")
        if isinstance(self.requested_allocated_savings, float):
            raise ValueError("requested_allocated_savings must be a decimal string or integer, not float")

        try:
            if isinstance(self.requested_allocated_savings, int):
                return rupees_to_paise(str(self.requested_allocated_savings))
            return rupees_to_paise(self.requested_allocated_savings)
        except Exception as exc:
            raise ValueError(f"Invalid requested allocated savings: {exc}") from exc


class GoalResponse(BaseModel):
    """Response payload for financial goal endpoints."""

    id: str
    user_id: str
    title: str
    target_amount_paise: int
    target_date: date
    requested_allocated_savings_paise: int
    permitted_allocated_savings_paise: Optional[int] = None
    is_allocation_capped: bool = False
    net_funding_gap_paise: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, goal: FinancialGoal) -> "GoalResponse":
        return cls(
            id=goal.id,
            user_id=goal.user_id,
            title=goal.title,
            target_amount_paise=goal.target_amount_paise,
            target_date=goal.target_date,
            requested_allocated_savings_paise=goal.requested_allocated_savings_paise,
            permitted_allocated_savings_paise=goal.permitted_allocated_savings_paise,
            is_allocation_capped=goal.is_allocation_capped,
            net_funding_gap_paise=goal.net_funding_gap_paise,
            status=goal.status,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )
