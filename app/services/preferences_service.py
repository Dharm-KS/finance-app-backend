"""How the twin talks to the user (insight tone + notification switches)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InsightTone
from app.models.preferences import UserPreferences
from app.models.user import User
from app.schemas.preferences import PreferencesIn
from app.services import onboarding_service

DEFAULTS = {"insight_tone": InsightTone.BALANCED, "vesting_alerts": True, "tax_deadline_alerts": True, "weekly_digest": False}


async def _get(db: AsyncSession, user: User) -> UserPreferences | None:
    return (await db.execute(select(UserPreferences).where(UserPreferences.user_id == user.id))).scalar_one_or_none()


def _view(prefs: UserPreferences | None) -> dict:
    if prefs is None:
        return {"is_saved": False, **DEFAULTS, "updated_at": None}
    return {"is_saved": True, **{k: getattr(prefs, k) for k in DEFAULTS}, "updated_at": prefs.updated_at}


async def get_view(db: AsyncSession, user: User) -> dict:
    return _view(await _get(db, user))


async def upsert(db: AsyncSession, user: User, payload: PreferencesIn) -> dict:
    """Fields not sent keep their saved value (or the default on first save)."""
    prefs = await _get(db, user)
    values = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if prefs is None:
        prefs = UserPreferences(user_id=user.id, **(DEFAULTS | values))
        db.add(prefs)
    else:
        for k, v in values.items():
            setattr(prefs, k, v)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    await db.refresh(prefs)
    return _view(prefs)
