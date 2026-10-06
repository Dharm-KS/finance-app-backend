from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models.enums import OnboardingStep
from app.schemas.common import AUTH_ERRORS, VALIDATION, ApiResponse, ok
from app.schemas.onboarding import OnboardingSkipIn, OnboardingStatusOut
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get(
    "/status",
    response_model=ApiResponse[OnboardingStatusOut],
    summary="Onboarding status",
    description="Which steps are done and `current_step` - the screen the app should resume on. "
    "Order: REGISTRATION -> CONSENT -> CREDIT -> FINANCIAL_PROFILE -> EQUITY -> RISK -> GOALS -> COMPLETED.",
    responses=AUTH_ERRORS,
)
async def onboarding_status(user: CurrentUser, db: DbSession):
    ob = await onboarding_service.get_status(db, user)
    return ok(OnboardingStatusOut.model_validate(ob), "Onboarding status fetched successfully")


@router.post(
    "/skip",
    response_model=ApiResponse[OnboardingStatusOut],
    summary="Skip an optional step",
    description="Currently only `EQUITY` can be skipped (users without employer equity).",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def skip_step(payload: OnboardingSkipIn, user: CurrentUser, db: DbSession):
    ob = await onboarding_service.skip_step(db, user, OnboardingStep(payload.step))
    return ok(OnboardingStatusOut.model_validate(ob), "Step skipped")
