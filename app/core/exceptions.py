"""Application exceptions and the handlers that turn them into the standard error envelope.

Error envelope::

    {"success": false, "message": "...", "error_code": "...", "errors": [...]?}
"""

import logging
from enum import StrEnum

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    # auth
    MOBILE_ALREADY_REGISTERED = "MOBILE_ALREADY_REGISTERED"
    MOBILE_NOT_REGISTERED = "MOBILE_NOT_REGISTERED"
    OTP_NOT_REQUESTED = "OTP_NOT_REQUESTED"
    OTP_INVALID = "OTP_INVALID"
    OTP_EXPIRED = "OTP_EXPIRED"
    OTP_TOO_MANY_ATTEMPTS = "OTP_TOO_MANY_ATTEMPTS"
    OTP_RESEND_TOO_SOON = "OTP_RESEND_TOO_SOON"
    OTP_LIMIT_REACHED = "OTP_LIMIT_REACHED"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    INVALID_CLIENT = "INVALID_CLIENT"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_INACTIVE = "USER_INACTIVE"
    # consent / credit
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    CONSENT_VERSION_UNSUPPORTED = "CONSENT_VERSION_UNSUPPORTED"
    CREDIT_REPORT_NOT_FOUND = "CREDIT_REPORT_NOT_FOUND"
    CREDIT_REPORT_ALREADY_EXISTS = "CREDIT_REPORT_ALREADY_EXISTS"
    CREDIT_REPORT_UNAVAILABLE = "CREDIT_REPORT_UNAVAILABLE"
    # financial data
    FINANCIAL_PROFILE_NOT_FOUND = "FINANCIAL_PROFILE_NOT_FOUND"
    FINANCIAL_PROFILE_REQUIRED = "FINANCIAL_PROFILE_REQUIRED"
    RISK_PROFILE_NOT_FOUND = "RISK_PROFILE_NOT_FOUND"
    EQUITY_HOLDING_NOT_FOUND = "EQUITY_HOLDING_NOT_FOUND"
    GOAL_NOT_FOUND = "GOAL_NOT_FOUND"
    GOAL_TARGET_REQUIRED = "GOAL_TARGET_REQUIRED"
    # onboarding
    ONBOARDING_STEP_NOT_SKIPPABLE = "ONBOARDING_STEP_NOT_SKIPPABLE"
    # generic
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICT = "CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Raise from services; converted into the error envelope by the handler below."""

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: ErrorCode | str,
        *,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_code = str(error_code)
        self.retry_after_seconds = retry_after_seconds


class NotFoundError(AppError):
    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.NOT_FOUND):
        super().__init__(status.HTTP_404_NOT_FOUND, message, error_code)


class ConflictError(AppError):
    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.CONFLICT):
        super().__init__(status.HTTP_409_CONFLICT, message, error_code)


def _error(status_code: int, message: str, code: str, errors: list | None = None, headers=None, extra=None):
    body: dict = {"success": False, "message": message, "error_code": code}
    if errors:
        body["errors"] = errors
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else {}
        extra = None
        if exc.retry_after_seconds is not None:
            # Machine-readable wait so the app can run its resend countdown.
            headers["Retry-After"] = str(exc.retry_after_seconds)
            extra = {"retry_after_seconds": exc.retry_after_seconds}
        return _error(exc.status_code, exc.message, exc.error_code, headers=headers or None, extra=extra)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        # Keep FastAPI's detailed error list, but never echo submitted values back
        # (they may be OTPs or financial figures).
        errors = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p != "body"),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return _error(422, "Request validation failed", ErrorCode.VALIDATION_ERROR, errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.HTTP_ERROR
        return _error(exc.status_code, str(exc.detail), code, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return _error(500, "Something went wrong. Please try again.", ErrorCode.INTERNAL_ERROR)
