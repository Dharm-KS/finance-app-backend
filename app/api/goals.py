from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, NOT_FOUND, VALIDATION, ApiResponse, ok
from app.schemas.goal import GoalCreate, GoalListOut, GoalOut, GoalSelectionIn, GoalSuggestionOut, GoalUpdate
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["Goals"])

GoalId = Path(gt=0, description="Goal id")


@router.get(
    "",
    response_model=ApiResponse[GoalListOut],
    summary="List goals",
    description="Goals with progress, at-risk flag and the latest automatic calculation.",
    responses=AUTH_ERRORS,
)
async def list_goals(user: CurrentUser, db: DbSession):
    return ok({"goals": await goal_service.list_goals(db, user)}, "Goals fetched successfully")


@router.get(
    "/suggestions",
    response_model=ApiResponse[list[GoalSuggestionOut]],
    summary="Suggested goals",
    description="All 9 goal cards for the \"Goals that matter\" screen, in screen order, with category tag, "
    "target calculated from the user's data, and `required_inputs` when the user must enter something first.",
    responses=AUTH_ERRORS,
)
async def goal_suggestions(user: CurrentUser, db: DbSession):
    return ok(await goal_service.suggestions(db, user), "Goal suggestions fetched successfully")


@router.post(
    "",
    response_model=ApiResponse[GoalOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create goal",
    description="If `target_amount` is omitted it is calculated (EMERGENCY_FUND, EQUITY_TAX_RESERVE, "
    "REDUCE_SINGLE_STOCK_CONCENTRATION). HOME_DOWN_PAYMENT requires `target_amount`.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def create_goal(payload: GoalCreate, user: CurrentUser, db: DbSession):
    return ok(await goal_service.create(db, user, payload), "Goal created successfully")


@router.put(
    "/selection",
    response_model=ApiResponse[GoalListOut],
    summary="Save the goals screen selection",
    description="Send every ticked goal card. The saved goals become exactly this set: new ticks are created "
    "with calculated targets, saved goals that are still ticked are kept, and unticked ones are deleted. "
    "Completes the GOALS onboarding step. All or nothing: if any goal can't be sized, nothing changes.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def save_goal_selection(payload: GoalSelectionIn, user: CurrentUser, db: DbSession):
    return ok({"goals": await goal_service.save_selection(db, user, payload)}, "Goals saved successfully")


@router.put(
    "/{goal_id}",
    response_model=ApiResponse[GoalOut],
    summary="Update goal",
    description="Partial update (e.g. progress or status). 404 if the goal does not belong to the user.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **VALIDATION},
)
async def update_goal(payload: GoalUpdate, user: CurrentUser, db: DbSession, goal_id: int = GoalId):
    return ok(await goal_service.update(db, user, goal_id, payload), "Goal updated successfully")


@router.delete(
    "/{goal_id}",
    response_model=ApiResponse[None],
    summary="Delete goal",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def delete_goal(user: CurrentUser, db: DbSession, goal_id: int = GoalId):
    await goal_service.delete(db, user, goal_id)
    return ok(None, "Goal deleted successfully")
