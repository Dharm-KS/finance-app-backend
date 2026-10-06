"""Seed realistic test data by driving the real service layer.

Usage::

    python -m app.seed.dummy_data            # create seed users (skips ones that exist)
    python -m app.seed.dummy_data --reset    # delete the seed users first, then recreate

Seed users (log in with OTP 123456):

    +919876543210  Aarav Sharma  credit 780  onboarding COMPLETED (6 goals, concentration above limit)
    +919876543215  Priya Nair    credit 692  stopped before EQUITY  (tests resume)
    +919876543218  Rohan Verma   credit 615  credit fetched, next step FINANCIAL_PROFILE

The three dummy credit profiles themselves live in
``app/services/providers/credit/dummy.py`` and are assigned by the last digit of the mobile.
"""

import argparse
import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal, engine
from app.models import User
from app.models.enums import (
    ConsentStatus,
    ConsentType,
    Currency,
    EmploymentType,
    GoalType,
    InsightTone,
    RiskTolerance,
    UserStatus,
)
from app.schemas.equity import EquityCreate
from app.schemas.financial import FinancialProfileIn
from app.schemas.goal import GoalSelectionIn, GoalSelectionItem
from app.schemas.preferences import PreferencesIn
from app.schemas.risk import RiskProfileIn
from app.services import (
    consent_service,
    credit_service,
    equity_service,
    financial_service,
    goal_service,
    onboarding_service,
    preferences_service,
    risk_service,
)
from app.services.otp_service import ClientInfo
from app.services.providers.credit import DummyCreditProvider

CLIENT = ClientInfo(ip_address="127.0.0.1", user_agent="seed-script")
D = Decimal

SEED_USERS = [
    {"mobile": "+919876543210", "name": "Aarav Sharma", "email": "aarav.sharma@example.com", "stage": "COMPLETED"},
    {"mobile": "+919876543215", "name": "Priya Nair", "email": "priya.nair@example.com", "stage": "FINANCIAL_PROFILE"},
    {"mobile": "+919876543218", "name": "Rohan Verma", "email": None, "stage": "CREDIT"},
]

FINANCIAL_PROFILES = {
    "+919876543210": dict(
        annual_income=D("3600000"), currency=Currency.INR, monthly_spend=D("65000"), cash_reserve=D("450000"),
        monthly_emi=D("27950"), total_debt=D("682000"), investments=D("1200000"),
        employment_type=EmploymentType.SALARIED, age=32, dependents=1, insurance_cover=D("10000000"),
    ),
    "+919876543215": dict(
        annual_income=D("1500000"), currency=Currency.INR, monthly_spend=D("55000"), cash_reserve=D("120000"),
        monthly_emi=D("13550"), total_debt=D("265000"), investments=D("380000"),
        employment_type=EmploymentType.SALARIED, age=28, dependents=0,
    ),
}


async def _reset(db) -> None:
    mobiles = [u["mobile"] for u in SEED_USERS]
    await db.execute(delete(User).where(User.mobile.in_(mobiles)))
    await db.commit()
    print("Deleted existing seed users")


async def _seed_user(db, spec: dict) -> None:
    existing = (await db.execute(select(User).where(User.mobile == spec["mobile"]))).scalar_one_or_none()
    if existing:
        print(f"  skip {spec['mobile']} (already exists)")
        return

    user = User(mobile=spec["mobile"], name=spec["name"], email=spec["email"], is_verified=True, status=UserStatus.ACTIVE)
    db.add(user)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()

    # Screen 3 - consent
    for ctype in (ConsentType.DATA_PROCESSING, ConsentType.CREDIT_REPORT, ConsentType.FINANCIAL_ANALYSIS):
        await consent_service.record(
            db, user, consent_type=ctype, version="v1", status=ConsentStatus.GRANTED, client=CLIENT
        )

    # Screen 4 - credit report (dummy bureau; profile chosen by last digit of mobile)
    await credit_service.fetch_report(db, user, DummyCreditProvider())
    if spec["stage"] == "CREDIT":
        _done(user)
        return

    # Screen 5 - your money
    await financial_service.upsert_profile(db, user, FinancialProfileIn(**FINANCIAL_PROFILES[spec["mobile"]]))
    if spec["stage"] == "FINANCIAL_PROFILE":
        _done(user)
        return

    # Screen 6 - equity
    await equity_service.create(db, user, EquityCreate(
        employer_name="Acme Technologies", security_name="Acme Technologies Inc.", ticker="ACME",
        vested_value=D("2500000"), unvested_value=D("1200000"), currency=Currency.INR, as_of_date=date(2026, 9, 30),
    ))
    await equity_service.create(db, user, EquityCreate(
        employer_name="Acme Technologies", security_name="Acme Technologies Inc. (ESPP)", ticker="ACME",
        vested_value=D("150000"), unvested_value=D("0"), currency=Currency.INR, as_of_date=date(2026, 9, 30),
    ))

    # Screen 7 - risk
    await risk_service.upsert(db, user, RiskProfileIn(
        risk_tolerance=RiskTolerance.BALANCED, max_drawdown_percent=D("18"),
        single_stock_limit_percent=D("35"), planning_horizon_years=10,
    ))

    # Screen 8 - goals (the ticked cards)
    await goal_service.save_selection(db, user, GoalSelectionIn(goals=[
        GoalSelectionItem(goal_type=GoalType.EMERGENCY_FUND),
        GoalSelectionItem(goal_type=GoalType.EQUITY_TAX_RESERVE),
        GoalSelectionItem(goal_type=GoalType.REDUCE_SINGLE_STOCK_CONCENTRATION),
        GoalSelectionItem(goal_type=GoalType.RETIREMENT_CORPUS),
        GoalSelectionItem(goal_type=GoalType.CLEAR_HIGH_INTEREST_DEBT),
        GoalSelectionItem(goal_type=GoalType.PROTECTION_TOPUP),
    ]))

    # Screen 9 - preferences
    await preferences_service.upsert(db, user, PreferencesIn(
        insight_tone=InsightTone.BALANCED, vesting_alerts=True, tax_deadline_alerts=True, weekly_digest=False,
    ))
    _done(user)


def _done(user: User) -> None:
    print(f"  created {user.mobile} ({user.name})")


async def main(reset: bool) -> None:
    async with AsyncSessionLocal() as db:
        if reset:
            await _reset(db)
        print("Seeding users...")
        for spec in SEED_USERS:
            await _seed_user(db, spec)
        print("\nOnboarding state:")
        for spec in SEED_USERS:
            user = (await db.execute(select(User).where(User.mobile == spec["mobile"]))).scalar_one()
            ob = await onboarding_service.get_status(db, user)
            print(f"  {user.mobile}  {user.name:<14} next_step={ob.current_step.value}")
    await engine.dispose()
    print("\nDone. Log in with any seed mobile and OTP 123456.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dummy data")
    parser.add_argument("--reset", action="store_true", help="delete seed users before seeding")
    asyncio.run(main(parser.parse_args().reset))
