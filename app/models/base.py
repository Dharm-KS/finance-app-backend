"""Declarative base, shared column types and mixins."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, Numeric, TypeDecorator
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time import ensure_utc, utcnow

# Deterministic constraint names -> clean, reproducible Alembic migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# BIGINT on MySQL, INTEGER on SQLite (SQLite only auto-increments INTEGER PKs; used in tests).
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in the DB (MySQL DATETIME has no timezone), returns aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        return ensure_utc(value).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return ensure_utc(value)


def Money() -> Numeric:  # noqa: N802 - reads like a type
    """Monetary amount: DECIMAL(18,2). Never use floats for money."""
    return Numeric(18, 2, asdecimal=True)


def Percent() -> Numeric:  # noqa: N802
    return Numeric(5, 2, asdecimal=True)


def enum_column(enum_cls: type[PyEnum], length: int = 40) -> SAEnum:
    """Enum stored as VARCHAR (not native MySQL ENUM) so new values don't need ALTER TABLE."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def new_uuid() -> str:
    return str(uuid.uuid4())


class IdMixin:
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True, sort_order=-100)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, sort_order=100)


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False, sort_order=101
    )
