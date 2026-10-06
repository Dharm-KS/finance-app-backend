from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, VALIDATION, ApiResponse, ok
from app.schemas.preferences import PreferencesIn, PreferencesOut
from app.services import preferences_service

router = APIRouter(prefix="/preferences", tags=["Preferences"])


@router.get(
    "",
    response_model=ApiResponse[PreferencesOut],
    summary="Get preferences",
    description="Insight tone and alert switches. Before the first save this returns the defaults with `is_saved: false`.",
    responses=AUTH_ERRORS,
)
async def get_preferences(user: CurrentUser, db: DbSession):
    return ok(await preferences_service.get_view(db, user), "Preferences fetched successfully")


@router.put(
    "",
    response_model=ApiResponse[PreferencesOut],
    summary="Save preferences",
    description="Saves the \"How your twin talks to you\" screen and completes the PREFERENCES onboarding step. "
    "Fields not sent keep their current value.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def put_preferences(payload: PreferencesIn, user: CurrentUser, db: DbSession):
    return ok(await preferences_service.upsert(db, user, payload), "Preferences saved successfully")
