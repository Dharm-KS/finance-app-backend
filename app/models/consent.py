from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, CreatedAtMixin, IdMixin, UTCDateTime, enum_column
from app.models.enums import ConsentStatus, ConsentType

if TYPE_CHECKING:
    from app.models.user import User


class Consent(IdMixin, CreatedAtMixin, Base):
    """Append-only consent audit log.

    Rows are never updated: granting and revoking each insert a new row. The user's
    effective consent for a type is the most recent row for that type.
    """

    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_user_id_consent_type_created_at", "user_id", "consent_type", "created_at"),)

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[ConsentType] = mapped_column(enum_column(ConsentType, 30), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)  # exact text the user agreed to
    status: Mapped[ConsentStatus] = mapped_column(enum_column(ConsentStatus, 20), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="consents")
