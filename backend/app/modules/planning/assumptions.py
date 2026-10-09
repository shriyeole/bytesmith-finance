"""Default planning assumptions.

DRAFT — every number here changes projections materially and must be signed off by a
finance reviewer before public launch (spec §16.4). They are surfaced to users with
every projection. M7 will make them versioned and user-overridable.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Tuple

VERSION = "2026.10-draft"


@dataclass(frozen=True)
class Assumptions:
    version: str = VERSION
    general_inflation_bps: int = 600          # 6%
    education_inflation_bps: int = 1000       # 10% — education costs rise faster
    # Expected annual return by months until the goal (asset-class mix gets more
    # conservative as the date approaches). Upper bound in months -> return.
    return_by_horizon: Tuple[Tuple[int, int], ...] = ((24, 600), (84, 800), (180, 1000), (10**6, 1100))
    post_retirement_return_bps: int = 700
    life_expectancy_years: int = 85
    home_down_payment_bps: int = 2000         # 20% of price paid upfront
    home_extra_costs_bps: int = 700           # stamp duty, registration, interiors ~7%
    home_loan_rate_bps: int = 850
    home_loan_months: int = 240
    home_emi_to_income_limit_bps: int = 4000  # EMI above 40% of take-home is a stretch
    on_track_bps: int = 10000                 # projected >= 100% of target
    at_risk_bps: int = 8500                   # projected >= 85% of target
    high_cost_debt_rate_bps: int = 1400
    debt_to_income_caution_bps: int = 3000
    debt_to_income_high_bps: int = 4000
    emergency_months: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        "stable": (3, 6), "variable": (6, 9), "uncertain": (9, 12),
    })
    life_cover_income_multiple: int = 10
    health_cover_single_paise: int = 5_00_000_00     # ₹5L
    health_cover_family_paise: int = 10_00_000_00    # ₹10L
    health_cover_parents_extra_paise: int = 5_00_000_00
    renewal_warning_days: int = 45
    # Wealth simulation (M8)
    salary_growth_bps: int = 700              # used when an income has no expected growth entered
    portfolio_return_bps: int = 900           # invested money before retirement (diversified mix)
    cash_return_bps: int = 400                # savings accounts / deposits
    emergency_buffer_months: int = 6          # surplus tops up cash to this many months of obligations first
    stress_salary_cut_bps: int = 400          # stress: raises 4 points lower (not below 0)
    stress_inflation_add_bps: int = 100       # stress: inflation 1 point higher
    stress_return_cut_bps: int = 200          # stress: returns 2 points lower
    upside_salary_add_bps: int = 300          # upside: raises 3 points higher
    upside_return_add_bps: int = 150          # upside: returns 1.5 points higher
    child_monthly_cost_paise: int = 15_000_00  # what-if "have a child": monthly cost today
    child_education_cost_paise: int = 25_00_000_00  # ... and college at 18, today's money

    def return_for_months(self, months: int) -> int:
        for upper, bps in self.return_by_horizon:
            if months <= upper:
                return bps
        return self.return_by_horizon[-1][1]

    def inflation_for(self, goal_type: str) -> int:
        return self.education_inflation_bps if goal_type == "child_education" else self.general_inflation_bps

    def describe(self) -> List[str]:
        bands = ", ".join(
            f"{'up to ' + str(u // 12) + ' yrs' if u < 10**6 else 'longer'}: {b / 100:g}%" for u, b in self.return_by_horizon
        )
        return [
            f"Inflation {self.general_inflation_bps / 100:g}% a year (education {self.education_inflation_bps / 100:g}%).",
            f"Expected returns by time to goal — {bands}.",
            f"After retirement: {self.post_retirement_return_bps / 100:g}% return, planning to age {self.life_expectancy_years}.",
            f"Salary growth {self.salary_growth_bps / 100:g}% a year where you have not entered one; invested money earns {self.portfolio_return_bps / 100:g}% before retirement, cash {self.cash_return_bps / 100:g}%.",
            "Returns are assumptions, not guarantees.",
        ]


DEFAULT = Assumptions()


def as_dict(a: Assumptions = DEFAULT) -> dict:
    d = asdict(a)
    d["return_by_horizon"] = [{"up_to_months": u if u < 10**6 else None, "return_bps": b} for u, b in a.return_by_horizon]
    d["emergency_months"] = {k: {"low": v[0], "high": v[1]} for k, v in a.emergency_months.items()}
    d["summary"] = a.describe()
    return d


# ---------------------------------------------------------------- user overrides (M7)
import hashlib  # noqa: E402
import json  # noqa: E402
from dataclasses import replace  # noqa: E402

HORIZON_BANDS = tuple(u for u, _ in DEFAULT.return_by_horizon)

# key -> (min, max) inclusive. return_by_horizon_bps is a list, one value per horizon band.
OVERRIDABLE: Dict[str, Tuple[int, int]] = {
    "general_inflation_bps": (0, 1500),
    "education_inflation_bps": (0, 2000),
    "post_retirement_return_bps": (0, 1500),
    "life_expectancy_years": (60, 105),
    "home_loan_rate_bps": (300, 2000),
    "home_down_payment_bps": (0, 10000),
    "return_by_horizon_bps": (0, 2000),
    "salary_growth_bps": (-2000, 3000),
    "portfolio_return_bps": (0, 2000),
    "cash_return_bps": (0, 1500),
}


def validate_overrides(overrides: dict) -> dict:
    """Return a clean overrides dict or raise ValueError with a readable message."""
    clean: dict = {}
    for key, value in overrides.items():
        if key not in OVERRIDABLE:
            raise ValueError(f"'{key}' cannot be changed.")
        if value is None:
            continue  # null removes an override
        lo, hi = OVERRIDABLE[key]
        values = value if key == "return_by_horizon_bps" else [value]
        if key == "return_by_horizon_bps" and (not isinstance(value, list) or len(value) != len(HORIZON_BANDS)):
            raise ValueError(f"return_by_horizon_bps needs {len(HORIZON_BANDS)} values, one per time band.")
        for v in values:
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise ValueError(f"{key} must be whole numbers between {lo} and {hi}.")
        clean[key] = value
    return clean


def effective(overrides: dict | None) -> Assumptions:
    """Defaults with the user's overrides applied."""
    if not overrides:
        return DEFAULT
    o = dict(overrides)
    changes = {k: v for k, v in o.items() if k != "return_by_horizon_bps"}
    if "return_by_horizon_bps" in o:
        changes["return_by_horizon"] = tuple(zip(HORIZON_BANDS, o["return_by_horizon_bps"]))
    return replace(DEFAULT, version=f"{VERSION}+custom", **changes)


def fingerprint(a: Assumptions) -> str:
    """Stable hash of every assumption value; identical numbers <=> identical hash."""
    payload = json.dumps(as_dict(a) | {"summary": None}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
