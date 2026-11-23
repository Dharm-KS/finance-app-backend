"""Currency conversion for display. Everything the customer sees is shown in REPORTING_CURRENCY (INR).

Stored provider data keeps its original currency; amounts are converted when the profile, agents
and API responses are built. MVP: static rates from ``FX_RATES_INR`` (rupees per unit of each
currency). A live-rate provider can implement :class:`FxProvider` later without other changes.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from functools import lru_cache

from app.core.config import settings


class FxProvider(ABC):
    source: str

    @abstractmethod
    def inr_per_unit(self, currency: str) -> Decimal:
        """Rupees for one unit of ``currency``."""


class StaticFxProvider(FxProvider):
    source = "static"

    def __init__(self, table: str) -> None:
        self.rates: dict[str, Decimal] = {"INR": Decimal("1")}
        for pair in filter(None, (p.strip() for p in table.split(","))):
            code, rate = pair.split(":")
            self.rates[code.strip().upper()] = Decimal(rate.strip())

    def inr_per_unit(self, currency: str) -> Decimal:
        try:
            return self.rates[(currency or "INR").upper()]
        except KeyError:
            raise ValueError(f"No exchange rate configured for {currency}; add it to FX_RATES_INR")


@lru_cache
def get_fx_provider() -> FxProvider:
    return StaticFxProvider(settings.FX_RATES_INR)


def reporting_currency() -> str:
    return settings.REPORTING_CURRENCY.upper()


def convert(amount, from_currency: str | None) -> float | None:
    """Convert ``amount`` from ``from_currency`` to the reporting currency (rounded to paise)."""
    if amount is None:
        return None
    fx = get_fx_provider()
    inr = Decimal(str(amount)) * fx.inr_per_unit(from_currency or reporting_currency())
    out = inr / fx.inr_per_unit(reporting_currency())
    return round(float(out), 2)


def rates_used(currencies: set[str]) -> dict[str, float]:
    """The rates applied, for showing "converted at ..." next to amounts."""
    fx = get_fx_provider()
    target = reporting_currency()
    return {c: round(float(fx.inr_per_unit(c) / fx.inr_per_unit(target)), 4) for c in sorted(currencies) if c != target}
