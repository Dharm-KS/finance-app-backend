from app.core.config import settings
from app.services.providers.credit.base import (
    CreditAccountData,
    CreditProvider,
    CreditProviderError,
    CreditReportData,
    CreditSubject,
)
from app.services.providers.credit.dummy import DummyCreditProvider


def get_credit_provider() -> CreditProvider:
    """Factory used as a FastAPI dependency. Add ``"cibil": CibilProvider`` here later."""
    providers: dict[str, type[CreditProvider]] = {"dummy": DummyCreditProvider}
    try:
        return providers[settings.CREDIT_PROVIDER.lower()]()
    except KeyError:
        raise RuntimeError(f"Unknown CREDIT_PROVIDER '{settings.CREDIT_PROVIDER}'")


__all__ = [
    "CreditAccountData",
    "CreditProvider",
    "CreditProviderError",
    "CreditReportData",
    "CreditSubject",
    "DummyCreditProvider",
    "get_credit_provider",
]
