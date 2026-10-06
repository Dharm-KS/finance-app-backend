"""Equity data provider contract (future: broker / employer stock-plan / market-price APIs).

MVP: all holdings are entered manually through ``/api/v1/equity`` and stored with
``source=MANUAL``, so :class:`ManualEquityProvider` has nothing to import. When an API-backed
provider is added it returns :class:`EquityHoldingData` rows which ``equity_service`` upserts
with that provider's ``source`` value - API routes stay unchanged.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models.enums import Currency, EquitySource


@dataclass
class EquityHoldingData:
    employer_name: str
    security_name: str
    ticker: str | None
    vested_value: Decimal
    unvested_value: Decimal
    currency: Currency
    as_of_date: date


class EquityProvider(ABC):
    source: EquitySource

    @abstractmethod
    async def fetch_holdings(self, user_uuid: str) -> list[EquityHoldingData]:
        ...


class ManualEquityProvider(EquityProvider):
    source = EquitySource.MANUAL

    async def fetch_holdings(self, user_uuid: str) -> list[EquityHoldingData]:
        return []  # manual holdings already live in the database
