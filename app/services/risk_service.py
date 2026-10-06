from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ErrorCode, NotFoundError
from app.models.risk_profile import RiskProfile
from app.models.user import User
from app.schemas.risk import RiskProfileIn
from app.services import onboarding_service


async def get_profile(db: AsyncSession, user: User) -> RiskProfile | None:
    return (await db.execute(select(RiskProfile).where(RiskProfile.user_id == user.id))).scalar_one_or_none()


async def require_profile(db: AsyncSession, user: User) -> RiskProfile:
    profile = await get_profile(db, user)
    if profile is None:
        raise NotFoundError("Risk profile has not been set yet", ErrorCode.RISK_PROFILE_NOT_FOUND)
    return profile


async def upsert(db: AsyncSession, user: User, payload: RiskProfileIn) -> RiskProfile:
    profile = await get_profile(db, user)
    values = payload.model_dump()
    if profile is None:
        profile = RiskProfile(user_id=user.id, **values)
        db.add(profile)
    else:
        for k, v in values.items():
            setattr(profile, k, v)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    await db.refresh(profile)
    return profile
