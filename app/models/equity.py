from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, Money, TimestampMixin, enum_column
from app.models.enums import Currency, EquitySource

if TYPE_CHECKING:
    from app.models.user import User


class EquityHolding(IdMixin, TimestampMixin, Base):
    """Employer equity (RSU / ESOP / ESPP) - "Your Equity Picture" screen."""

    __tablename__ = "equity_holdings"

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    security_name: Mapped[str] = mapped_column(String(120), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20))
    vested_value: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    unvested_value: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    currency: Mapped[Currency] = mapped_column(enum_column(Currency, 3), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_vest_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[EquitySource] = mapped_column(
        enum_column(EquitySource, 20), default=EquitySource.MANUAL, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="equity_holdings")
