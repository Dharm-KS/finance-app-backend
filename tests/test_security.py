"""Unauthorised access and cross-user isolation."""

import pytest

from tests.conftest import API, EQUITY, FINANCIAL_PROFILE, give_credit_consent, register_headers

PROTECTED = [
    ("POST", "/auth/register/request-otp"),
    ("POST", "/auth/register/verify-otp"),
    ("POST", "/auth/login/request-otp"),
    ("POST", "/auth/login/verify-otp"),
    ("PATCH", "/auth/me"),
    ("POST", "/onboarding/skip"),
    ("GET", "/goals/suggestions"),
    ("GET", "/auth/me"),
    ("POST", "/auth/logout"),
    ("GET", "/onboarding/status"),
    ("GET", "/consents"),
    ("POST", "/consents"),
    ("POST", "/credit/fetch"),
    ("GET", "/credit/report"),
    ("GET", "/credit/accounts"),
    ("GET", "/financial-profile"),
    ("PUT", "/financial-profile"),
    ("GET", "/equity"),
    ("POST", "/equity"),
    ("PUT", "/equity/1"),
    ("DELETE", "/equity/1"),
    ("GET", "/risk-profile"),
    ("PUT", "/risk-profile"),
    ("GET", "/goals"),
    ("POST", "/goals"),
    ("PUT", "/goals/1"),
    ("DELETE", "/goals/1"),
    ("GET", "/dashboard"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_endpoints_require_auth(raw_client, method, path):
    r = await raw_client.request(method, f"{API}{path}", json={})
    assert r.status_code == 401, (method, path, r.text)
    assert r.json()["success"] is False


async def test_expired_token_rejected(raw_client):
    from datetime import timedelta

    import jwt

    from app.core.config import settings
    from app.core.time import utcnow

    token = jwt.encode(
        {"sub": "x", "jti": "y", "type": "access", "exp": int((utcnow() - timedelta(minutes=1)).timestamp())},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    r = await raw_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["error_code"] == "TOKEN_EXPIRED"


async def test_cross_user_access_is_prevented(client):
    alice = await register_headers(client, "9876543210", "Alice")
    bob = await register_headers(client, "9876543215", "Bob")

    # Alice creates data
    await give_credit_consent(client, alice)
    await client.post(f"{API}/credit/fetch", headers=alice)
    await client.put(f"{API}/financial-profile", json=FINANCIAL_PROFILE, headers=alice)
    equity_id = (await client.post(f"{API}/equity", json=EQUITY, headers=alice)).json()["data"]["id"]
    goal_id = (
        await client.post(f"{API}/goals", json={"goal_type": "EMERGENCY_FUND"}, headers=alice)
    ).json()["data"]["id"]

    # Bob cannot read, modify or delete Alice's resources
    r = await client.put(f"{API}/equity/{equity_id}", json={"vested_value": 1}, headers=bob)
    assert r.status_code == 404
    r = await client.delete(f"{API}/equity/{equity_id}", headers=bob)
    assert r.status_code == 404
    r = await client.put(f"{API}/goals/{goal_id}", json={"current_amount": 1}, headers=bob)
    assert r.status_code == 404
    r = await client.delete(f"{API}/goals/{goal_id}", headers=bob)
    assert r.status_code == 404

    # Bob's own views contain none of Alice's data
    assert (await client.get(f"{API}/equity", headers=bob)).json()["data"]["holdings"] == []
    assert (await client.get(f"{API}/goals", headers=bob)).json()["data"]["goals"] == []
    assert (await client.get(f"{API}/credit/report", headers=bob)).status_code == 404
    assert (await client.get(f"{API}/financial-profile", headers=bob)).json()["data"]["is_saved"] is False
    assert (await client.get(f"{API}/dashboard", headers=bob)).json()["data"]["net_worth"] == 0

    # Alice's data is untouched
    assert (await client.get(f"{API}/equity", headers=alice)).json()["data"]["holdings"][0]["vested_value"] == 2500000
    assert len((await client.get(f"{API}/goals", headers=alice)).json()["data"]["goals"]) == 1
