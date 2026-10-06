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
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
