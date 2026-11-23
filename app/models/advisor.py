"""Persistent AI-advisor state per customer.

- ``agent_states``: one row per (customer, agent). Holds the facts the agent was given, its
  latest insight and the hash of its inputs, so an agent is regenerated only when its inputs
  change - never from scratch on every login or question.
- ``advisor_recommendations``: the Chief agent's prioritized recommendations. Keyed by a stable
  ``rec_key`` so the customer's status (done / dismissed) survives regenerations.
- ``analysis_runs``: audit of every (re)analysis and what triggered it.
- ``chat_messages``: the customer's conversation with the Chief agent.
- ``customer_extra_data``: financial details collected through other forms (Gemini extraction later).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, CreatedAtMixin, IdMixin, Money, TimestampMixin, UTCDateTime, enum_column
from app.models.enums import AgentKey, AgentStatus, AnalysisRunStatus, ChatRole, RecommendationStatus


def _user_fk():
    return mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class AgentState(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_states"
    __table_args__ = (UniqueConstraint("user_id", "agent_key"),)

    user_id: Mapped[int] = _user_fk()
    agent_key: Mapped[AgentKey] = mapped_column(enum_column(AgentKey, 20), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(enum_column(AgentStatus, 20), nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    insight: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(30))  # offline | claude
    model: Mapped[str | None] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # +1 per regeneration
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error: Mapped[str | None] = mapped_column(String(500))


class AdvisorRecommendation(IdMixin, TimestampMixin, Base):
    __tablename__ = "advisor_recommendations"
    __table_args__ = (
        UniqueConstraint("user_id", "rec_key"),
        Index("ix_advisor_recommendations_user_id_active_priority", "user_id", "active", "priority"),
    )

    user_id: Mapped[int] = _user_fk()
    rec_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(String(10), nullable=False)  # HIGH | MEDIUM | LOW
    risk: Mapped[str] = mapped_column(String(10), nullable=False)  # risk of NOT acting
    effort: Mapped[str] = mapped_column(String(10), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = do first
    amount: Mapped[Decimal | None] = mapped_column(Money())
    currency: Mapped[str | None] = mapped_column(String(3))
    agents: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    action_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        enum_column(RecommendationStatus, 20), default=RecommendationStatus.OPEN, nullable=False
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # in the latest Chief run


class AnalysisRun(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[int] = _user_fk()
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[AnalysisRunStatus] = mapped_column(enum_column(AnalysisRunStatus, 20), nullable=False)
    agents_regenerated: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    agents_unchanged: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error: Mapped[str | None] = mapped_column(String(500))


class ChatMessage(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[int] = _user_fk()
    role: Mapped[ChatRole] = mapped_column(enum_column(ChatRole, 10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agents: Mapped[list[str] | None] = mapped_column(JSON)  # agents whose knowledge the answer used


class CustomerExtraData(IdMixin, TimestampMixin, Base):
    __tablename__ = "customer_extra_data"
    __table_args__ = (Index("ix_customer_extra_data_user_id_category", "user_id", "category"),)

    user_id: Mapped[int] = _user_fk()
    category: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. INSURANCE, ESTATE, TAX, INCOME
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # FORM | DOCUMENT
    extracted_by: Mapped[str] = mapped_column(String(30), nullable=False)  # manual | gemini
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
