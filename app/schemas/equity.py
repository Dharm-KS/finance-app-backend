from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.time import utctoday
from app.models.enums import Currency, EquitySource
from app.schemas.common import Money, MoneyOut, ORMModel

_EXAMPLE = {
    "employer_name": "Helio Systems",
    "ticker": "HELO",
    "vested_value": 2500000,
    "unvested_value": 1200000,
    "next_vest_date": "2026-12-15",
}


class _EquityFields(BaseModel):
    @field_validator("ticker", check_fields=False)
    @classmethod
    def _ticker(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not v:
            return None
        if not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Ticker may contain letters, digits, '.' and '-' only")
        return v

    @field_validator("as_of_date", check_fields=False)
    @classmethod
    def _not_future(cls, v: date | None) -> date | None:
        if v is not None and v > utctoday():
            raise ValueError("as_of_date cannot be in the future")
        return v

    @field_validator("next_vest_date", check_fields=False)
    @classmethod
    def _not_past(cls, v: date | None) -> date | None:
        if v is not None and v < utctoday():
            raise ValueError("next_vest_date cannot be in the past")
        return v


class EquityCreate(_EquityFields):
    """"Your equity picture" screen."""

    employer_name: str = Field(min_length=1, max_length=120, description="Employer holding your equity")
    ticker: str | None = Field(default=None, max_length=20)
    vested_value: Money = Field(description="What you could sell today, before tax")
    unvested_value: Money = Field(default=0, description="Value still to vest under current grants")
    next_vest_date: date | None = None
    security_name: str | None = Field(
        default=None, min_length=1, max_length=120, description="Not on the screen; defaults to employer_name"
    )
    currency: Currency | None = Field(default=None, description="Defaults to the reporting currency from Money")
    as_of_date: date | None = Field(default=None, description="Defaults to today")

    model_config = ConfigDict(json_schema_extra={"example": _EXAMPLE})


class EquityUpdate(_EquityFields):
    """Partial update: only provided fields change."""

    employer_name: str | None = Field(default=None, min_length=1, max_length=120)
    ticker: str | None = Field(default=None, max_length=20)
    vested_value: Money | None = None
    unvested_value: Money | None = None
    next_vest_date: date | None = None
    security_name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: Currency | None = None
    as_of_date: date | None = None

    model_config = ConfigDict(json_schema_extra={"example": {"vested_value": 2700000}})


class EquityOut(ORMModel):
    id: int
    employer_name: str
    security_name: str
    ticker: str | None
    vested_value: MoneyOut
    unvested_value: MoneyOut
    next_vest_date: date | None
    currency: Currency
    as_of_date: date
    source: EquitySource
    created_at: datetime
    updated_at: datetime


class EquityListOut(BaseModel):
    holdings: list[EquityOut]
    total_vested_value: MoneyOut
    total_unvested_value: MoneyOut
