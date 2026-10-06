"""Employer equity holdings (manual entry for the MVP)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ErrorCode, NotFoundError
from app.core.time import utctoday
from app.models.enums import Currency, EquitySource
from app.models.equity import EquityHolding
from app.models.financial_profile import FinancialProfile
from app.models.user import User
from app.schemas.equity import EquityCreate, EquityUpdate
from app.services import onboarding_service


async def list_holdings(db: AsyncSession, user: User) -> dict:
    holdings = list(
        (
            await db.execute(
                select(EquityHolding).where(EquityHolding.user_id == user.id).order_by(EquityHolding.id)
            )
        ).scalars()
    )
    return {
        "holdings": holdings,
        "total_vested_value": sum((h.vested_value for h in holdings), Decimal("0")),
        "total_unvested_value": sum((h.unvested_value for h in holdings), Decimal("0")),
    }


async def get_owned(db: AsyncSession, user: User, holding_id: int) -> EquityHolding:
    """Ownership is part of the query: another user's id is indistinguishable from a missing one."""
    holding = (
        await db.execute(
            select(EquityHolding).where(EquityHolding.id == holding_id, EquityHolding.user_id == user.id)
        )
    ).scalar_one_or_none()
    if holding is None:
        raise NotFoundError("Equity holding not found", ErrorCode.EQUITY_HOLDING_NOT_FOUND)
    return holding


async def create(db: AsyncSession, user: User, payload: EquityCreate) -> EquityHolding:
    values = payload.model_dump()
    values["as_of_date"] = values["as_of_date"] or utctoday()
    values["security_name"] = values["security_name"] or values["employer_name"]
    if values["currency"] is None:
        profile = (
            await db.execute(select(FinancialProfile.currency).where(FinancialProfile.user_id == user.id))
        ).scalar_one_or_none()
        values["currency"] = profile or Currency.INR
    holding = EquityHolding(user_id=user.id, source=EquitySource.MANUAL, **values)
    db.add(holding)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    await db.refresh(holding)
    return holding


async def update(db: AsyncSession, user: User, holding_id: int, payload: EquityUpdate) -> EquityHolding:
    holding = await get_owned(db, user, holding_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is None and k not in ("ticker", "next_vest_date"):  # required columns can't be nulled
            continue
        setattr(holding, k, v)
    await db.commit()
    await db.refresh(holding)
    return holding


async def delete(db: AsyncSession, user: User, holding_id: int) -> None:
    holding = await get_owned(db, user, holding_id)
    await db.delete(holding)
    await db.commit()
