"""Import every model here so ``Base.metadata`` is complete (needed by Alembic and tests)."""

from app.models.base import Base
from app.models.consent import Consent
from app.models.credit_account import CreditAccount
from app.models.credit_report import CreditReport
from app.models.equity import EquityHolding
from app.models.financial_profile import FinancialProfile
from app.models.goal import FinancialGoal
from app.models.onboarding import Onboarding
from app.models.otp import OtpSession
from app.models.preferences import UserPreferences
from app.models.risk_profile import RiskProfile
from app.models.user import RevokedToken, User

__all__ = [
    "Base",
    "Consent",
    "CreditAccount",
    "CreditReport",
    "EquityHolding",
    "FinancialGoal",
    "FinancialProfile",
    "Onboarding",
    "OtpSession",
    "RevokedToken",
    "RiskProfile",
    "User",
    "UserPreferences",
]
