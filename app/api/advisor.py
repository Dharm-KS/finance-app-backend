from fastapi import APIRouter, Path, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.advisor import (
    AdvisorStatusOut,
    AgentDetailOut,
    AgentSummaryOut,
    AnalysisRunOut,
    ChatHistoryOut,
    ChatIn,
    ChatMessageOut,
    ChatReplyOut,
    ExtraDataIn,
    ExtraDataOut,
    OverviewOut,
    RecommendationOut,
    RecommendationUpdateIn,
    RefreshIn,
)
from app.schemas.common import ErrorResponse, AUTH_ERRORS, CONFLICT, NOT_FOUND, VALIDATION, ApiResponse, ok
from app.services.advisor import engine
from app.services.advisor.profile import build_profile
from app.services.providers.extraction import get_extractor

router = APIRouter(prefix="/advisor", tags=["AI advisor"])


@router.get(
    "/status",
    response_model=ApiResponse[AdvisorStatusOut],
    summary="Analysis status",
    description="Poll while `running` is true. `stale` means the customer's data changed since the last analysis "
    "(call `POST /advisor/refresh`).",
    responses=AUTH_ERRORS,
)
async def advisor_status(user: CurrentUser, db: DbSession):
    s = await engine.status(db, user)
    s["last_run"] = AnalysisRunOut.model_validate(s["last_run"]) if s["last_run"] else None
    return ok(s, "Status fetched")


@router.post(
    "/refresh",
    response_model=ApiResponse[AnalysisRunOut],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run the analysis",
    description="Regenerates only the agents whose data changed (or all of them with `force: true`). Runs in the "
    "background; if a run is already in progress, that run is returned. Returns `ONBOARDING_INCOMPLETE` (409) "
    "before onboarding is finished: the first analysis starts by itself when the last screen is saved.",
    responses={**AUTH_ERRORS, 409: {"model": ErrorResponse, "description": "Onboarding not finished"}},
)
async def refresh(payload: RefreshIn, user: CurrentUser, db: DbSession):
    await engine.require_onboarding(db, user)
    run = await engine.start_analysis(db, user, trigger="MANUAL", force=payload.force)
    return ok(AnalysisRunOut.model_validate(run), "Analysis started")


@router.get(
    "/overview",
    response_model=ApiResponse[OverviewOut],
    summary="Chief agent: overview and step-by-step plan",
    description="The Chief Financial Intelligence Agent's headline, summary, conflicts between areas, the "
    "recommendations as numbered steps, and each specialist agent's card.",
    responses=AUTH_ERRORS,
)
async def overview(user: CurrentUser, db: DbSession):
    return ok(await engine.overview(db, user), "Overview fetched")


@router.get(
    "/agents",
    response_model=ApiResponse[list[AgentSummaryOut]],
    summary="Specialist agents",
    responses=AUTH_ERRORS,
)
async def agents(user: CurrentUser, db: DbSession):
    return ok(await engine.list_agents(db, user), "Agents fetched")


@router.get(
    "/agents/{agent_key}",
    response_model=ApiResponse[AgentDetailOut],
    summary="One agent's full analysis",
    description="Findings, recommendations, data gaps and the facts (computed in code) the agent was given. "
    "`agent_key`: INVESTMENT, TAX, INSURANCE, LOAN, BUDGET, RSU, ESTATE or GOAL.",
    responses={**AUTH_ERRORS, **NOT_FOUND},
)
async def agent_detail(user: CurrentUser, db: DbSession, agent_key: str = Path(max_length=20)):
    return ok(await engine.get_agent(db, user, agent_key), "Agent fetched")


@router.get(
    "/recommendations",
    response_model=ApiResponse[dict[str, list[RecommendationOut]]],
    summary="Recommendations (steps)",
    description="`steps`: open / in-progress recommendations in the order to act. `completed`: done or dismissed.",
    responses=AUTH_ERRORS,
)
async def list_recommendations(user: CurrentUser, db: DbSession):
    steps, done = await engine.recommendations(db, user)
    return ok({"steps": steps, "completed": done}, "Recommendations fetched")


@router.patch(
    "/recommendations/{rec_id}",
    response_model=ApiResponse[RecommendationOut],
    summary="Update a recommendation's status",
    description="Mark a step IN_PROGRESS, DONE or DISMISSED (or back to OPEN). The status is kept when the analysis "
    "regenerates, and the Chief agent takes it into account.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **VALIDATION},
)
async def update_recommendation(payload: RecommendationUpdateIn, user: CurrentUser, db: DbSession,
                                rec_id: int = Path(gt=0)):
    return ok(await engine.update_recommendation(db, user, rec_id, payload.status), "Recommendation updated")


@router.post(
    "/chat",
    response_model=ApiResponse[ChatReplyOut],
    summary="Ask the advisor",
    description="Chat with the Chief agent. Answers use the customer's saved analysis (it is not rebuilt per "
    "question). 409 `ADVISOR_NOT_READY` until the first analysis finishes.",
    responses={**AUTH_ERRORS, **CONFLICT, **VALIDATION},
)
async def chat(payload: ChatIn, user: CurrentUser, db: DbSession):
    q, a = await engine.chat(db, user, payload.message)
    return ok({"question": ChatMessageOut.model_validate(q), "answer": ChatMessageOut.model_validate(a)}, "Answered")


@router.get(
    "/chat",
    response_model=ApiResponse[ChatHistoryOut],
    summary="Chat history",
    responses=AUTH_ERRORS,
)
async def chat_history(user: CurrentUser, db: DbSession, limit: int = Query(50, ge=1, le=200)):
    rows = await engine.chat_history(db, user, limit)
    return ok({"messages": [ChatMessageOut.model_validate(m) for m in rows]}, "Chat history fetched")


@router.get(
    "/profile",
    response_model=ApiResponse[dict],
    summary="Merged customer financial profile",
    description="Everything the agents see: aggregator data + onboarding answers + extra form data, merged and "
    "without personal identifiers.",
    responses=AUTH_ERRORS,
)
async def profile(user: CurrentUser, db: DbSession):
    p = await build_profile(db, user)
    return ok(p.domains, "Profile fetched")


@router.post(
    "/extra-data",
    response_model=ApiResponse[ExtraDataOut],
    status_code=status.HTTP_201_CREATED,
    summary="Add financial details from another form",
    description="Stores extra details (e.g. will, insurance policies) and re-runs the agents they affect. "
    "Later, Gemini will extract these fields from free text and documents.",
    responses={**AUTH_ERRORS, **VALIDATION},
)
async def add_extra_data(payload: ExtraDataIn, user: CurrentUser, db: DbSession):
    extractor = get_extractor()
    data = await extractor.extract(payload.category, payload.data)
    row = await engine.add_extra_data(db, user, payload.category, data, extractor.name)
    await engine.analyse_if_ready(db, user, trigger="EXTRA_DATA")
    return ok(ExtraDataOut.model_validate(row), "Details saved; analysis updating")


@router.get(
    "/extra-data",
    response_model=ApiResponse[list[ExtraDataOut]],
    summary="List extra form data",
    responses=AUTH_ERRORS,
)
async def list_extra_data(user: CurrentUser, db: DbSession):
    return ok([ExtraDataOut.model_validate(r) for r in await engine.list_extra_data(db, user)], "Extra data fetched")
