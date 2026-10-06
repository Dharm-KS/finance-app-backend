"""Shared schema building blocks: response envelope and validated numeric types."""

from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")


def _decimal_to_number(v: Decimal) -> float | int:
    # Decimal is used for all maths; it is emitted as a JSON number for mobile-client convenience.
    # DECIMAL(18,2) values fit comfortably inside float precision.
    return int(v) if v == v.to_integral_value() else float(v)


_as_number = PlainSerializer(_decimal_to_number, return_type=float, when_used="json")

# Non-negative money amount with at most 2 decimal places.
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2), _as_number]
# Output-only money (may be negative, e.g. net worth); no input constraints.
MoneyOut = Annotated[Decimal, _as_number]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2), _as_number]
PercentOut = Annotated[Decimal, _as_number]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "OK"


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str
    errors: list[dict] | None = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"success": False, "message": "Credit consent is required", "error_code": "CONSENT_REQUIRED"}}
    )


def ok(data=None, message: str = "OK") -> dict:
    """Build a success envelope. Routes declare ``response_model=ApiResponse[X]`` for docs/validation."""
    return {"success": True, "data": data, "message": message}


# Reusable OpenAPI error docs for routes
AUTH_ERRORS = {401: {"model": ErrorResponse, "description": "Missing, invalid, expired or revoked token"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found (or not owned by caller)"}}
VALIDATION = {422: {"model": ErrorResponse, "description": "Request validation failed"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Conflict with current state"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Action not permitted (e.g. consent missing)"}}
