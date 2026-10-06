from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, IdMixin, TimestampMixin, UTCDateTime, enum_column, new_uuid
from app.models.enums import OtpPurpose, OtpStatus

if TYPE_CHECKING:
    from app.models.user import User


class OtpSession(IdMixin, TimestampMixin, Base):
    """One OTP challenge. The OTP itself is never stored, only a keyed hash of it."""

    __tablename__ = "otp_sessions"
    __table_args__ = (Index("ix_otp_sessions_mobile_purpose_status", "mobile", "purpose", "status"),)

    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid, nullable=False)
    # Nullable: during registration the user does not exist yet.
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mobile: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[OtpPurpose] = mapped_column(enum_column(OtpPurpose, 20), nullable=False)
    status: Mapped[OtpStatus] = mapped_column(
        enum_column(OtpStatus, 20), default=OtpStatus.PENDING, nullable=False
    )
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User | None"] = relationship(back_populates="otp_sessions")
