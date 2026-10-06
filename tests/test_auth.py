from tests.conftest import API, CLIENT_CREDENTIALS, OTP, auth, register


async def test_register_request_otp_does_not_expose_otp(client):
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "+91 98765 43210"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["mobile"] == "+919876543210"
    assert OTP not in r.text


async def test_register_request_otp_invalid_mobile(client):
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "12345"})
    assert r.status_code == 422
    assert r.json()["success"] is False
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_register_verify_creates_user_and_returns_token(client):
    data = await register(client, "9876543210", "Aarav Sharma")
    assert data["access_token"]
    assert data["is_new_user"] is True
    assert data["user"]["name"] == "Aarav Sharma"
    assert data["user"]["is_verified"] is True
    assert data["next_step"] == "FINANCIAL_PROFILE"  # first calibration screen after OTP
    assert OTP not in str(data)


async def test_register_without_name_then_patch_me(client):
    data = await register(client, "9876543211", name=None)
    assert data["next_step"] == "FINANCIAL_PROFILE"  # name is optional, it doesn't block onboarding
    headers = auth(data["access_token"])
    r = await client.patch(f"{API}/auth/me", json={"name": "Priya Nair"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Priya Nair"
    r = await client.get(f"{API}/onboarding/status", headers=headers)
    assert r.json()["data"]["registration_completed"] is True


async def test_register_existing_mobile_conflict(client):
    await register(client, "9876543210")
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    assert r.status_code == 409
    assert r.json()["error_code"] == "MOBILE_ALREADY_REGISTERED"


async def test_login_flow(client):
    await register(client, "9876543210")
    r = await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    assert r.status_code == 200
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["is_new_user"] is False
    assert data["next_step"] == "FINANCIAL_PROFILE"
    assert data["user"]["last_login_at"] is not None


async def test_login_unregistered_mobile(client):
    r = await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9000000001"})
    assert r.status_code == 404
    assert r.json()["error_code"] == "MOBILE_NOT_REGISTERED"


async def test_invalid_otp(client):
    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": "000000", "name": "A B"})
    assert r.status_code == 400
    assert r.json()["error_code"] == "OTP_INVALID"


async def test_too_many_otp_attempts_locks_session(client):
    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    codes = []
    for _ in range(5):
        r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": "000000"})
        codes.append(r.json()["error_code"])
    assert codes[-1] == "OTP_TOO_MANY_ATTEMPTS"
    # even the right OTP is rejected now
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 429


async def test_verify_without_request(client):
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 404  # not registered
    await register(client, "9876543210")
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 400
    assert r.json()["error_code"] == "OTP_NOT_REQUESTED"


async def test_expired_otp(client, session_factory):
    from datetime import timedelta

    from sqlalchemy import update

    from app.core.time import utcnow
    from app.models import OtpSession

    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    async with session_factory() as s:
        await s.execute(update(OtpSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 400
    assert r.json()["error_code"] == "OTP_EXPIRED"


async def test_otp_is_used_once(client):
    await register(client, "9876543210")
    await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    r1 = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    r2 = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r1.status_code == 200
    assert r2.status_code == 400


async def test_me_authenticated(client):
    data = await register(client, "9876543210", "Aarav Sharma")
    r = await client.get(f"{API}/auth/me", headers=auth(data["access_token"]))
    assert r.status_code == 200
    assert r.json()["data"]["mobile"] == "+919876543210"
    assert "id" not in r.json()["data"]  # internal id never exposed


async def test_me_requires_token(raw_client):
    r = await raw_client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json() == {"success": False, "message": "Authentication required", "error_code": "NOT_AUTHENTICATED"}


async def test_me_invalid_token(client):
    r = await client.get(f"{API}/auth/me", headers=auth("not-a-jwt"))
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_TOKEN"


async def test_logout_revokes_token(client):
    data = await register(client, "9876543210")
    headers = auth(data["access_token"])
    r = await client.post(f"{API}/auth/logout", headers=headers)
    assert r.status_code == 200
    r = await client.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["error_code"] == "TOKEN_REVOKED"


# ---- client token (POST /auth/token) ---------------------------------------------------------

async def test_create_client_token(raw_client):
    r = await raw_client.post(f"{API}/auth/token", json=CLIENT_CREDENTIALS)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


async def test_create_client_token_wrong_secret(raw_client):
    r = await raw_client.post(f"{API}/auth/token", json={**CLIENT_CREDENTIALS, "client_secret": "wrong"})
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CLIENT"


async def test_otp_endpoints_require_client_token(raw_client):
    for path in ("register/request-otp", "register/verify-otp", "login/request-otp", "login/verify-otp"):
        r = await raw_client.post(f"{API}/auth/{path}", json={"mobile": "9876543210", "otp": OTP})
        assert r.status_code == 401, path
        assert r.json()["error_code"] == "NOT_AUTHENTICATED"


async def test_user_token_rejected_on_otp_endpoints(client):
    data = await register(client, "9876543210")
    r = await client.post(
        f"{API}/auth/login/request-otp", json={"mobile": "9876543210"}, headers=auth(data["access_token"])
    )
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_TOKEN"


async def test_client_token_rejected_on_user_endpoints(client):
    r = await client.get(f"{API}/auth/me")  # only the default client token is sent
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_TOKEN"


async def test_user_token_lasts_7_days(client):
    from datetime import datetime, timedelta, timezone

    data = await register(client, "9876543210")
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    remaining = expires_at - datetime.now(timezone.utc)
    assert timedelta(days=7) - timedelta(minutes=1) < remaining <= timedelta(days=7)


# ---- resend / limits -------------------------------------------------------------------------

async def test_resend_replaces_previous_otp(client, session_factory):
    from sqlalchemy import select

    from app.models import OtpSession

    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})  # resend
    assert r.status_code == 200
    async with session_factory() as s:
        statuses = [x.status.value for x in (await s.execute(select(OtpSession).order_by(OtpSession.id))).scalars()]
    assert statuses == ["SUPERSEDED", "PENDING"]
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": OTP, "name": "A B"})
    assert r.status_code == 201


async def test_resend_too_soon_returns_wait_time(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 30)
    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    assert r.status_code == 429
    body = r.json()
    assert body["error_code"] == "OTP_RESEND_TOO_SOON"
    assert 0 < body["retry_after_seconds"] <= 31
    assert r.headers["Retry-After"] == str(body["retry_after_seconds"])


async def test_resend_allowed_after_expiry_or_lock(client, session_factory):
    from datetime import timedelta

    from sqlalchemy import update

    from app.core.time import utcnow
    from app.models import OtpSession

    # expired -> resend -> verify works
    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    async with session_factory() as s:
        await s.execute(update(OtpSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.json()["error_code"] == "OTP_EXPIRED"
    await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/register/verify-otp", json={"mobile": "9876543210", "otp": OTP, "name": "A B"})
    assert r.status_code == 201

    # locked -> resend -> verify works (attempt counter starts again)
    await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    for _ in range(5):
        r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": "000000"})
    assert r.json()["error_code"] == "OTP_TOO_MANY_ATTEMPTS"
    await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": OTP})
    assert r.status_code == 200


async def test_otp_send_limit_per_mobile(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_WINDOW", 3)
    for _ in range(3):
        r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
        assert r.status_code == 200
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543210"})
    assert r.status_code == 429
    body = r.json()
    assert body["error_code"] == "OTP_LIMIT_REACHED"
    assert 3500 < body["retry_after_seconds"] <= 3601
    # another number is unaffected
    r = await client.post(f"{API}/auth/register/request-otp", json={"mobile": "9876543211"})
    assert r.status_code == 200
