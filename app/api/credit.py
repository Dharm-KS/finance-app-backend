from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, CONFLICT, FORBIDDEN, NOT_FOUND, ApiResponse, ErrorResponse, ok
from app.schemas.credit import CreditAccountOut, CreditReportOut
from app.services import credit_service
from app.services.providers.credit import CreditProvider, get_credit_provider

router = APIRouter(prefix="/credit", tags=["Credit"])


@router.post(
    "/fetch",
    response_model=ApiResponse[CreditReportOut],
    status_code=status.HTTP_201_CREATED,
    summary="Fetch credit report",
    description="Pulls the user's credit report from the configured bureau provider (MVP: dummy provider) "
    "and stores it. Requires an active `CREDIT_REPORT` consent.\n\n"
    "Dummy profile by last digit of mobile: 0-3 -> score 780, 4-6 -> 692, 7-9 -> 615; "
    "mobile ending `0000` -> no bureau record.",
    responses={
        **AUTH_ERRORS, **FORBIDDEN, **CONFLICT,
        404: {"model": ErrorResponse, "description": "Bureau has no record for this user"},
        503: {"model": ErrorResponse, "description": "Bureau unavailable"},
    },
)
async def fetch_credit_report(
    user: CurrentUser, db: DbSession, provider: Annotated[CreditProvider, Depends(get_credit_provider)]
):
    report = await credit_service.fetch_report(db, user, provider)
    return ok(credit_service.to_response(report), "Credit report fetched successfully")


@router.get(
    "/report",
    response_model=ApiResponse[CreditReportOut],
    summary="Get latest credit report",
    description="Latest successful credit report with summary and normalised accounts (raw bureau data is never returned).",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def get_credit_report(user: CurrentUser, db: DbSession):
    report = await credit_service.require_latest_report(db, user)
    return ok(credit_service.to_response(report), "Credit report fetched successfully")


@router.get(
    "/accounts",
    response_model=ApiResponse[list[CreditAccountOut]],
    summary="List credit accounts",
    description="Normalised tradelines (loans / cards) from the latest credit report.",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def get_credit_accounts(user: CurrentUser, db: DbSession):
    report = await credit_service.require_latest_report(db, user)
    return ok(report.accounts, "Credit accounts fetched successfully")
