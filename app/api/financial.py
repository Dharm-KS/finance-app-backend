from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, VALIDATION, ApiResponse, ok
from app.schemas.financial import FinancialProfileIn, FinancialProfileOut
from app.services import financial_service

router = APIRouter(prefix="/financial-profile", tags=["Financial profile"])


@router.get(
    "",
    response_model=ApiResponse[FinancialProfileOut],
    summary="Get financial profile (\"Your Money\")",
    description="Returns the saved profile. If nothing is saved yet, returns a form pre-filled from the "
    "credit report (`total_debt`, `monthly_emi`) with `is_saved=false` and the list of `prefilled_fields`.",
    responses=AUTH_ERRORS,
)
async def get_financial_profile(user: CurrentUser, db: DbSession):
    return ok(await financial_service.get_profile_view(db, user), "Financial profile fetched successfully")


@router.put(
    "",
    response_model=ApiResponse[FinancialProfileOut],
    summary="Create or replace financial profile",
    description="Full replacement. Amounts must be >= 0 with at most 2 decimals; age 18-100; dependents 0-20.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def put_financial_profile(payload: FinancialProfileIn, user: CurrentUser, db: DbSession):
    return ok(await financial_service.upsert_profile(db, user, payload), "Financial profile saved successfully")
