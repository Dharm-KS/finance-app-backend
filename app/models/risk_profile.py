from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, Percent, TimestampMixin, enum_column
from app.models.enums import RiskTolerance

if TYPE_CHECKING:
    from app.models.user import User


class RiskProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "risk_profiles"
    __table_args__ = (
        CheckConstraint("max_drawdown_percent >= 0 AND max_drawdown_percent <= 100", name="max_drawdown_range"),
        CheckConstraint(
            "single_stock_limit_percent >= 0 AND single_stock_limit_percent <= 100", name="single_stock_range"
        ),
        CheckConstraint("planning_horizon_years >= 1 AND planning_horizon_years <= 50", name="horizon_range"),
    )

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(enum_column(RiskTolerance, 20), nullable=False)
    max_drawdown_percent: Mapped[Decimal] = mapped_column(Percent(), nullable=False)
    single_stock_limit_percent: Mapped[Decimal] = mapped_column(Percent(), nullable=False)
    planning_horizon_years: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="risk_profile")
