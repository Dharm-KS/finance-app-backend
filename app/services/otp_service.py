"""OTP lifecycle: issue, verify, expire, lock.

Only this module knows how OTPs are generated/checked; it delegates delivery to an
:class:`~app.services.providers.otp.OtpProvider`. Swapping the fixed MVP OTP for a real SMS
provider does not touch the API layer.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ErrorCode
from app.core.security import hash_otp, verify_otp_hash
from app.core.time import ensure_utc, utcnow
from app.models.base import new_uuid
from app.models.enums import OtpPurpose, OtpStatus
from app.models.otp import OtpSession
from app.services.providers.otp import OtpProvider, get_otp_provider


@dataclass(frozen=True)
class ClientInfo:
    ip_address: str | None = None
    user_agent: str | None = None


async def _latest_session(db: AsyncSession, mobile: str, purpose: OtpPurpose, lock: bool = False) -> OtpSession | None:
    stmt = (
        select(OtpSession)
        .where(OtpSession.mobile == mobile, OtpSession.purpose == purpose)
        .order_by(OtpSession.created_at.desc(), OtpSession.id.desc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def request_otp(
    db: AsyncSession,
    *,
    mobile: str,
    purpose: OtpPurpose,
    user_id: int | None,
    client: ClientInfo,
    provider: OtpProvider | None = None,
) -> OtpSession:
    """Create a new OTP session and dispatch the OTP. Caller commits."""
    provider = provider or get_otp_provider()
    now = utcnow()

    latest = await _latest_session(db, mobile, purpose, lock=True)
    if latest and latest.status == OtpStatus.PENDING:
        elapsed = (now - ensure_utc(latest.created_at)).total_seconds()
        if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1
            raise AppError(
                429, f"Please wait {wait} seconds before requesting a new OTP",
                ErrorCode.OTP_RESEND_TOO_SOON, retry_after_seconds=wait,
            )

    # Hard cap per mobile across purposes: limits SMS cost and OTP guessing across resends.
    window_start = now - timedelta(seconds=settings.OTP_SEND_WINDOW_SECONDS)
    sent, oldest = (
        await db.execute(
            select(func.count(OtpSession.id), func.min(OtpSession.created_at))
            .where(OtpSession.mobile == mobile, OtpSession.created_at > window_start)
        )
    ).one()
    if sent >= settings.OTP_MAX_SENDS_PER_WINDOW:
        oldest_utc = ensure_utc(oldest) if oldest else now
        wait = max(1, int((oldest_utc + timedelta(seconds=settings.OTP_SEND_WINDOW_SECONDS) - now).total_seconds()) + 1)
        raise AppError(
            429, f"Too many OTP requests. Please try again in {max(1, round(wait / 60))} minute(s).",
            ErrorCode.OTP_LIMIT_REACHED, retry_after_seconds=wait,
        )

    # Only the newest OTP is valid.
    await db.execute(
        update(OtpSession)
        .where(OtpSession.mobile == mobile, OtpSession.purpose == purpose, OtpSession.status == OtpStatus.PENDING)
        .values(status=OtpStatus.SUPERSEDED)
    )

    otp = provider.generate_otp()
    session_uuid = new_uuid()
    session = OtpSession(
        uuid=session_uuid,
        user_id=user_id,
        mobile=mobile,
        purpose=purpose,
        status=OtpStatus.PENDING,
        otp_hash=hash_otp(otp, session_uuid),
        provider=provider.name,
        attempts=0,
        max_attempts=settings.OTP_MAX_ATTEMPTS,
        expires_at=now + timedelta(seconds=settings.OTP_EXPIRY_SECONDS),
        ip_address=client.ip_address,
        user_agent=(client.user_agent or "")[:255] or None,
    )
    db.add(session)
    await db.flush()
    await provider.send(mobile, otp, purpose)
    return session


async def verify_otp(db: AsyncSession, *, mobile: str, purpose: OtpPurpose, otp: str) -> OtpSession:
    """Validate the OTP for the latest session.

    Failure states (attempt counts, expiry, lock) are committed before raising so they persist.
    On success the session is marked VERIFIED and flushed; the caller commits together with
    whatever it does next (e.g. creating the user) so the whole step is atomic.
    """
    session = await _latest_session(db, mobile, purpose, lock=True)
    if session is None or session.status in (OtpStatus.SUPERSEDED, OtpStatus.VERIFIED):
        raise AppError(400, "No active OTP. Please request a new OTP.", ErrorCode.OTP_NOT_REQUESTED)
    if session.status == OtpStatus.LOCKED:
        raise AppError(429, "Too many incorrect attempts. Please request a new OTP.", ErrorCode.OTP_TOO_MANY_ATTEMPTS)
    if session.status == OtpStatus.EXPIRED or utcnow() > ensure_utc(session.expires_at):
        session.status = OtpStatus.EXPIRED
        await db.commit()
        raise AppError(400, "OTP has expired. Please request a new OTP.", ErrorCode.OTP_EXPIRED)

    session.attempts += 1
    if not verify_otp_hash(otp, session.uuid, session.otp_hash):
        remaining = session.max_attempts - session.attempts
        if remaining <= 0:
            session.status = OtpStatus.LOCKED
            await db.commit()
            raise AppError(429, "Too many incorrect attempts. Please request a new OTP.", ErrorCode.OTP_TOO_MANY_ATTEMPTS)
        await db.commit()
        raise AppError(400, f"Invalid OTP. {remaining} attempt(s) remaining.", ErrorCode.OTP_INVALID)

    session.status = OtpStatus.VERIFIED
    session.verified_at = utcnow()
    await db.flush()
    return session
