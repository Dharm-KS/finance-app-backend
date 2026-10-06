from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, NOT_FOUND, VALIDATION, ApiResponse, ok
from app.schemas.risk import RiskProfileIn, RiskProfileOut
from app.services import risk_service

router = APIRouter(prefix="/risk-profile", tags=["Risk profile"])


@router.get(
    "",
    response_model=ApiResponse[RiskProfileOut],
    summary="Get risk profile",
    description="404 `RISK_PROFILE_NOT_FOUND` until the user completes the risk screen.",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def get_risk_profile(user: CurrentUser, db: DbSession):
    profile = await risk_service.require_profile(db, user)
    return ok(RiskProfileOut.model_validate(profile), "Risk profile fetched successfully")


@router.put(
    "",
    response_model=ApiResponse[RiskProfileOut],
    summary="Create or replace risk profile",
    description="Risk tolerance (STEADY/BALANCED/GROWTH), drawdown and single-stock limits (0-100%), "
    "planning horizon (1-50 years).",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def put_risk_profile(payload: RiskProfileIn, user: CurrentUser, db: DbSession):
    profile = await risk_service.upsert(db, user, payload)
    return ok(RiskProfileOut.model_validate(profile), "Risk profile saved successfully")
