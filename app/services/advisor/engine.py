"""Advisor engine: runs the agents, persists their state, and serves overview / recommendations / chat.

Persistence model
- Each agent's state is stored per customer with the hash of its inputs (facts + agent version +
  provider). A run regenerates only agents whose hash changed, so logging in or chatting never
  rebuilds anything, and a new report regenerates only the agents it affects.
- The Chief agent re-runs when any specialist changed; its recommendations are upserted by key, so
  the customer's DONE / DISMISSED status survives regenerations.
"""

import asyncio
import hashlib
import json
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppError, ErrorCode, NotFoundError
from app.core.time import ensure_utc, utcnow
from app.models.advisor import AdvisorRecommendation, AgentState, AnalysisRun, ChatMessage, CustomerExtraData
from app.models.enums import AgentKey, AgentStatus, AnalysisRunStatus, ChatRole, RecommendationStatus
from app.models.user import User
from app.schemas.advisor import AgentInsight, ChiefInsight
from app.services.advisor.agents import AGENTS, AGENTS_BY_KEY, AgentSpec
from app.services.advisor.chief import build_chief_context, offline_chief
from app.services.advisor.llm import LLMError, LLMProvider, OfflineProvider, get_llm_provider
from app.services.advisor.profile import build_profile

logger = logging.getLogger(__name__)

CHIEF_VERSION = 2
RUN_STALE_AFTER = timedelta(minutes=15)  # a RUNNING run older than this is considered dead
CHAT_HISTORY_TURNS = 12
_background: set[asyncio.Task] = set()


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


async def _states(db: AsyncSession, user: User) -> dict[AgentKey, AgentState]:
    rows = (await db.execute(select(AgentState).where(AgentState.user_id == user.id))).scalars()
    return {s.agent_key: s for s in rows}


# ---- running -------------------------------------------------------------------------------------

