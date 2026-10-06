from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    BigIntPK,
    CreatedAtMixin,
    IdMixin,
    TimestampMixin,
    UTCDateTime,
    enum_column,
    new_uuid,
)
from app.models.enums import UserStatus

if TYPE_CHECKING:
    from app.models.consent import Consent
    from app.models.credit_report import CreditReport
    from app.models.equity import EquityHolding
    from app.models.financial_profile import FinancialProfile
    from app.models.goal import FinancialGoal
    from app.models.onboarding import Onboarding
    from app.models.otp import OtpSession
    from app.models.preferences import UserPreferences
    from app.models.risk_profile import RiskProfile


# Deleting a user removes all of their data (passive_deletes -> rely on DB ON DELETE CASCADE).
_CASCADE = {"cascade": "all, delete-orphan", "passive_deletes": True}


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Public identifier (used in JWT `sub`). The numeric id never leaves the backend.
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid, nullable=False)
    mobile: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # E.164
    name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        enum_column(UserStatus, 20), default=UserStatus.ACTIVE, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    otp_sessions: Mapped[list["OtpSession"]] = relationship(back_populates="user", **_CASCADE)
    consents: Mapped[list["Consent"]] = relationship(back_populates="user", **_CASCADE)
    onboarding: Mapped["Onboarding | None"] = relationship(back_populates="user", uselist=False, **_CASCADE)
    credit_reports: Mapped[list["CreditReport"]] = relationship(back_populates="user", **_CASCADE)
    financial_profile: Mapped["FinancialProfile | None"] = relationship(
        back_populates="user", uselist=False, **_CASCADE
    )
    equity_holdings: Mapped[list["EquityHolding"]] = relationship(back_populates="user", **_CASCADE)
    risk_profile: Mapped["RiskProfile | None"] = relationship(back_populates="user", uselist=False, **_CASCADE)
    goals: Mapped[list["FinancialGoal"]] = relationship(back_populates="user", **_CASCADE)
    preferences: Mapped["UserPreferences | None"] = relationship(back_populates="user", uselist=False, **_CASCADE)


class RevokedToken(IdMixin, CreatedAtMixin, Base):
    """Denylist of JWT ids invalidated via logout. Rows can be purged once ``expires_at`` passes."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True, nullable=False)
