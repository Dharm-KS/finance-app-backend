from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, TimestampMixin, enum_column
from app.models.enums import CreditProviderName, CreditReportStatus

if TYPE_CHECKING:
    from app.models.credit_account import CreditAccount
    from app.models.user import User


class CreditReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "credit_reports"
    __table_args__ = (Index("ix_credit_reports_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[CreditProviderName] = mapped_column(enum_column(CreditProviderName, 20), nullable=False)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. CONSUMER_CIR
    report_reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    credit_score: Mapped[int | None] = mapped_column(Integer)
    score_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    report_status: Mapped[CreditReportStatus] = mapped_column(enum_column(CreditReportStatus, 20), nullable=False)
    # Raw provider payload, kept for audit/re-parsing. Deferred so it is never loaded by accident
    # and never serialised in API responses. Normalised data lives in credit_accounts.
    raw_report: Mapped[dict[str, Any] | None] = deferred(mapped_column(JSON))

    user: Mapped["User"] = relationship(back_populates="credit_reports")
    accounts: Mapped[list["CreditAccount"]] = relationship(
        back_populates="credit_report", cascade="all, delete-orphan", passive_deletes=True,
        order_by="CreditAccount.id",
    )

    @property
    def total_outstanding(self) -> Decimal:
        return sum((a.current_balance for a in self.accounts if a.is_active), Decimal("0"))