async def _running_run(db: AsyncSession, user: User) -> AnalysisRun | None:
    run = (
        await db.execute(
            select(AnalysisRun).where(AnalysisRun.user_id == user.id, AnalysisRun.status == AnalysisRunStatus.RUNNING)
            .order_by(AnalysisRun.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if run and utcnow() - ensure_utc(run.created_at) < RUN_STALE_AFTER:
        return run
    return None


async def start_analysis(db: AsyncSession, user: User, trigger: str, force: bool = False) -> AnalysisRun:
    """Start a (re)analysis. Runs in the background unless ADVISOR_INLINE is set.

    If one is already running for this customer, that run is returned instead of starting another.
    """
    if running := await _running_run(db, user):
        return running
    run = AnalysisRun(user_id=user.id, trigger=trigger, status=AnalysisRunStatus.RUNNING,
                      agents_regenerated=[], agents_unchanged=[])
    db.add(run)
    await db.commit()
    if settings.ADVISOR_INLINE:
        await execute_run(db, user, run, force)
        return run
    task = asyncio.create_task(_run_in_new_session(user.id, run.id, force))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return run


async def _run_in_new_session(user_id: int, run_id: int, force: bool) -> None:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        run = await db.get(AnalysisRun, run_id)
        if user and run:
            await execute_run(db, user, run, force)


async def execute_run(db: AsyncSession, user: User, run: AnalysisRun, force: bool,
                      provider: LLMProvider | None = None) -> AnalysisRun:
    provider = provider or get_llm_provider()
    run_id, user_id = run.id, user.id  # rollback expires ORM objects; keep the ids
    try:
        profile = await build_profile(db, user)
        states = await _states(db, user)

        planned: list[tuple[AgentSpec, dict, str, AgentState]] = []
        unchanged: list[str] = []
        for spec in AGENTS:
            facts = spec.facts(profile)
            h = _hash({"version": spec.version, "provider": provider.name, "facts": facts})
            st = states.get(spec.key)
            if st is None:
                st = AgentState(user_id=user.id, agent_key=spec.key, status=AgentStatus.PENDING, version=0)
                db.add(st)
                states[spec.key] = st
            if force or st.input_hash != h or st.status != AgentStatus.READY:
                planned.append((spec, facts, h, st))
            else:
                unchanged.append(spec.key.value)
        for *_, st in planned:
            st.status = AgentStatus.RUNNING
        await db.commit()

        semaphore = asyncio.Semaphore(settings.LLM_MAX_PARALLEL)

        async def one(spec: AgentSpec, facts: dict, st: AgentState):
            previous = None
            if st.insight:
                previous = {"summary": st.insight.get("summary"),
                            "recommendations": [{"key": r["key"], "title": r["title"]}
                                                for r in st.insight.get("recommendations", [])]}
            async with semaphore:
                try:
                    return await provider.agent_insight(spec, facts, previous), provider.name, None
                except LLMError as e:
                    logger.warning("agent %s fell back to offline: %s", spec.key, e)
                    return await OfflineProvider().agent_insight(spec, facts, None), "offline-fallback", str(e)

        results = await asyncio.gather(*(one(spec, facts, st) for spec, facts, _, st in planned))
        now = utcnow()
        for (spec, facts, h, st), (ins, used, err) in zip(planned, results, strict=True):
            st.insight, st.facts, st.input_hash = ins, facts, h
            st.status, st.provider, st.error = AgentStatus.READY, used, err
            st.model = provider.model if used == provider.name else None
            st.version += 1
            st.generated_at = now

        regenerated = [spec.key.value for spec, *_ in planned]
        if await _run_chief(db, user, profile, states, provider, force or bool(planned)):
            regenerated.append(AgentKey.CHIEF.value)

        run.status = AnalysisRunStatus.COMPLETED
        run.agents_regenerated, run.agents_unchanged = regenerated, unchanged
        run.finished_at = utcnow()
        await db.commit()
    except Exception as e:  # never leave a run stuck in RUNNING
        logger.exception("analysis run %s failed", run_id)
        await db.rollback()
        run = await db.get(AnalysisRun, run_id)
        run.status, run.error, run.finished_at = AnalysisRunStatus.FAILED, str(e)[:500], utcnow()
        states = (await db.execute(select(AgentState).where(AgentState.user_id == user_id))).scalars()
        for st in states:
            if st.status == AgentStatus.RUNNING:
                st.status = AgentStatus.FAILED if not st.insight else AgentStatus.READY
        await db.commit()
    return run


async def _run_chief(db: AsyncSession, user: User, profile, states: dict, provider: LLMProvider, changed: bool) -> bool:
    ready = {k.value: s for k, s in states.items() if k != AgentKey.CHIEF and s.status == AgentStatus.READY and s.insight}
    recs = list((await db.execute(select(AdvisorRecommendation).where(AdvisorRecommendation.user_id == user.id))).scalars())
    previous = [{"key": r.rec_key, "title": r.title, "status": r.status.value} for r in recs if r.status != RecommendationStatus.OPEN]
    context = build_chief_context(
        profile,
        {k: s.insight for k, s in ready.items()},
        {k: AGENTS_BY_KEY[AgentKey(k)].name for k in ready},
        {k: (s.facts or {}).get("metrics", []) for k, s in ready.items()},
        previous,
    )
    h = _hash({"version": CHIEF_VERSION, "provider": provider.name, "context": context})
    chief = states.get(AgentKey.CHIEF)
    if chief is None:
        chief = AgentState(user_id=user.id, agent_key=AgentKey.CHIEF, status=AgentStatus.PENDING, version=0)
        db.add(chief)
    if not changed and chief.status == AgentStatus.READY and chief.input_hash == h:
        return False

    chief.status = AgentStatus.RUNNING
    await db.commit()
    try:
        out, used, err = await provider.chief_insight(context), provider.name, None
    except LLMError as e:
        logger.warning("chief fell back to offline: %s", e)
        out, used, err = ChiefInsight.model_validate(offline_chief(context)).model_dump(), "offline-fallback", str(e)

    chief.insight = out
    chief.facts = {"currency": context["currency"], "balance_sheet": context["balance_sheet"],
                   "cashflow": context["cashflow"], "fx_rates": (profile.get("fx") or {}).get("rates_used", {})}
    chief.input_hash, chief.status, chief.provider, chief.error = h, AgentStatus.READY, used, err
    chief.model = provider.model if used == provider.name else None
    chief.version += 1
    chief.generated_at = utcnow()
    _sync_recommendations(user, recs, out["recommendations"], context["currency"], db)
    return True


def _sync_recommendations(user: User, existing: list[AdvisorRecommendation], new: list[dict], currency: str,
                          db: AsyncSession) -> None:
    by_key = {r.rec_key: r for r in existing}
    seen = set()
    for r in new:
        key = r["key"][:80]
        seen.add(key)
        values = dict(
            title=r["title"][:200], why=r["why"], impact=r["impact"], risk=r["risk"], effort=r["effort"],
            timeframe=r["timeframe"], priority=r["priority"], amount=r.get("amount") or None, currency=currency,
            agents=r["agents"], action_steps=r["action_steps"], active=True,
        )
        row = by_key.get(key)
        if row is None:
            db.add(AdvisorRecommendation(user_id=user.id, rec_key=key, status=RecommendationStatus.OPEN, **values))
        else:
            for k, v in values.items():
                setattr(row, k, v)
    for key, row in by_key.items():
        if key not in seen:
            row.active = False


# ---- read side -----------------------------------------------------------------------------------

def _agent_summary(spec_key: AgentKey, st: AgentState | None) -> dict:
    spec = AGENTS_BY_KEY[spec_key]
    ins = (st.insight if st else None) or {}
    return {
        "key": spec.key, "name": spec.name, "description": spec.description,
        "status": st.status if st else AgentStatus.PENDING, "health": ins.get("health"), "summary": ins.get("summary"),
        "metrics": ((st.facts or {}).get("metrics") if st else None) or [],
        "recommendations_count": len(ins.get("recommendations") or []),
        "version": st.version if st else 0, "provider": st.provider if st else None,
        "generated_at": st.generated_at if st else None,
    }


async def list_agents(db: AsyncSession, user: User) -> list[dict]:
    states = await _states(db, user)
    return [_agent_summary(spec.key, states.get(spec.key)) for spec in AGENTS]


async def get_agent(db: AsyncSession, user: User, key: str) -> dict:
    try:
        agent_key = AgentKey(key.upper())
    except ValueError:
        raise NotFoundError("Agent not found", ErrorCode.AGENT_NOT_FOUND)
    if agent_key not in AGENTS_BY_KEY:
        raise NotFoundError("Agent not found", ErrorCode.AGENT_NOT_FOUND)
    st = (await _states(db, user)).get(agent_key)
    ins = (st.insight if st else None) or {}
    facts = {k: v for k, v in ((st.facts if st else None) or {}).items() if k != "metrics"} or None
    return {
        **_agent_summary(agent_key, st),
        "findings": ins.get("findings") or [], "recommendations": ins.get("recommendations") or [],
        "data_gaps": ins.get("data_gaps") or [], "facts": facts, "error": st.error if st else None,
    }


def _rec_view(r: AdvisorRecommendation, step: int) -> dict:
    return {
        "id": r.id, "key": r.rec_key, "step": step, "title": r.title, "why": r.why, "action_steps": r.action_steps,
        "impact": r.impact, "risk": r.risk, "effort": r.effort, "timeframe": r.timeframe, "amount": r.amount,
        "currency": r.currency, "agents": r.agents, "status": r.status, "status_changed_at": r.status_changed_at,
        "updated_at": r.updated_at,
    }


async def recommendations(db: AsyncSession, user: User) -> tuple[list[dict], list[dict]]:
    """(steps to act on, completed). Steps are numbered in priority order."""
    rows = list((await db.execute(
        select(AdvisorRecommendation).where(AdvisorRecommendation.user_id == user.id)
        .order_by(AdvisorRecommendation.priority, AdvisorRecommendation.id)
    )).scalars())
    open_ = [r for r in rows if r.active and r.status in (RecommendationStatus.OPEN, RecommendationStatus.IN_PROGRESS)]
    done = [r for r in rows if r.status in (RecommendationStatus.DONE, RecommendationStatus.DISMISSED)]
    done.sort(key=lambda r: r.status_changed_at or r.updated_at, reverse=True)
    return [_rec_view(r, i) for i, r in enumerate(open_, 1)], [_rec_view(r, 0) for r in done]


async def update_recommendation(db: AsyncSession, user: User, rec_id: int, status: RecommendationStatus) -> dict:
    row = (await db.execute(select(AdvisorRecommendation).where(
        AdvisorRecommendation.id == rec_id, AdvisorRecommendation.user_id == user.id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Recommendation not found", ErrorCode.RECOMMENDATION_NOT_FOUND)
    if row.status != status:
        row.status = status
        row.status_changed_at = utcnow()
    await db.commit()
    await db.refresh(row)
    steps, done = await recommendations(db, user)
    return next((r for r in steps + done if r["id"] == row.id), _rec_view(row, 0))


async def overview(db: AsyncSession, user: User) -> dict:
    states = await _states(db, user)
    chief = states.get(AgentKey.CHIEF)
    ins = (chief.insight if chief else None) or {}
    steps, done = await recommendations(db, user)
    return {
        "ready": bool(chief and chief.insight),
        "headline": ins.get("headline"), "summary": ins.get("summary"), "health": ins.get("health"),
        "currency": (chief.facts or {}).get("currency") if chief else None,
        "balance_sheet": (chief.facts or {}).get("balance_sheet") if chief else None,
        "conflicts": ins.get("conflicts") or [],
        "steps": steps, "completed": done,
        "agents": [_agent_summary(spec.key, states.get(spec.key)) for spec in AGENTS],
        "generated_at": chief.generated_at if chief else None, "provider": chief.provider if chief else None,
        "fx_rates": ((chief.facts or {}).get("fx_rates") if chief else None) or {},
    }


async def status(db: AsyncSession, user: User) -> dict:
    states = await _states(db, user)
    last = (await db.execute(select(AnalysisRun).where(AnalysisRun.user_id == user.id)
                             .order_by(AnalysisRun.id.desc()).limit(1))).scalar_one_or_none()
    running = await _running_run(db, user) is not None
    stale = False
    if not running and states:
        provider_name = get_llm_provider().name
        profile = await build_profile(db, user)
        for spec in AGENTS:
            st = states.get(spec.key)
            h = _hash({"version": spec.version, "provider": provider_name, "facts": spec.facts(profile)})
            if st is None or st.input_hash != h:
                stale = True
                break
    chief = states.get(AgentKey.CHIEF)
    return {
        "ready": bool(chief and chief.insight), "running": running, "stale": stale, "last_run": last,
        "agents": [
            {"key": k.value, "status": (states[k].status if k in states else AgentStatus.PENDING).value,
             "version": states[k].version if k in states else 0}
            for k in [s.key for s in AGENTS] + [AgentKey.CHIEF]
        ],
    }


# ---- chat ----------------------------------------------------------------------------------------

async def _chat_context(db: AsyncSession, user: User) -> dict:
    states = await _states(db, user)
    chief = states.get(AgentKey.CHIEF)
    if not chief or not chief.insight:
        raise AppError(409, "Your analysis isn't ready yet. Connect your accounts or refresh the analysis first.",
                       ErrorCode.ADVISOR_NOT_READY)
    steps, done = await recommendations(db, user)
    facts = chief.facts or {}
    return {
        "currency": facts.get("currency"),
        "balance_sheet": facts.get("balance_sheet"),
        "cashflow": facts.get("cashflow"),
        "chief": {k: chief.insight.get(k) for k in ("headline", "summary", "health", "conflicts")},
        "recommendations": [
            {k: r[k] for k in ("key", "step", "title", "why", "status", "amount", "agents")} for r in steps + done
        ],
        "agents": {
            spec.key.value: {
                "name": spec.name,
                "health": (states[spec.key].insight or {}).get("health"),
                "summary": (states[spec.key].insight or {}).get("summary"),
                "metrics": (states[spec.key].facts or {}).get("metrics", []),
                "recommendations": [{k: r[k] for k in ("title", "why", "amount")}
                                    for r in (states[spec.key].insight or {}).get("recommendations", [])],
                "data_gaps": (states[spec.key].insight or {}).get("data_gaps", []),
            }
            for spec in AGENTS if spec.key in states and states[spec.key].insight
        },
    }


async def chat(db: AsyncSession, user: User, message: str) -> tuple[ChatMessage, ChatMessage]:
    context = await _chat_context(db, user)
    rows = list((await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(CHAT_HISTORY_TURNS * 2)
    )).scalars())[::-1]
    history: list[dict] = []
    for m in rows:  # keep strict user/assistant alternation, starting with the user
        role = m.role.value
        if (not history and role != "user") or (history and history[-1]["role"] == role):
            continue
        history.append({"role": role, "content": m.content})
    if history and history[-1]["role"] == "user":
        history.pop()

    provider = get_llm_provider()
    try:
        reply, agents = await provider.chat(context, history, message)
    except LLMError as e:
        logger.warning("chat fell back to offline: %s", e)
        reply, agents = await OfflineProvider().chat(context, history, message)
        reply = "(The AI assistant is unavailable right now, so this answer comes from your saved analysis.)\n\n" + reply

    question = ChatMessage(user_id=user.id, role=ChatRole.USER, content=message)
    answer = ChatMessage(user_id=user.id, role=ChatRole.ASSISTANT, content=reply, agents=agents)
    db.add_all([question, answer])
    await db.commit()
    return question, answer


async def chat_history(db: AsyncSession, user: User, limit: int) -> list[ChatMessage]:
    rows = list((await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(limit)
    )).scalars())
    return rows[::-1]


# ---- extra data ----------------------------------------------------------------------------------

async def add_extra_data(db: AsyncSession, user: User, category: str, data: dict, extracted_by: str = "manual") -> CustomerExtraData:
    row = CustomerExtraData(user_id=user.id, category=category, source="FORM", extracted_by=extracted_by, data=data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_extra_data(db: AsyncSession, user: User) -> list[CustomerExtraData]:
    return list((await db.execute(
        select(CustomerExtraData).where(CustomerExtraData.user_id == user.id).order_by(CustomerExtraData.id)
    )).scalars())
