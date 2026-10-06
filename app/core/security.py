"""JWT creation/verification and OTP hashing helpers."""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.exceptions import AppError, ErrorCode
from app.core.time import utcnow

TOKEN_TYPE_ACCESS = "access"  # user token, issued after OTP verification
TOKEN_TYPE_CLIENT = "client"  # app token, issued by POST /auth/token


@dataclass(frozen=True)
class TokenPayload:
    user_uuid: str
    jti: str
    expires_at: datetime


def create_access_token(user_uuid: str) -> tuple[str, datetime, str]:
    """Return ``(token, expires_at, jti)``."""
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_uuid,
        "jti": jti,
        "type": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at, jti


def create_client_token(client_id: str) -> tuple[str, datetime]:
    """Return ``(token, expires_at)`` for an authenticated app client."""
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.CLIENT_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": client_id,
        "jti": uuid.uuid4().hex,
        "type": TOKEN_TYPE_CLIENT,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), expires_at


def verify_client_credentials(client_id: str, client_secret: str) -> bool:
    id_ok = hmac.compare_digest(client_id.encode(), settings.API_CLIENT_ID.encode())
    secret_ok = hmac.compare_digest(client_secret.encode(), settings.API_CLIENT_SECRET.encode())
    return id_ok and secret_ok


def decode_access_token(token: str, expected_type: str = TOKEN_TYPE_ACCESS) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "jti", "exp", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(401, "Access token has expired", ErrorCode.TOKEN_EXPIRED)
    except jwt.PyJWTError:
        raise AppError(401, "Invalid access token", ErrorCode.INVALID_TOKEN)

    if payload.get("type") != expected_type:
        raise AppError(401, "Invalid access token", ErrorCode.INVALID_TOKEN)

    return TokenPayload(
        user_uuid=payload["sub"],
        jti=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


def hash_otp(otp: str, salt: str) -> str:
    """Keyed hash so a DB leak does not reveal OTPs. ``salt`` is the OTP session uuid."""
    msg = f"{salt}:{otp}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify_otp_hash(otp: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp, salt), expected_hash)
