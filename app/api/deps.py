"""Shared FastAPI dependencies: DB session, authenticated user, client info."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError, ErrorCode
from app.core.security import TOKEN_TYPE_CLIENT, TokenPayload, decode_access_token
from app.models.user import User
from app.services import auth_service
from app.services.otp_service import ClientInfo

DbSession = Annotated[AsyncSession, Depends(get_db)]

# auto_error=False so a missing token produces our own 401 envelope instead of FastAPI's 403.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Client token from POST /auth/token (OTP endpoints) or user token from /auth/*/verify-otp (everything else)",
)


def _bearer(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError(401, "Authentication required", ErrorCode.NOT_AUTHENTICATED)
    return credentials.credentials


async def require_client_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TokenPayload:
    """Pre-login endpoints: a valid app token from POST /auth/token (user tokens are rejected)."""
    return decode_access_token(_bearer(credentials), expected_type=TOKEN_TYPE_CLIENT)


async def get_auth_context(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> tuple[User, TokenPayload]:
    return await auth_service.authenticate_token(db, _bearer(credentials))


AuthContext = Annotated[tuple[User, TokenPayload], Depends(get_auth_context)]


async def get_current_user(ctx: AuthContext) -> User:
    return ctx[0]


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_client_info(request: Request) -> ClientInfo:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return ClientInfo(ip_address=ip, user_agent=request.headers.get("user-agent"))


Client = Annotated[ClientInfo, Depends(get_client_info)]
