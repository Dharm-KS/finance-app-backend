from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import Currency, OnboardingStep, RiskTolerance
from app.schemas.common import MoneyOut, PercentOut


class DashboardRisk(BaseModel):
    profile: RiskTolerance
    max_drawdown: PercentOut
    single_stock_limit: PercentOut
    planning_horizon_years: int


class DashboardGoals(BaseModel):
    total: int
    active: int
    completed: int
    at_risk: int


class DashboardConcentration(BaseModel):
    security_name: str
    ticker: str | None
    value: MoneyOut
    percent_of_net_worth: PercentOut | None
    limit_percent: PercentOut | None
    above_limit: bool


class Alert(BaseModel):
    code: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    title: str
    message: str


class DashboardOut(BaseModel):
    currency: Currency
    net_worth: MoneyOut = Field(description="cash + investments + vested equity - debt")
    cash: MoneyOut
    investments: MoneyOut
    equity: MoneyOut = Field(description="Vested equity value")
    unvested_equity: MoneyOut
    debt: MoneyOut
    monthly_emi: MoneyOut
    credit_score: int | None
    emergency_fund_months: PercentOut | None = Field(description="cash_reserve / monthly_spend")
    top_concentration: DashboardConcentration | None
    risk: DashboardRisk | None
    goals: DashboardGoals
    alerts: list[Alert]
    onboarding_step: OnboardingStep
