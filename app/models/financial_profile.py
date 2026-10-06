from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, Money, TimestampMixin, enum_column
from app.models.enums import Currency, EmploymentType

if TYPE_CHECKING:
    from app.models.user import User


class FinancialProfile(IdMixin, TimestampMixin, Base):
    """The "Your Money" screen. One row per user; amounts are in ``currency``."""

    __tablename__ = "financial_profiles"

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    annual_income: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    currency: Mapped[Currency] = mapped_column(enum_column(Currency, 3), nullable=False)
    monthly_spend: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    cash_reserve: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    monthly_emi: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    total_debt: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    investments: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    # Not collected on the onboarding Money screen; filled in later.
    employment_type: Mapped[EmploymentType | None] = mapped_column(enum_column(EmploymentType, 30))
    age: Mapped[int | None] = mapped_column(Integer)
    dependents: Mapped[int | None] = mapped_column(Integer)
    insurance_cover: Mapped[Decimal | None] = mapped_column(Money())

    user: Mapped["User"] = relationship(back_populates="financial_profile")
