"""Financial profile ("Your Money") + the consolidated FinancialSnapshot.

:class:`FinancialSnapshot` is the single read-model of a user's position. Goals, dashboard and
(later) the AI analysis engine consume it instead of querying tables themselves.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_report import CreditReport
from app.models.enums import Currency
from app.models.equity import EquityHolding
from app.models.financial_profile import FinancialProfile
from app.models.risk_profile import RiskProfile
from app.models.user import User
from app.schemas.financial import FinancialProfileIn
from app.services import credit_service, onboarding_service

ZERO = Decimal("0")
PROFILE_FIELDS = (
    "annual_income", "currency", "monthly_spend", "cash_reserve", "monthly_emi", "total_debt",
    "investments", "employment_type", "age", "dependents", "insurance_cover",
)


async def get_profile(db: AsyncSession, user: User) -> FinancialProfile | None:
    return (
        await db.execute(select(FinancialProfile).where(FinancialProfile.user_id == user.id))
    ).scalar_one_or_none()


def credit_prefill(report: CreditReport | None) -> dict[str, Decimal]:
    """Values we can suggest from the bureau: outstanding debt and EMIs on active accounts."""
    if report is None:
        return {}
    active = [a for a in report.accounts if a.is_active]
    if not active:
        return {}
    prefill = {"total_debt": sum((a.current_balance for a in active), ZERO)}
    emis = [a.emi_amount for a in active if a.emi_amount is not None]
    if emis:
        prefill["monthly_emi"] = sum(emis, ZERO)
    return prefill


def money_summary(annual_income: Decimal | None, monthly_spend: Decimal | None, cash: Decimal | None) -> dict:
    """The "monthly surplus" and "runway today" tiles on the Money screen."""
    surplus = runway = None
    if annual_income is not None and monthly_spend is not None:
        surplus = (annual_income / 12 - monthly_spend).quantize(Decimal("0.01"))
    if cash is not None and monthly_spend:
        runway = (cash / monthly_spend).quantize(Decimal("0.1"))
    return {"monthly_surplus": surplus, "runway_months": runway}


async def get_profile_view(db: AsyncSession, user: User) -> dict:
    """Saved profile if present; otherwise an unsaved form pre-filled from the credit report."""
    profile = await get_profile(db, user)
    if profile:
        return {
            "is_saved": True,
            "profile": {f: getattr(profile, f) for f in PROFILE_FIELDS},
            "summary": money_summary(profile.annual_income, profile.monthly_spend, profile.cash_reserve),
            "prefilled_fields": [],
            "prefill_source": None,
            "updated_at": profile.updated_at,
        }

    prefill = credit_prefill(await credit_service.get_latest_report(db, user))
    data: dict = {f: None for f in PROFILE_FIELDS}
    data["currency"] = Currency.INR
    data.update(prefill)
    return {
        "is_saved": False,
        "profile": data,
        "summary": money_summary(None, None, None),
        "prefilled_fields": sorted(prefill),
        "prefill_source": "CREDIT_REPORT" if prefill else None,
        "updated_at": None,
    }


# Columns that can't be null: an explicit null in the request is ignored for these.
_NOT_NULL = {"annual_income", "currency", "monthly_spend", "cash_reserve", "monthly_emi", "total_debt", "investments"}


async def upsert_profile(db: AsyncSession, user: User, payload: FinancialProfileIn) -> dict:
    """Save the Money screen. Fields not sent keep their saved value.

    First save: monthly_emi / total_debt default to what the credit report shows, else 0.
    """
    profile = await get_profile(db, user)
    values = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if not (v is None and k in _NOT_NULL)
    }
    values.setdefault("currency", payload.currency)
    if profile is None:
        prefill = credit_prefill(await credit_service.get_latest_report(db, user))
        defaults = {
            "monthly_emi": prefill.get("monthly_emi", ZERO),
            "total_debt": prefill.get("total_debt", ZERO),
            "investments": ZERO,
        }
        profile = FinancialProfile(user_id=user.id, **(defaults | values))
        db.add(profile)
    else:
        for k, v in values.items():
            setattr(profile, k, v)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    return await get_profile_view(db, user)


# ---- snapshot ---------------------------------------------------------------------------------

@dataclass
class Position:
    security_name: str
    ticker: str | None
    vested_value: Decimal


@dataclass
class FinancialSnapshot:
    currency: Currency
    profile: FinancialProfile | None
    risk: RiskProfile | None
    credit_report: CreditReport | None
    holdings: list[EquityHolding]
    excluded_holdings: list[EquityHolding] = field(default_factory=list)  # other currency, no FX yet

    @property
    def cash(self) -> Decimal:
        return self.profile.cash_reserve if self.profile else ZERO

    @property
    def investments(self) -> Decimal:
        return self.profile.investments if self.profile else ZERO

    @property
    def debt(self) -> Decimal:
        if self.profile:
            return self.profile.total_debt
        return credit_prefill(self.credit_report).get("total_debt", ZERO)

    @property
    def monthly_emi(self) -> Decimal:
        if self.profile:
            return self.profile.monthly_emi
        return credit_prefill(self.credit_report).get("monthly_emi", ZERO)

    @property
    def vested_equity(self) -> Decimal:
        return sum((h.vested_value for h in self.holdings), ZERO)

    @property
    def unvested_equity(self) -> Decimal:
        return sum((h.unvested_value for h in self.holdings), ZERO)

    @property
    def net_worth(self) -> Decimal:
        """Cash + investments + vested equity - debt. Unvested equity is not yet owned."""
        return self.cash + self.investments + self.vested_equity - self.debt

    @property
    def credit_score(self) -> int | None:
        return self.credit_report.credit_score if self.credit_report else None

    def positions(self) -> list[Position]:
        """Holdings aggregated per security (same stock can be entered more than once)."""
        grouped: dict[str, Position] = {}
        for h in self.holdings:
            key = (h.ticker or h.security_name).strip().upper()
            pos = grouped.setdefault(key, Position(h.security_name, h.ticker, ZERO))
            pos.vested_value += h.vested_value
        return sorted(grouped.values(), key=lambda p: p.vested_value, reverse=True)

    def top_position(self) -> Position | None:
        positions = self.positions()
        return positions[0] if positions and positions[0].vested_value > 0 else None

    def concentration_percent(self, position: Position) -> Decimal | None:
        nw = self.net_worth
        if nw <= 0:
            return None
        return (position.vested_value / nw * 100).quantize(Decimal("0.01"))


async def build_snapshot(db: AsyncSession, user: User) -> FinancialSnapshot:
    profile = await get_profile(db, user)
    currency = profile.currency if profile else Currency.INR
    risk = (await db.execute(select(RiskProfile).where(RiskProfile.user_id == user.id))).scalar_one_or_none()
    holdings = list(
        (await db.execute(select(EquityHolding).where(EquityHolding.user_id == user.id))).scalars()
    )
    return FinancialSnapshot(
        currency=currency,
        profile=profile,
        risk=risk,
        credit_report=await credit_service.get_latest_report(db, user),
        holdings=[h for h in holdings if h.currency == currency],
        excluded_holdings=[h for h in holdings if h.currency != currency],
    )
