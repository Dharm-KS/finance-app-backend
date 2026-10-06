from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, TimestampMixin, enum_column
from app.models.enums import OnboardingStep

if TYPE_CHECKING:
    from app.models.user import User


class Onboarding(IdMixin, TimestampMixin, Base):
    __tablename__ = "onboarding"

    # unique=True -> exactly one onboarding row per user (prevents duplicates at DB level)
    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    current_step: Mapped[OnboardingStep] = mapped_column(
        enum_column(OnboardingStep, 30), default=OnboardingStep.REGISTRATION, nullable=False
    )
    registration_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credit_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    financial_profile_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    equity_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    equity_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    goals_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferences_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="onboarding")
