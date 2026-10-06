from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GoalStatus
from app.models.user import User
from app.services import goal_service, onboarding_service
from app.services.financial_service import build_snapshot
from app.services.insights import InsightEngine, get_insight_engine


async def get_dashboard(db: AsyncSession, user: User, engine: InsightEngine | None = None) -> dict:
    engine = engine or get_insight_engine()
    s = await build_snapshot(db, user)
    goals = await goal_service.assess_all(db, user, s)
    onboarding = await onboarding_service.refresh(db, user)
    await db.commit()

    conc = goal_service.concentration_analysis(s)
    emergency_months = (
        (s.cash / s.profile.monthly_spend).quantize(Decimal("0.01"))
        if s.profile and s.profile.monthly_spend > 0 else None
    )

    return {
        "currency": s.currency,
        "net_worth": s.net_worth,
        "cash": s.cash,
        "investments": s.investments,
        "equity": s.vested_equity,
        "unvested_equity": s.unvested_equity,
        "debt": s.debt,
        "monthly_emi": s.monthly_emi,
        "credit_score": s.credit_score,
        "emergency_fund_months": emergency_months,
        "top_concentration": conc,
        "risk": {
            "profile": s.risk.risk_tolerance,
            "max_drawdown": s.risk.max_drawdown_percent,
            "single_stock_limit": s.risk.single_stock_limit_percent,
            "planning_horizon_years": s.risk.planning_horizon_years,
        } if s.risk else None,
        "goals": {
            "total": len(goals),
            "active": sum(1 for g, _ in goals if g.status == GoalStatus.ACTIVE),
            "completed": sum(1 for g, _ in goals if g.status == GoalStatus.COMPLETED),
            "at_risk": sum(1 for _, reason in goals if reason),
        },
        "alerts": engine.alerts(s, goals),
        "onboarding_step": onboarding.current_step,
    }
