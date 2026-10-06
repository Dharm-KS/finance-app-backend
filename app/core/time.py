"""UTC time helpers. All timestamps are handled as timezone-aware UTC internally."""

from datetime import date, datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utctoday() -> date:
    return utcnow().date()


def ensure_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC (that is how they are stored in the DB)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
