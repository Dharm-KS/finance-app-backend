"""Application configuration loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Finance Friend API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str

    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # App (client) credentials for POST /auth/token. The client token protects the
    # pre-login endpoints (OTP request/verify).
    API_CLIENT_ID: str = Field(min_length=3)
    API_CLIENT_SECRET: str = Field(min_length=16)
    CLIENT_TOKEN_EXPIRE_MINUTES: int = 60

    OTP_PROVIDER: str = "fixed"
    OTP_EXPIRY_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 30
    # Per mobile number (all purposes): at most N OTPs in a rolling window.
    OTP_MAX_SENDS_PER_WINDOW: int = 5
    OTP_SEND_WINDOW_SECONDS: int = 3600

    CREDIT_PROVIDER: str = "dummy"
    AGGREGATOR_PROVIDER: str = "mock"  # third-party bank/investment data (mock = sample reports)

    # Everything is shown to the customer in this currency; other currencies are converted with
    # these rates (rupees per 1 unit). Approximate defaults - update them, or plug in live rates.
    REPORTING_CURRENCY: str = "INR"
    FX_RATES_INR: str = "EUR:100,USD:88,GBP:115,AED:24,SGD:66"

    # AI advisor. "offline" = rule-based insights (no API key, free, deterministic);
    # "claude" = Claude via the Anthropic API.
    LLM_PROVIDER: str = "offline"
    ANTHROPIC_API_KEY: str | None = None
    LLM_MODEL: str = "claude-opus-5-5"
    LLM_AGENT_EFFORT: str = "low"
    LLM_CHIEF_EFFORT: str = "medium"
    LLM_CHAT_EFFORT: str = "low"
    LLM_MAX_PARALLEL: int = 4
    # Run analyses inside the request instead of a background task (tests, debugging).
    ADVISOR_INLINE: bool = False

    CORS_ORIGINS: str = "*"

    @field_validator("JWT_SECRET")
    @classmethod
    def _secret_not_placeholder(cls, v: str) -> str:
        if v.lower() in {"change-me", "secret", "changeme"}:
            raise ValueError("JWT_SECRET must be a strong random value")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def dev_endpoints_enabled(self) -> bool:
        """Endpoints that accept test data (e.g. pushing a raw aggregator report)."""
        return not self.is_production

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
