"""Provider-agnostic credit bureau contract.

Every bureau integration (Dummy today, CIBIL/Experian/... later) returns the same normalised
:class:`CreditReportData`. ``credit_service`` persists it; API routes never see provider details.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.models.enums import CreditAccountStatus, CreditAccountType, CreditProviderName, CreditReportStatus


@dataclass(frozen=True)
class CreditSubject:
    """Identity details sent to the bureau. Add PAN/DOB/address here when integrating CIBIL."""

    user_uuid: str
    mobile: str
    name: str | None


@dataclass
class CreditAccountData:
    account_type: CreditAccountType
    lender_name: str
    account_number_masked: str
    sanctioned_amount: Decimal
    current_balance: Decimal
    account_status: CreditAccountStatus
    dpd: int = 0
    credit_limit: Decimal | None = None
    emi_amount: Decimal | None = None
    interest_rate: Decimal | None = None
    tenure_months: int | None = None
    remaining_months: int | None = None
    opened_date: date | None = None
    closed_date: date | None = None


@dataclass
class CreditReportData:
    provider: CreditProviderName
    report_type: str
    report_reference: str
    report_status: CreditReportStatus
    credit_score: int | None
    score_date: date | None
    report_date: date | None
    accounts: list[CreditAccountData] = field(default_factory=list)
    raw_report: dict[str, Any] | None = None  # untouched provider payload


class CreditProviderError(Exception):
    """Bureau unreachable / returned an error. Mapped to HTTP 503 by the service."""


class CreditProvider(ABC):
    name: CreditProviderName

    @abstractmethod
    async def fetch_report(self, subject: CreditSubject) -> CreditReportData:
        ...
