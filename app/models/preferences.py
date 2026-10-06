from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, TimestampMixin, enum_column
from app.models.enums import InsightTone

if TYPE_CHECKING:
    from app.models.user import User


class UserPreferences(IdMixin, TimestampMixin, Base):
    """"How your twin talks to you" - the last onboarding screen."""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    insight_tone: Mapped[InsightTone] = mapped_column(
        enum_column(InsightTone, 20), default=InsightTone.BALANCED, nullable=False
    )
    vesting_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tax_deadline_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weekly_digest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="preferences")
