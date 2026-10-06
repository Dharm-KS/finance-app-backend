from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, Money, TimestampMixin, enum_column
from app.models.enums import GoalPriority, GoalStatus, GoalType

if TYPE_CHECKING:
    from app.models.user import User


class FinancialGoal(IdMixin, TimestampMixin, Base):
    __tablename__ = "financial_goals"
    __table_args__ = (Index("ix_financial_goals_user_id_status", "user_id", "status"),)

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    goal_type: Mapped[GoalType] = mapped_column(enum_column(GoalType, 50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[GoalPriority] = mapped_column(enum_column(GoalPriority, 20), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(
        enum_column(GoalStatus, 20), default=GoalStatus.ACTIVE, nullable=False
    )
    # Extra user inputs some goals are sized from (e.g. property_value for HOME_DOWN_PAYMENT).
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship(back_populates="goals")
