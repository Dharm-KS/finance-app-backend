"""Domain enums shared by models, schemas and services."""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DELETED = "DELETED"


class OtpPurpose(StrEnum):
    REGISTER = "REGISTER"
    LOGIN = "LOGIN"


class OtpStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    LOCKED = "LOCKED"          # too many wrong attempts
    SUPERSEDED = "SUPERSEDED"  # a newer OTP was requested


class ConsentType(StrEnum):
    CREDIT_REPORT = "CREDIT_REPORT"
    FINANCIAL_ANALYSIS = "FINANCIAL_ANALYSIS"
    DATA_PROCESSING = "DATA_PROCESSING"


class ConsentStatus(StrEnum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


class OnboardingStep(StrEnum):
    REGISTRATION = "REGISTRATION"
    CONSENT = "CONSENT"
    CREDIT = "CREDIT"
    FINANCIAL_PROFILE = "FINANCIAL_PROFILE"
    EQUITY = "EQUITY"
    RISK = "RISK"
    GOALS = "GOALS"
    PREFERENCES = "PREFERENCES"
    COMPLETED = "COMPLETED"


class CreditProviderName(StrEnum):
    DUMMY = "DUMMY"
    CIBIL = "CIBIL"


class CreditReportStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NO_HIT = "NO_HIT"  # bureau has no record for the user


class CreditAccountType(StrEnum):
    PERSONAL_LOAN = "PERSONAL_LOAN"
    HOME_LOAN = "HOME_LOAN"
    AUTO_LOAN = "AUTO_LOAN"
    EDUCATION_LOAN = "EDUCATION_LOAN"
    CONSUMER_LOAN = "CONSUMER_LOAN"
    GOLD_LOAN = "GOLD_LOAN"
    CREDIT_CARD = "CREDIT_CARD"
    OTHER = "OTHER"


class CreditAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    WRITTEN_OFF = "WRITTEN_OFF"
    SETTLED = "SETTLED"


class Currency(StrEnum):
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    SGD = "SGD"
    AED = "AED"


class EmploymentType(StrEnum):
    SALARIED = "SALARIED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    BUSINESS_OWNER = "BUSINESS_OWNER"
    STUDENT = "STUDENT"
    RETIRED = "RETIRED"
    UNEMPLOYED = "UNEMPLOYED"
    OTHER = "OTHER"


class EquitySource(StrEnum):
    MANUAL = "MANUAL"
    # Future: BROKER_API, EMPLOYER_PLAN_API ...


class RiskTolerance(StrEnum):
    STEADY = "STEADY"
    BALANCED = "BALANCED"
    GROWTH = "GROWTH"


class GoalType(StrEnum):
    EMERGENCY_FUND = "EMERGENCY_FUND"
    EQUITY_TAX_RESERVE = "EQUITY_TAX_RESERVE"
    REDUCE_SINGLE_STOCK_CONCENTRATION = "REDUCE_SINGLE_STOCK_CONCENTRATION"
    HOME_DOWN_PAYMENT = "HOME_DOWN_PAYMENT"
    RETIREMENT_CORPUS = "RETIREMENT_CORPUS"
    CHILD_EDUCATION = "CHILD_EDUCATION"
    SABBATICAL_RUNWAY = "SABBATICAL_RUNWAY"
    CLEAR_HIGH_INTEREST_DEBT = "CLEAR_HIGH_INTEREST_DEBT"
    PROTECTION_TOPUP = "PROTECTION_TOPUP"


class GoalCategory(StrEnum):
    """The tag shown on each goal card."""

    ESSENTIAL = "ESSENTIAL"
    PROPERTY = "PROPERTY"
    FAMILY = "FAMILY"
    FREEDOM = "FREEDOM"


class GoalPriority(StrEnum):
    ESSENTIAL = "ESSENTIAL"
    IMPORTANT = "IMPORTANT"
    OPTIONAL = "OPTIONAL"


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"


class InsightTone(StrEnum):
    CONCISE = "CONCISE"
    BALANCED = "BALANCED"
    DETAILED = "DETAILED"
