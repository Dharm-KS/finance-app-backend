from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import AppError, ErrorCode
from app.schemas.advisor import (
    ConnectionOut,
    ConnectionStartOut,
    DataSummaryOut,
    OtpIn,
    PushReportsIn,
    SyncOut,
)
from app.schemas.common import AUTH_ERRORS, CONFLICT, NOT_FOUND, VALIDATION, ApiResponse, ErrorResponse, ok
from app.services import aggregator_service, onboarding_service
from app.services.advisor import engine
from app.services.aggregator_service import OTP_TTL
from app.services.providers.aggregator import AggregatorProvider, get_aggregator_provider

router = APIRouter(prefix="/aggregator", tags=["Bank data (aggregator)"])

ConnectionId = Path(gt=0, description="Connection id")
Provider = Annotated[AggregatorProvider, Depends(get_aggregator_provider)]
OTP_ERRORS = {400: {"model": ErrorResponse, "description": "Invalid / expired OTP"},
              429: {"model": ErrorResponse, "description": "Too many attempts"},
              503: {"model": ErrorResponse, "description": "Provider unavailable"}}


async def _after_sync(db, user, result: dict) -> dict | None:
    """Connecting completes the BANK_CONNECT onboarding step. New or changed data is analysed only once
    onboarding is complete (the first analysis needs every screen too); then only affected agents regenerate."""
    if not result["changed"]:
        await onboarding_service.refresh(db, user)
        await db.commit()
        return None
    return await engine.analyse_if_ready(db, user, trigger="AGGREGATOR_SYNC")


def _sync_out(conn, result: dict, analysis: dict | None) -> dict:
    return {"connection": ConnectionOut.model_validate(conn), "data_changed": result["changed"],
            "reports": result["reports"], "analysis": analysis}


@router.post(
    "/connections",
    response_model=ApiResponse[ConnectionStartOut],
    status_code=status.HTTP_201_CREATED,
    summary="Connect bank accounts (send OTP)",
    description="Starts a connection with the account aggregator, which sends the customer an OTP. "
    "MVP: mock provider, OTP is always `123456`.",
    responses=AUTH_ERRORS,
)
async def start_connection(user: CurrentUser, db: DbSession, provider: Provider):
    conn = await aggregator_service.start_connection(db, user, provider)
    return ok({"connection": ConnectionOut.model_validate(conn), "otp_expires_in_seconds": int(OTP_TTL.total_seconds())},
              "OTP sent")


@router.post(
    "/connections/{connection_id}/verify-otp",
    response_model=ApiResponse[SyncOut],
    summary="Verify the OTP and import the data",
    description="Verifies the aggregator OTP, fetches the reports and stores each section in its own table. This is the "
    "first onboarding screen after login; the AI analysis starts once onboarding is complete "
    "(`analysis` is null until then).",
    responses={**AUTH_ERRORS, **NOT_FOUND, **VALIDATION, **OTP_ERRORS},
)
async def verify_connection(payload: OtpIn, user: CurrentUser, db: DbSession, provider: Provider,
                            connection_id: int = ConnectionId):
    conn, result = await aggregator_service.verify_connection(db, user, connection_id, payload.otp, provider)
    return ok(_sync_out(conn, result, await _after_sync(db, user, result)), "Accounts connected and data imported")


@router.post(
    "/connections/{connection_id}/refresh",
    response_model=ApiResponse[SyncOut],
    summary="Fetch the latest data",
    description="Re-fetches the reports. If the data changed, the stored data is replaced and only the affected "
    "agents are regenerated. `data_changed: false` means nothing changed and nothing was re-analysed.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **CONFLICT},
)
async def refresh_connection(user: CurrentUser, db: DbSession, provider: Provider, connection_id: int = ConnectionId):
    conn, result = await aggregator_service.refresh_connection(db, user, connection_id, provider)
    return ok(_sync_out(conn, result, await _after_sync(db, user, result)), "Data refreshed")


@router.post(
    "/connections/{connection_id}/reports",
    response_model=ApiResponse[SyncOut],
    summary="[Test only] Push raw provider reports",
    description="Stores the given raw provider responses as if the provider had sent them, to test updates "
    "(e.g. next month's report). Disabled when `ENVIRONMENT=production`.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **CONFLICT, **VALIDATION},
)
async def push_reports(payload: PushReportsIn, user: CurrentUser, db: DbSession, connection_id: int = ConnectionId):
    if not settings.dev_endpoints_enabled:
        raise AppError(403, "This endpoint is disabled in production", ErrorCode.DEV_ENDPOINT_DISABLED)
    conn, result = await aggregator_service.push_reports(db, user, connection_id, payload.reports)
    return ok(_sync_out(conn, result, await _after_sync(db, user, result)), "Reports stored")


@router.get(
    "/connections",
    response_model=ApiResponse[list[ConnectionOut]],
    summary="List connections",
    responses=AUTH_ERRORS,
)
async def list_connections(user: CurrentUser, db: DbSession):
    return ok([ConnectionOut.model_validate(c) for c in await aggregator_service.list_connections(db, user)],
              "Connections fetched")


@router.get(
    "/data",
    response_model=ApiResponse[DataSummaryOut],
    summary="Imported data summary",
    description="Row counts per table plus headline values of accounts, portfolios, loans and deposits.",
    responses=AUTH_ERRORS,
)
async def data_summary(user: CurrentUser, db: DbSession):
    return ok(await aggregator_service.data_summary(db, user), "Data summary fetched")
