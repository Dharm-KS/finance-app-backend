from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Currency, EmploymentType
from app.schemas.common import Money, MoneyOut


class FinancialProfileIn(BaseModel):
    """"Your money today" screen.

    The screen sends the first four fields. The rest are optional: a field that is not sent
    keeps its saved value (on the first save: `monthly_emi` / `total_debt` come from the
    credit report when available, everything else 0 / empty).
    """

    annual_income: Money = Field(description="Pre-tax: salary, bonus and cash incentives")
    monthly_spend: Money = Field(description="Everything that leaves the account each month, including EMIs")
    cash_reserve: Money = Field(description="Cash reachable within a day")
    currency: Currency = Field(default=Currency.INR, description="Reporting currency")

    monthly_emi: Money | None = None
    total_debt: Money | None = None
    investments: Money | None = None
    employment_type: EmploymentType | None = None
    age: int | None = Field(default=None, ge=18, le=100)
    dependents: int | None = Field(default=None, ge=0, le=20)
    insurance_cover: Money | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "annual_income": 6000000,
                "monthly_spend": 260000,
                "cash_reserve": 1850000,
                "currency": "INR",
            }
        }
    )


class FinancialProfileData(BaseModel):
    annual_income: MoneyOut | None
    currency: Currency
    monthly_spend: MoneyOut | None
    cash_reserve: MoneyOut | None
    monthly_emi: MoneyOut | None
    total_debt: MoneyOut | None
    investments: MoneyOut | None
    employment_type: EmploymentType | None
    age: int | None
    dependents: int | None
    insurance_cover: MoneyOut | None


class MoneySummary(BaseModel):
    """The two tiles under the Money form."""

    monthly_surplus: MoneyOut | None = Field(description="annual_income / 12 - monthly_spend (can be negative)")
    runway_months: MoneyOut | None = Field(description="cash_reserve / monthly_spend, 1 decimal")


class FinancialProfileOut(BaseModel):
    is_saved: bool = Field(description="False when nothing is saved yet and values are only suggestions")
    profile: FinancialProfileData
    summary: MoneySummary
    prefilled_fields: list[str] = Field(
        description="Fields whose value was suggested from the credit report (user can edit them)"
    )
    prefill_source: str | None = Field(description="e.g. CREDIT_REPORT")
    updated_at: datetime | None
