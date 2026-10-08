from enum import Enum

from app.calc.normalize import Frequency  # re-exported for convenience

__all__ = [
    "Frequency", "MaritalStatus", "EmploymentType", "IncomeStability", "TaxRegime", "Relationship",
    "IncomeKind", "Owner", "ExpenseCategory", "ExpenseBucket", "AssetType", "Liquidity",
    "LiabilityType", "PolicyType", "CoverSource", "OnboardingStep",
    "DEFAULT_BUCKET", "DEFAULT_LIQUIDITY",
]


class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"


class EmploymentType(str, Enum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"
    BUSINESS_OWNER = "business_owner"
    FREELANCER = "freelancer"
    NOT_WORKING = "not_working"
    RETIRED = "retired"


class IncomeStability(str, Enum):
    STABLE = "stable"
    VARIABLE = "variable"
    UNCERTAIN = "uncertain"


class TaxRegime(str, Enum):
    OLD = "old"
    NEW = "new"
    UNKNOWN = "unknown"


class Relationship(str, Enum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    OTHER = "other"


class IncomeKind(str, Enum):
    SALARY = "salary"
    BONUS = "bonus"
    BUSINESS = "business"
    FREELANCE = "freelance"
    RENTAL = "rental"
    INTEREST_DIVIDEND = "interest_dividend"
    PENSION = "pension"
    OTHER = "other"


class Owner(str, Enum):
    SELF = "self"
    SPOUSE = "spouse"
    JOINT = "joint"
    OTHER = "other"


class ExpenseBucket(str, Enum):
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"


class ExpenseCategory(str, Enum):
    # Essentials. Loan EMIs live on Liability and personal insurance premiums on
    # InsurancePolicy, so they are deliberately NOT expense categories (no double counting).
    HOUSING = "housing"
    GROCERIES = "groceries"
    UTILITIES = "utilities"
    TRANSPORT = "transport"
    HEALTHCARE = "healthcare"
    CHILDREN = "children"
    EDUCATION = "education"
    FAMILY_SUPPORT = "family_support"
    HOUSEHOLD_HELP = "household_help"
    # Discretionary
    DINING = "dining"
    SHOPPING = "shopping"
    TRAVEL = "travel"
    ENTERTAINMENT = "entertainment"
    SUBSCRIPTIONS = "subscriptions"
    PERSONAL_CARE = "personal_care"
    GIFTS_DONATIONS = "gifts_donations"
    OTHER = "other"


DEFAULT_BUCKET = {
    ExpenseCategory.HOUSING: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.GROCERIES: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.UTILITIES: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.TRANSPORT: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.HEALTHCARE: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.CHILDREN: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.EDUCATION: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.FAMILY_SUPPORT: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.HOUSEHOLD_HELP: ExpenseBucket.ESSENTIAL,
    ExpenseCategory.DINING: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.SHOPPING: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.TRAVEL: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.ENTERTAINMENT: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.SUBSCRIPTIONS: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.PERSONAL_CARE: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.GIFTS_DONATIONS: ExpenseBucket.DISCRETIONARY,
    ExpenseCategory.OTHER: ExpenseBucket.DISCRETIONARY,
}


class AssetType(str, Enum):
    CASH = "cash"
    SAVINGS_ACCOUNT = "savings_account"
    FIXED_DEPOSIT = "fixed_deposit"
    MUTUAL_FUND = "mutual_fund"
    DIRECT_EQUITY = "direct_equity"
    EPF = "epf"
    PPF = "ppf"
    NPS = "nps"
    GOLD = "gold"
    REAL_ESTATE = "real_estate"
    BUSINESS = "business"
    OTHER = "other"


class Liquidity(str, Enum):
    IMMEDIATE = "immediate"        # usable today (cash, savings)
    SHORT_TERM = "short_term"      # days, small penalty (FDs)
    MARKET_LINKED = "market_linked"  # sellable, value fluctuates (MF, equity, gold)
    LOCKED = "locked"              # retirement/lock-in (EPF, PPF, NPS)
    ILLIQUID = "illiquid"          # property, business


DEFAULT_LIQUIDITY = {
    AssetType.CASH: Liquidity.IMMEDIATE,
    AssetType.SAVINGS_ACCOUNT: Liquidity.IMMEDIATE,
    AssetType.FIXED_DEPOSIT: Liquidity.SHORT_TERM,
    AssetType.MUTUAL_FUND: Liquidity.MARKET_LINKED,
    AssetType.DIRECT_EQUITY: Liquidity.MARKET_LINKED,
    AssetType.GOLD: Liquidity.MARKET_LINKED,
    AssetType.EPF: Liquidity.LOCKED,
    AssetType.PPF: Liquidity.LOCKED,
    AssetType.NPS: Liquidity.LOCKED,
    AssetType.REAL_ESTATE: Liquidity.ILLIQUID,
    AssetType.BUSINESS: Liquidity.ILLIQUID,
    AssetType.OTHER: Liquidity.ILLIQUID,
}


class LiabilityType(str, Enum):
    HOME_LOAN = "home_loan"
    CAR_LOAN = "car_loan"
    PERSONAL_LOAN = "personal_loan"
    EDUCATION_LOAN = "education_loan"
    CREDIT_CARD = "credit_card"
    GOLD_LOAN = "gold_loan"
    OTHER = "other"


class PolicyType(str, Enum):
    HEALTH = "health"
    TERM_LIFE = "term_life"
    OTHER_LIFE = "other_life"
    CRITICAL_ILLNESS = "critical_illness"
    PERSONAL_ACCIDENT = "personal_accident"
    DISABILITY = "disability"


class CoverSource(str, Enum):
    EMPLOYER = "employer"
    PERSONAL = "personal"


class OnboardingStep(str, Enum):
    PROFILE = "profile"
    INCOME = "income"
    EXPENSES = "expenses"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    INSURANCE = "insurance"
