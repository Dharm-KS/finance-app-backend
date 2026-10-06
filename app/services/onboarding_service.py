"""Onboarding state machine.

Completion flags are derived from the user's actual data (so the app can always resume at the
right screen) and are *sticky*: once a step is done it stays done. ``current_step`` is the first
incomplete step in :data:`STEP_ORDER`.
"""

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ErrorCode
from app.models.consent import Consent
from app.models.credit_report import CreditReport
from app.models.enums import ConsentStatus, ConsentType, CreditReportStatus, OnboardingStep
from app.models.equity import EquityHolding
from app.models.financial_profile import FinancialProfile
from app.models.goal import FinancialGoal
from app.models.onboarding import Onboarding
from app.models.preferences import UserPreferences
from app.models.risk_profile import RiskProfile
from app.models.user import User

# The calibration screens, in app order. Mobile/OTP comes before (the user exists once it
# succeeds). Name, consent and credit are tracked as flags but don't block onboarding: credit
# data is fetched and used by the backend.
STEP_ORDER: list[tuple[OnboardingStep, str]] = [
    (OnboardingStep.FINANCIAL_PROFILE, "financial_profile_completed"),
    (OnboardingStep.EQUITY, "equity_completed"),
    (OnboardingStep.RISK, "risk_completed"),
    (OnboardingStep.GOALS, "goals_completed"),
    (OnboardingStep.PREFERENCES, "preferences_completed"),
]

SKIPPABLE_STEPS = {OnboardingStep.EQUITY}


async def get_or_create(db: AsyncSession, user: User) -> Onboarding:
    """Return the user's single onboarding row, creating it if missing (race-safe)."""
    stmt = select(Onboarding).where(Onboarding.user_id == user.id)
    onboarding = (await db.execute(stmt)).scalar_one_or_none()
    if onboarding:
        return onboarding
    try:
        async with db.begin_nested():
            onboarding = Onboarding(user_id=user.id, current_step=STEP_ORDER[0][0])
            db.add(onboarding)
    except IntegrityError:
        # Another request created it concurrently (unique user_id) -> use that one.
        onboarding = (await db.execute(stmt)).scalar_one()
    return onboarding


async def _exists(db: AsyncSession, stmt) -> bool:
    return bool((await db.execute(select(exists(stmt)))).scalar())


async def _credit_consent_granted(db: AsyncSession, user_id: int) -> bool:
    latest = (
        await db.execute(
            select(Consent.status)
            .where(Consent.user_id == user_id, Consent.consent_type == ConsentType.CREDIT_REPORT)
            .order_by(Consent.created_at.desc(), Consent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return latest == ConsentStatus.GRANTED


async def refresh(db: AsyncSession, user: User) -> Onboarding:
    """Recalculate flags/current step from data. Caller commits."""
    ob = await get_or_create(db, user)
    uid = user.id

    derived = {
        "registration_completed": bool(user.name),
        "consent_completed": await _credit_consent_granted(db, uid),
        "credit_completed": await _exists(
            db, select(CreditReport.id).where(
                CreditReport.user_id == uid, CreditReport.report_status == CreditReportStatus.SUCCESS
            )
        ),
        "financial_profile_completed": await _exists(db, select(FinancialProfile.id).where(FinancialProfile.user_id == uid)),
        "equity_completed": ob.equity_skipped
        or await _exists(db, select(EquityHolding.id).where(EquityHolding.user_id == uid)),
        "risk_completed": await _exists(db, select(RiskProfile.id).where(RiskProfile.user_id == uid)),
        "goals_completed": (
            await db.execute(select(func.count(FinancialGoal.id)).where(FinancialGoal.user_id == uid))
        ).scalar_one() > 0,
        "preferences_completed": await _exists(db, select(UserPreferences.id).where(UserPreferences.user_id == uid)),
    }
    for attr, value in derived.items():
        setattr(ob, attr, getattr(ob, attr) or value)  # sticky

    ob.current_step = next((step for step, attr in STEP_ORDER if not getattr(ob, attr)), OnboardingStep.COMPLETED)
    ob.onboarding_completed = ob.current_step == OnboardingStep.COMPLETED
    await db.flush()
    return ob


async def get_status(db: AsyncSession, user: User) -> Onboarding:
    ob = await refresh(db, user)
    await db.commit()
    return ob


async def skip_step(db: AsyncSession, user: User, step: OnboardingStep) -> Onboarding:
    if step not in SKIPPABLE_STEPS:
        raise AppError(400, f"Step {step.value} cannot be skipped", ErrorCode.ONBOARDING_STEP_NOT_SKIPPABLE)
    ob = await get_or_create(db, user)
    if step == OnboardingStep.EQUITY:
        ob.equity_skipped = True
    ob = await refresh(db, user)
    await db.commit()
    return ob
