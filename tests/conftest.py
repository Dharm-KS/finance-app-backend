"""Test fixtures: each test gets a fresh in-memory SQLite DB and an HTTP client bound to the app.

SQLite keeps tests self-contained (no MySQL needed); the models only use portable types.
"""

import os

# Must be set before the app (and its settings) is imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = "test-secret-key-that-is-long-enough-for-hs256-0123456789"
os.environ["ENVIRONMENT"] = "test"
os.environ["OTP_RESEND_COOLDOWN_SECONDS"] = "0"
os.environ["API_CLIENT_ID"] = "test-mobile-app"
os.environ["API_CLIENT_SECRET"] = "test-client-secret-0123456789"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

OTP = "123456"
API = "/api/v1"
CLIENT_CREDENTIALS = {"client_id": "test-mobile-app", "client_secret": "test-client-secret-0123456789"}


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest.fixture
async def raw_client(session_factory):
    """HTTP client with no token at all."""

    async def _get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def client(raw_client):
    """Like the mobile app: holds a client token from POST /auth/token by default.

    Requests that pass their own Authorization header (a user token) override it.
    """
    r = await raw_client.post(f"{API}/auth/token", json=CLIENT_CREDENTIALS)
    assert r.status_code == 200, r.text
    raw_client.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    yield raw_client


async def register(client: AsyncClient, mobile: str = "9876543210", name: str | None = "Test User") -> dict:
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    body = {"mobile": mobile, "otp": OTP}
    if name:
        body["name"] = name
    r = await client.post(f"{API}/auth/register/verify-otp", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def register_headers(client: AsyncClient, mobile: str = "9876543210", name: str = "Test User") -> dict:
    return auth((await register(client, mobile, name))["access_token"])


async def give_credit_consent(client: AsyncClient, headers: dict) -> None:
    r = await client.post(
        f"{API}/consents", json={"consent_type": "CREDIT_REPORT", "consent_version": "v1"}, headers=headers
    )
    assert r.status_code == 201, r.text


FINANCIAL_PROFILE = {
    "annual_income": 2400000,
    "currency": "INR",
    "monthly_spend": 65000,
    "cash_reserve": 450000,
    "monthly_emi": 27950,
    "total_debt": 682000,
    "investments": 1200000,
    "employment_type": "SALARIED",
    "age": 32,
    "dependents": 1,
}

RISK_PROFILE = {
    "risk_tolerance": "BALANCED",
    "max_drawdown_percent": 18,
    "single_stock_limit_percent": 35,
    "planning_horizon_years": 10,
}

EQUITY = {
    "employer_name": "Acme Technologies",
    "security_name": "Acme Technologies Inc.",
    "ticker": "acme",
    "vested_value": 2500000,
    "unvested_value": 1200000,
    "currency": "INR",
}
