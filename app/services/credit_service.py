"""Credit report orchestration: consent check -> provider -> persist normalised data."""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ConflictError, ErrorCode, NotFoundError
from app.models.credit_account import CreditAccount
from app.models.credit_report import CreditReport
from app.models.enums import ConsentType, CreditAccountType, CreditReportStatus
from app.models.user import User
from app.services import consent_service, onboarding_service
from app.services.providers.credit import CreditProvider, CreditProviderError, CreditSubject

logger = logging.getLogger(__name__)


async def get_latest_report(db: AsyncSession, user: User, *, successful_only: bool = True) -> CreditReport | None:
    stmt = (
        select(CreditReport)
        .options(selectinload(CreditReport.accounts))
        .where(CreditReport.user_id == user.id)
        .order_by(CreditReport.created_at.desc(), CreditReport.id.desc())
        .limit(1)
    )
    if successful_only:
        stmt = stmt.where(CreditReport.report_status == CreditReportStatus.SUCCESS)
    return (await db.execute(stmt)).scalar_one_or_none()


async def require_latest_report(db: AsyncSession, user: User) -> CreditReport:
    report = await get_latest_report(db, user)
    if report is None:
        raise NotFoundError("No credit report found. Fetch your credit report first.", ErrorCode.CREDIT_REPORT_NOT_FOUND)
    return report


async def fetch_report(db: AsyncSession, user: User, provider: CreditProvider) -> CreditReport:
    if not await consent_service.has_active_consent(db, user, ConsentType.CREDIT_REPORT):
        raise AppError(403, "Credit consent is required", ErrorCode.CONSENT_REQUIRED)

    if await get_latest_report(db, user):
        raise ConflictError("A credit report already exists for this user", ErrorCode.CREDIT_REPORT_ALREADY_EXISTS)

    try:
        data = await provider.fetch_report(CreditSubject(user_uuid=user.uuid, mobile=user.mobile, name=user.name))
    except CreditProviderError:
        logger.warning("Credit provider %s failed for user %s", provider.name, user.uuid)
        raise AppError(503, "Credit bureau is unavailable right now. Please try again later.", ErrorCode.CREDIT_REPORT_UNAVAILABLE)

    report = CreditReport(
        user_id=user.id,
        provider=data.provider,
        report_type=data.report_type,
        report_reference=data.report_reference,
        credit_score=data.credit_score,
        score_date=data.score_date,
        report_date=data.report_date,
        report_status=data.report_status,
        raw_report=data.raw_report,
        accounts=[CreditAccount(**vars(a)) for a in data.accounts],
    )
    db.add(report)
    await db.flush()

    if data.report_status != CreditReportStatus.SUCCESS:
        # Keep the attempt for audit, but tell the client no report is available.
        await db.commit()
        raise AppError(
            404,
            "No credit history was found with the credit bureau for this user",
            ErrorCode.CREDIT_REPORT_UNAVAILABLE,
        )

    await onboarding_service.refresh(db, user)
    await db.commit()
    return await require_latest_report(db, user)


def summarise(report: CreditReport) -> dict:
    active = [a for a in report.accounts if a.is_active]
    cards = [a for a in active if a.account_type == CreditAccountType.CREDIT_CARD and a.credit_limit]
    card_limit = sum((a.credit_limit for a in cards), Decimal("0"))
    card_balance = sum((a.current_balance for a in cards), Decimal("0"))
    utilization = (card_balance / card_limit * 100).quantize(Decimal("0.01")) if card_limit > 0 else None
    return {
        "active_accounts": len(active),
        "total_accounts": len(report.accounts),
        "total_outstanding": sum((a.current_balance for a in active), Decimal("0")),
        "total_monthly_emi": sum((a.emi_amount or Decimal("0") for a in active), Decimal("0")),
        "credit_card_utilization_percent": utilization,
        "max_dpd": max((a.dpd for a in report.accounts), default=0),
    }


def to_response(report: CreditReport) -> dict:
    return {
        "id": report.id,
        "provider": report.provider,
        "report_type": report.report_type,
        "report_reference": report.report_reference,
        "credit_score": report.credit_score,
        "score_date": report.score_date,
        "report_date": report.report_date,
        "report_status": report.report_status,
        "created_at": report.created_at,
        "summary": summarise(report),
        "accounts": report.accounts,
    }
