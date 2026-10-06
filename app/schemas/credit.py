from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import CreditAccountStatus, CreditAccountType, CreditProviderName, CreditReportStatus
from app.schemas.common import MoneyOut, ORMModel, PercentOut


class CreditAccountOut(ORMModel):
    id: int
    account_type: CreditAccountType
    lender_name: str
    account_number_masked: str
    sanctioned_amount: MoneyOut
    current_balance: MoneyOut
    credit_limit: MoneyOut | None
    emi_amount: MoneyOut | None
    interest_rate: PercentOut | None
    tenure_months: int | None
    remaining_months: int | None
    account_status: CreditAccountStatus
    dpd: int = Field(description="Highest days-past-due in payment history")
    opened_date: date | None
    closed_date: date | None


class CreditSummaryOut(BaseModel):
    active_accounts: int
    total_accounts: int
    total_outstanding: MoneyOut
    total_monthly_emi: MoneyOut
    credit_card_utilization_percent: PercentOut | None
    max_dpd: int


class CreditReportOut(ORMModel):
    id: int
    provider: CreditProviderName
    report_type: str
    report_reference: str
    credit_score: int | None
    score_date: date | None
    report_date: date | None
    report_status: CreditReportStatus
    created_at: datetime
    summary: CreditSummaryOut
    accounts: list[CreditAccountOut]
