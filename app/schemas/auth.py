import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import OnboardingStep, UserStatus
from app.schemas.common import ORMModel

_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")


def normalize_mobile(value: str) -> str:
    """Accept ``9876543210``, ``+919876543210``, ``91 98765 43210`` -> ``+919876543210``.

    MVP supports Indian mobile numbers only.
    """
    digits = re.sub(r"[\s\-()]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not _MOBILE_RE.match(digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number")
    return f"+91{digits}"


class MobileIn(BaseModel):
    mobile: str = Field(description="Indian mobile number; normalised to E.164 (+91XXXXXXXXXX)")

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        return normalize_mobile(v)


class ClientTokenIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    client_secret: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(
        json_schema_extra={"example": {"client_id": "finance-mobile-app", "client_secret": "<from your .env>"}}
    )


class ClientTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
    expires_at: datetime


class OtpRequestIn(MobileIn):
    model_config = ConfigDict(json_schema_extra={"example": {"mobile": "9876543210"}})


class OtpRequestOut(BaseModel):
    """Note: the OTP itself is never returned."""

    otp_session_id: str
    mobile: str
    expires_in_seconds: int
    resend_after_seconds: int


class _OtpVerifyBase(MobileIn):
    otp: str = Field(min_length=4, max_length=8, description="One-time password")

    @field_validator("otp")
    @classmethod
    def _otp_digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("OTP must contain only digits")
        return v


class RegisterVerifyIn(_OtpVerifyBase):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Optional. If omitted, call PATCH /auth/me with the name (onboarding step REGISTRATION).",
    )

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_name(v) if v is not None else None

    model_config = ConfigDict(
        json_schema_extra={"example": {"mobile": "9876543210", "otp": "123456", "name": "Aarav Sharma"}}
    )


class LoginVerifyIn(_OtpVerifyBase):
    model_config = ConfigDict(json_schema_extra={"example": {"mobile": "9876543210", "otp": "123456"}})


def validate_name(v: str) -> str:
    v = " ".join(v.split())
    if len(v) < 2 or not _NAME_RE.match(v):
        raise ValueError("Name may contain letters, spaces, dots, apostrophes and hyphens only")
    return v


class UserOut(ORMModel):
    uuid: str
    mobile: str
    name: str | None
    email: str | None
    is_verified: bool
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_name(v) if v is not None else None

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Aarav Sharma"}})


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut
    is_new_user: bool
    next_step: OnboardingStep
    onboarding_completed: bool
