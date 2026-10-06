from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import OnboardingStep
from app.schemas.common import ORMModel


class OnboardingStatusOut(ORMModel):
    current_step: OnboardingStep
    registration_completed: bool
    consent_completed: bool
    credit_completed: bool
    financial_profile_completed: bool
    equity_completed: bool
    equity_skipped: bool
    risk_completed: bool
    goals_completed: bool
    onboarding_completed: bool
    updated_at: datetime


class OnboardingSkipIn(BaseModel):
    step: Literal["EQUITY"]  # only optional steps can be skipped
