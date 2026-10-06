from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, Money, Percent, TimestampMixin, enum_column
from app.models.enums import CreditAccountStatus, CreditAccountType

if TYPE_CHECKING:
    from app.models.credit_report import CreditReport


class CreditAccount(IdMixin, TimestampMixin, Base):
    """Normalised tradeline from a credit report (provider-agnostic shape)."""

    __tablename__ = "credit_accounts"

    credit_report_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("credit_reports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_type: Mapped[CreditAccountType] = mapped_column(enum_column(CreditAccountType, 30), nullable=False)
    lender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_number_masked: Mapped[str] = mapped_column(String(32), nullable=False)
    sanctioned_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(Money())
    emi_amount: Mapped[Decimal | None] = mapped_column(Money())
    interest_rate: Mapped[Decimal | None] = mapped_column(Percent())
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    remaining_months: Mapped[int | None] = mapped_column(Integer)
    account_status: Mapped[CreditAccountStatus] = mapped_column(enum_column(CreditAccountStatus, 20), nullable=False)
    # Highest days-past-due reported in the account's payment history (0 = always on time).
    dpd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opened_date: Mapped[date | None] = mapped_column(Date)
    closed_date: Mapped[date | None] = mapped_column(Date)

    credit_report: Mapped["CreditReport"] = relationship(back_populates="accounts")

    @property
    def is_active(self) -> bool:
        return self.account_status == CreditAccountStatus.ACTIVE
