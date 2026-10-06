"""Registration / login / logout orchestration."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ErrorCode, NotFoundError
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_client_token,
    decode_access_token,
    verify_client_credentials,
)
from app.core.time import utcnow
from app.models.enums import OtpPurpose, UserStatus
from app.models.onboarding import Onboarding
from app.models.otp import OtpSession
from app.models.user import RevokedToken, User
from app.services import onboarding_service, otp_service
from app.services.otp_service import ClientInfo


@dataclass
class AuthResult:
    access_token: str
    expires_at: datetime
    user: User
    onboarding: Onboarding
    is_new_user: bool


async def get_user_by_mobile(db: AsyncSession, mobile: str) -> User | None:
    return (await db.execute(select(User).where(User.mobile == mobile))).scalar_one_or_none()


def _ensure_active(user: User) -> None:
    if user.status != UserStatus.ACTIVE:
        raise AppError(403, "This account is not active. Please contact support.", ErrorCode.USER_INACTIVE)


def _otp_response(session: OtpSession) -> dict:
    return {
        "otp_session_id": session.uuid,
        "mobile": session.mobile,
        "expires_in_seconds": settings.OTP_EXPIRY_SECONDS,
        "resend_after_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
    }


async def _issue_token(db: AsyncSession, user: User, is_new: bool) -> AuthResult:
    user.last_login_at = utcnow()
    onboarding = await onboarding_service.refresh(db, user)
    await db.commit()
    token, expires_at, _ = create_access_token(user.uuid)
    return AuthResult(token, expires_at, user, onboarding, is_new)


# ---- app client token ------------------------------------------------------------------------

def issue_client_token(client_id: str, client_secret: str) -> dict:
    if not verify_client_credentials(client_id, client_secret):
        raise AppError(401, "Invalid client credentials", ErrorCode.INVALID_CLIENT)
    token, expires_at = create_client_token(client_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.CLIENT_TOKEN_EXPIRE_MINUTES * 60,
        "expires_at": expires_at,
    }


# ---- registration -----------------------------------------------------------------------------

async def register_request_otp(db: AsyncSession, mobile: str, client: ClientInfo) -> dict:
    if await get_user_by_mobile(db, mobile):
        raise ConflictError("This mobile number is already registered. Please log in.", ErrorCode.MOBILE_ALREADY_REGISTERED)
    session = await otp_service.request_otp(
        db, mobile=mobile, purpose=OtpPurpose.REGISTER, user_id=None, client=client
    )
    await db.commit()
    return _otp_response(session)


async def register_verify_otp(db: AsyncSession, mobile: str, otp: str, name: str | None) -> AuthResult:
    if await get_user_by_mobile(db, mobile):
        raise ConflictError("This mobile number is already registered. Please log in.", ErrorCode.MOBILE_ALREADY_REGISTERED)

    session = await otp_service.verify_otp(db, mobile=mobile, purpose=OtpPurpose.REGISTER, otp=otp)

    user = User(mobile=mobile, name=name, is_verified=True, status=UserStatus.ACTIVE)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("This mobile number is already registered. Please log in.", ErrorCode.MOBILE_ALREADY_REGISTERED)
    session.user_id = user.id
    return await _issue_token(db, user, is_new=True)


# ---- login ------------------------------------------------------------------------------------

async def login_request_otp(db: AsyncSession, mobile: str, client: ClientInfo) -> dict:
    user = await get_user_by_mobile(db, mobile)
    if user is None:
        raise NotFoundError("This mobile number is not registered. Please sign up.", ErrorCode.MOBILE_NOT_REGISTERED)
    _ensure_active(user)
    session = await otp_service.request_otp(
        db, mobile=mobile, purpose=OtpPurpose.LOGIN, user_id=user.id, client=client
    )
    await db.commit()
    return _otp_response(session)


async def login_verify_otp(db: AsyncSession, mobile: str, otp: str) -> AuthResult:
    user = await get_user_by_mobile(db, mobile)
    if user is None:
        raise NotFoundError("This mobile number is not registered. Please sign up.", ErrorCode.MOBILE_NOT_REGISTERED)
    _ensure_active(user)
    await otp_service.verify_otp(db, mobile=mobile, purpose=OtpPurpose.LOGIN, otp=otp)
    return await _issue_token(db, user, is_new=False)


# ---- session / token --------------------------------------------------------------------------

async def authenticate_token(db: AsyncSession, token: str) -> tuple[User, TokenPayload]:
    payload = decode_access_token(token)
    revoked = (
        await db.execute(select(RevokedToken.id).where(RevokedToken.jti == payload.jti))
    ).scalar_one_or_none()
    if revoked:
        raise AppError(401, "Session has been logged out. Please log in again.", ErrorCode.TOKEN_REVOKED)

    user = (await db.execute(select(User).where(User.uuid == payload.user_uuid))).scalar_one_or_none()
    if user is None:
        raise AppError(401, "User not found for this token", ErrorCode.USER_NOT_FOUND)
    _ensure_active(user)
    return user, payload


async def logout(db: AsyncSession, user: User, token: TokenPayload) -> None:
    db.add(RevokedToken(jti=token.jti, user_id=user.id, expires_at=token.expires_at))
    try:
        await db.commit()
    except IntegrityError:  # already logged out with this token
        await db.rollback()


async def update_me(db: AsyncSession, user: User, *, name: str | None, email: str | None, fields_set: set[str]) -> Onboarding:
    if "name" in fields_set and name:
        user.name = name
    if "email" in fields_set:
        user.email = email.lower() if email else None
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("This email is already in use")
    onboarding = await onboarding_service.refresh(db, user)
    await db.commit()
    return onboarding
