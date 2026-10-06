from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, NOT_FOUND, VALIDATION, ApiResponse, ok
from app.schemas.equity import EquityCreate, EquityListOut, EquityOut, EquityUpdate
from app.services import equity_service

router = APIRouter(prefix="/equity", tags=["Equity"])

HoldingId = Path(gt=0, description="Equity holding id")


@router.get(
    "",
    response_model=ApiResponse[EquityListOut],
    summary="List equity holdings",
    description="All of the user's employer-equity holdings with vested/unvested totals.",
    responses=AUTH_ERRORS,
)
async def list_equity(user: CurrentUser, db: DbSession):
    return ok(await equity_service.list_holdings(db, user), "Equity holdings fetched successfully")


@router.post(
    "",
    response_model=ApiResponse[EquityOut],
    status_code=status.HTTP_201_CREATED,
    summary="Add equity holding",
    description="Manual entry (`source=MANUAL`). A user may have multiple holdings.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def create_equity(payload: EquityCreate, user: CurrentUser, db: DbSession):
    holding = await equity_service.create(db, user, payload)
    return ok(EquityOut.model_validate(holding), "Equity holding added successfully")


@router.put(
    "/{holding_id}",
    response_model=ApiResponse[EquityOut],
    summary="Update equity holding",
    description="Partial update; only fields sent are changed. 404 if the holding does not belong to the user.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **VALIDATION},
)
async def update_equity(payload: EquityUpdate, user: CurrentUser, db: DbSession, holding_id: int = HoldingId):
    holding = await equity_service.update(db, user, holding_id, payload)
    return ok(EquityOut.model_validate(holding), "Equity holding updated successfully")


@router.delete(
    "/{holding_id}",
    response_model=ApiResponse[None],
    summary="Delete equity holding",
    description="404 if the holding does not belong to the user.",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def delete_equity(user: CurrentUser, db: DbSession, holding_id: int = HoldingId):
    await equity_service.delete(db, user, holding_id)
    return ok(None, "Equity holding deleted successfully")
