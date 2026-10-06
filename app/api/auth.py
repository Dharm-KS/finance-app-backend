from fastapi import APIRouter, Depends, status

from app.api.deps import AuthContext, Client, CurrentUser, DbSession, require_client_token
from app.schemas.auth import (
    AuthTokenOut,
    ClientTokenIn,
    ClientTokenOut,
    LoginVerifyIn,
    OtpRequestIn,
    OtpRequestOut,
    RegisterVerifyIn,
    UserOut,
    UserUpdateIn,
)
from app.schemas.common import AUTH_ERRORS, CONFLICT, NOT_FOUND, VALIDATION, ApiResponse, ErrorResponse, ok
from app.services import auth_service
from app.services.auth_service import AuthResult

router = APIRouter(prefix="/auth", tags=["Auth"])

# Pre-login endpoints need the app's client token (POST /auth/token).
CLIENT_AUTH = [Depends(require_client_token)]

OTP_ERRORS = {
    400: {"model": ErrorResponse, "description": "Invalid / expired / not-requested OTP"},
    429: {"model": ErrorResponse, "description": "Too many attempts or OTP requested too soon"},
}


@router.post(
    "/token",
    response_model=ApiResponse[ClientTokenOut],
    summary="Create auth token",
    description="Exchange the app's client credentials for a short-lived client token. Send it as "
    "`Authorization: Bearer <token>` on the registration and login OTP endpoints. "
    "This is the only endpoint that needs no token.",
    responses={401: {"model": ErrorResponse, "description": "Invalid client credentials"}, **VALIDATION},
)
async def create_token(payload: ClientTokenIn):
    return ok(auth_service.issue_client_token(payload.client_id, payload.client_secret), "Token created successfully")


def _token_response(result: AuthResult) -> dict:
    return {
        "access_token": result.access_token,
        "token_type": "bearer",
        "expires_at": result.expires_at,
        "user": UserOut.model_validate(result.user),
        "is_new_user": result.is_new_user,
        "next_step": result.onboarding.current_step,
        "onboarding_completed": result.onboarding.onboarding_completed,
    }


@router.post(
    "/register/request-otp",
    dependencies=CLIENT_AUTH,
    response_model=ApiResponse[OtpRequestOut],
    summary="Registration: request OTP",
    description="Starts sign-up for a new mobile number and sends an OTP. **The OTP is never returned.** "
    "(MVP: the OTP is always `123456`.) Fails with 409 if the number is already registered.",
    responses={**AUTH_ERRORS, **CONFLICT, **VALIDATION, 429: OTP_ERRORS[429]},
)
async def register_request_otp(payload: OtpRequestIn, db: DbSession, client: Client):
    data = await auth_service.register_request_otp(db, payload.mobile, client)
    return ok(data, "OTP sent successfully")


@router.post(
    "/register/verify-otp",
    dependencies=CLIENT_AUTH,
    response_model=ApiResponse[AuthTokenOut],
    status_code=status.HTTP_201_CREATED,
    summary="Registration: verify OTP and create user",
    description="Verifies the OTP, creates the user and returns a JWT plus the next onboarding step. "
    "`name` may be sent here, or later via `PATCH /auth/me` (next_step will be `REGISTRATION` until it is set).",
    responses={**AUTH_ERRORS, **OTP_ERRORS, **CONFLICT, **VALIDATION},
)
async def register_verify_otp(payload: RegisterVerifyIn, db: DbSession):
    result = await auth_service.register_verify_otp(db, payload.mobile, payload.otp, payload.name)
    return ok(_token_response(result), "Registration successful")


@router.post(
    "/login/request-otp",
    dependencies=CLIENT_AUTH,
    response_model=ApiResponse[OtpRequestOut],
    summary="Login: request OTP",
    description="Sends a login OTP to a registered mobile number. 404 if the number is not registered.",
    responses={**AUTH_ERRORS, **NOT_FOUND, **VALIDATION, 429: OTP_ERRORS[429]},
)
async def login_request_otp(payload: OtpRequestIn, db: DbSession, client: Client):
    data = await auth_service.login_request_otp(db, payload.mobile, client)
    return ok(data, "OTP sent successfully")


@router.post(
    "/login/verify-otp",
    dependencies=CLIENT_AUTH,
    response_model=ApiResponse[AuthTokenOut],
    summary="Login: verify OTP",
    description="Verifies the OTP and returns a JWT with the onboarding status so the app can resume.",
    responses={**AUTH_ERRORS, **OTP_ERRORS, **NOT_FOUND, **VALIDATION},
)
async def login_verify_otp(payload: LoginVerifyIn, db: DbSession):
    result = await auth_service.login_verify_otp(db, payload.mobile, payload.otp)
    return ok(_token_response(result), "Login successful")


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    summary="Logout",
    description="Revokes the current access token. Requires Bearer token.",
    responses=AUTH_ERRORS,
)
async def logout(ctx: AuthContext, db: DbSession):
    user, token = ctx
    await auth_service.logout(db, user, token)
    return ok(None, "Logged out successfully")


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="Current user",
    description="Returns the authenticated user's profile. Requires Bearer token.",
    responses=AUTH_ERRORS,
)
async def me(user: CurrentUser):
    return ok(UserOut.model_validate(user), "User fetched successfully")


@router.patch(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="Update current user",
    description="Set name (completes the REGISTRATION onboarding step) and/or email. Requires Bearer token.",
    responses={**AUTH_ERRORS, **CONFLICT, **VALIDATION},
)
async def update_me(payload: UserUpdateIn, user: CurrentUser, db: DbSession):
    await auth_service.update_me(
        db, user, name=payload.name, email=payload.email, fields_set=payload.model_fields_set
    )
    return ok(UserOut.model_validate(user), "Profile updated successfully")
