"""Schemas for the AI advisor: agent / Chief outputs (validated whether they come from Claude or
the rule engine) and the API request/response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentKey, AgentStatus, AggregatorConnectionStatus, RecommendationStatus
from app.schemas.common import MoneyOut

Level = Literal["HIGH", "MEDIUM", "LOW"]
Health = Literal["GOOD", "WATCH", "ACTION_NEEDED"]
Severity = Literal["INFO", "WARNING", "CRITICAL"]
Timeframe = Literal["NOW", "THIS_MONTH", "THIS_QUARTER", "THIS_YEAR"]


# ---- what an agent produces -----------------------------------------------------------------------

class Finding(BaseModel):
    title: str
    detail: str
    severity: Severity


class AgentRecommendation(BaseModel):
    key: str = Field(description="Stable kebab-case id, e.g. diversify-single-stock")
    title: str
    why: str
    action_steps: list[str]
    impact: Level
    effort: Level
    timeframe: Timeframe
    amount: float = Field(description="Amount involved in the main currency; 0 if not applicable")


class AgentInsight(BaseModel):
    summary: str
    health: Health
    findings: list[Finding]
    recommendations: list[AgentRecommendation]
    data_gaps: list[str]


class Conflict(BaseModel):
    title: str
    agents: list[str]
    detail: str
    resolution: str


class ChiefRecommendation(AgentRecommendation):
    risk: Level = Field(description="Risk of NOT acting")
    priority: int = Field(description="1 = do first")
    agents: list[str]


class ChiefInsight(BaseModel):
    headline: str
    summary: str
    health: Health
    conflicts: list[Conflict]
    recommendations: list[ChiefRecommendation]


def _strict(schema: dict) -> dict:
    """JSON schema for structured outputs: every object closed and every property required."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"])
        for v in schema["properties"].values():
            _strict(v)
    elif schema.get("type") == "array":
        _strict(schema["items"])
    return schema


def _obj(**props) -> dict:
    return {"type": "object", "properties": props}


_S, _N, _I = {"type": "string"}, {"type": "number"}, {"type": "integer"}
_LEVEL = {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]}
_STR_LIST = {"type": "array", "items": _S}
_REC_PROPS = dict(
    key=_S, title=_S, why=_S, action_steps=_STR_LIST, impact=_LEVEL, effort=_LEVEL,
    timeframe={"type": "string", "enum": ["NOW", "THIS_MONTH", "THIS_QUARTER", "THIS_YEAR"]}, amount=_N,
)
_HEALTH = {"type": "string", "enum": ["GOOD", "WATCH", "ACTION_NEEDED"]}

AGENT_JSON_SCHEMA = _strict(_obj(
    summary=_S, health=_HEALTH,
    findings={"type": "array", "items": _obj(title=_S, detail=_S, severity={"type": "string", "enum": ["INFO", "WARNING", "CRITICAL"]})},
    recommendations={"type": "array", "items": _obj(**_REC_PROPS)},
    data_gaps=_STR_LIST,
))
CHIEF_JSON_SCHEMA = _strict(_obj(
    headline=_S, summary=_S, health=_HEALTH,
    conflicts={"type": "array", "items": _obj(title=_S, agents=_STR_LIST, detail=_S, resolution=_S)},
    recommendations={"type": "array", "items": _obj(**_REC_PROPS, risk=_LEVEL, priority=_I, agents=_STR_LIST)},
))


# ---- API -------------------------------------------------------------------------------------------

class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    status: AggregatorConnectionStatus
    connected_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime


class ConnectionStartOut(BaseModel):
    connection: ConnectionOut
    otp_expires_in_seconds: int


class OtpIn(BaseModel):
    otp: str = Field(min_length=4, max_length=8, examples=["123456"])


class SyncOut(BaseModel):
    connection: ConnectionOut
    data_changed: bool = Field(description="False when the provider returned exactly the same data as last time")
    reports: list[dict[str, Any]]
    analysis: dict[str, Any] | None = Field(description="The analysis run started for this data, if any")


class PushReportsIn(BaseModel):
    """Raw provider responses, exactly as the provider returns them."""

    reports: list[dict[str, Any]] = Field(min_length=1)


class ExtraDataIn(BaseModel):
    category: Literal["INCOME", "TAX", "INSURANCE", "ESTATE", "GOALS", "OTHER"]
    data: dict[str, Any] = Field(description="Structured fields from the form (later: extracted by Gemini)")

    model_config = ConfigDict(
        json_schema_extra={"example": {"category": "ESTATE", "data": {"has_will": False, "pension_beneficiaries_named": False}}}
    )


class ExtraDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    source: str
    extracted_by: str
    data: dict[str, Any]
    created_at: datetime


class AgentSummaryOut(BaseModel):
    key: AgentKey
    name: str
    description: str
    status: AgentStatus
    health: Health | None
    summary: str | None
    metrics: list[dict[str, Any]]
    recommendations_count: int
    version: int
    provider: str | None
    generated_at: datetime | None


class AgentDetailOut(AgentSummaryOut):
    findings: list[Finding]
    recommendations: list[AgentRecommendation]
    data_gaps: list[str]
    facts: dict[str, Any] | None = Field(description="The numbers the agent was given (computed in code)")
    error: str | None


class RecommendationOut(BaseModel):
    id: int
    key: str
    step: int = Field(description="Order to act in (1 = first) among open recommendations")
    title: str
    why: str
    action_steps: list[str]
    impact: Level
    risk: Level
    effort: Level
    timeframe: Timeframe
    amount: MoneyOut | None
    currency: str | None
    agents: list[str]
    status: RecommendationStatus
    status_changed_at: datetime | None
    updated_at: datetime


class RecommendationUpdateIn(BaseModel):
    status: RecommendationStatus


class OverviewOut(BaseModel):
    ready: bool = Field(description="False until the first analysis finishes")
    headline: str | None
    summary: str | None
    health: Health | None
    currency: str | None
    balance_sheet: dict[str, Any] | None
    conflicts: list[Conflict]
    steps: list[RecommendationOut] = Field(description="Open / in-progress recommendations in the order to act on them")
    completed: list[RecommendationOut] = Field(description="Done or dismissed")
    agents: list[AgentSummaryOut]
    generated_at: datetime | None
    provider: str | None
    fx_rates: dict[str, float] = Field(
        default={}, description="Rates used to convert other currencies to the shown currency (units of it per 1)"
    )


class AnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    status: str
    agents_regenerated: list[str]
    agents_unchanged: list[str]
    created_at: datetime
    finished_at: datetime | None
    error: str | None


class AdvisorStatusOut(BaseModel):
    ready: bool
    running: bool
    stale: bool = Field(description="True when the customer's data changed since the last analysis")
    last_run: AnalysisRunOut | None
    agents: list[dict[str, Any]]


class RefreshIn(BaseModel):
    force: bool = Field(default=False, description="Regenerate every agent even if its data didn't change")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(json_schema_extra={"example": {"message": "Should I prepay my mortgage?"}})


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    agents: list[str] | None
    created_at: datetime


class ChatReplyOut(BaseModel):
    question: ChatMessageOut
    answer: ChatMessageOut


class ChatHistoryOut(BaseModel):
    messages: list[ChatMessageOut]


class DataSummaryOut(BaseModel):
    currency: str = Field(description="All amounts are in this currency (converted from each account's own currency)")
    counts: dict[str, int]
    accounts: list[dict[str, Any]]
    portfolios: list[dict[str, Any]]
    loans: list[dict[str, Any]]
    deposits: list[dict[str, Any]]

