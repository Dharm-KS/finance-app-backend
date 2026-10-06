from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, ApiResponse, ok
from app.schemas.dashboard import DashboardOut
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "",
    response_model=ApiResponse[DashboardOut],
    summary="Financial dashboard",
    description="Consolidated position: net worth (cash + investments + vested equity - debt), credit score, "
    "risk settings, goal counts and rule-based alerts. Works with partial data during onboarding.",
    responses=AUTH_ERRORS,
)
async def get_dashboard(user: CurrentUser, db: DbSession):
    return ok(await dashboard_service.get_dashboard(db, user), "Dashboard fetched successfully")
