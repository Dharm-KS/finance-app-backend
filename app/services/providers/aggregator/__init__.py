"""Account-aggregator providers (bank / investment / loan data, fetched after an OTP).

The service layer depends only on :class:`AggregatorProvider`. The MVP uses
:class:`MockAggregatorProvider`, which accepts OTP ``123456`` and returns the two sample
reports in ``fixtures/``. A real provider implements the same three methods.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.providers.otp import mask_mobile

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_OTP = "123456"


class AggregatorError(Exception):
    """Provider unreachable or returned an error."""


class AggregatorProvider(ABC):
    name: str

    @abstractmethod
    def generate_otp(self) -> str:
        """OTP the provider sends to the customer (hashed before storage, never logged)."""

    @abstractmethod
    async def send_otp(self, mobile: str, otp: str) -> None:
        ...

    @abstractmethod
    async def fetch_reports(self, mobile: str) -> list[dict[str, Any]]:
        """Return the provider's raw responses (one per institution) after OTP verification."""


class MockAggregatorProvider(AggregatorProvider):
    name = "MOCK"
    report_files = ("report_bank_checking.json", "report_bank_savings.json")

    def generate_otp(self) -> str:
        return MOCK_OTP

    async def send_otp(self, mobile: str, otp: str) -> None:
        logger.info("Aggregator OTP issued (mock) mobile=%s", mask_mobile(mobile))

    async def fetch_reports(self, mobile: str) -> list[dict[str, Any]]:
        reports = []
        for name in self.report_files:
            with open(FIXTURES / name, encoding="utf-8") as fh:
                reports.append(json.load(fh))
        return reports


def get_aggregator_provider() -> AggregatorProvider:
    providers: dict[str, type[AggregatorProvider]] = {"mock": MockAggregatorProvider}
    try:
        return providers[settings.AGGREGATOR_PROVIDER.lower()]()
    except KeyError:
        raise RuntimeError(f"Unknown AGGREGATOR_PROVIDER '{settings.AGGREGATOR_PROVIDER}'")
