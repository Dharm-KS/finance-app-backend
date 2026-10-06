"""OTP delivery providers.

The API and ``otp_service`` only depend on :class:`OtpProvider`. To go live, implement e.g.
``Msg91OtpProvider`` / ``TwilioOtpProvider`` and return it from :func:`get_otp_provider`.
No API contract changes are needed.
"""

import logging
from abc import ABC, abstractmethod

from app.core.config import settings
from app.models.enums import OtpPurpose

logger = logging.getLogger(__name__)

FIXED_MVP_OTP = "123456"


def mask_mobile(mobile: str) -> str:
    return f"{mobile[:3]}******{mobile[-4:]}" if len(mobile) >= 7 else "****"


class OtpProvider(ABC):
    name: str

    @abstractmethod
    def generate_otp(self) -> str:
        """Return the OTP to send. It is hashed before storage and never logged."""

    @abstractmethod
    async def send(self, mobile: str, otp: str, purpose: OtpPurpose) -> None:
        """Deliver the OTP (SMS/WhatsApp/...)."""


class FixedOtpProvider(OtpProvider):
    """MVP provider: always 123456, nothing is sent."""

    name = "FIXED"

    def generate_otp(self) -> str:
        return FIXED_MVP_OTP

    async def send(self, mobile: str, otp: str, purpose: OtpPurpose) -> None:
        # Never log the OTP itself.
        logger.info("OTP issued (fixed provider) purpose=%s mobile=%s", purpose.value, mask_mobile(mobile))


def get_otp_provider() -> OtpProvider:
    providers: dict[str, type[OtpProvider]] = {"fixed": FixedOtpProvider}
    try:
        return providers[settings.OTP_PROVIDER.lower()]()
    except KeyError:
        raise RuntimeError(f"Unknown OTP_PROVIDER '{settings.OTP_PROVIDER}'")
