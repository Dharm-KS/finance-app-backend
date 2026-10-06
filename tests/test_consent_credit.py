from tests.conftest import API, give_credit_consent, register_headers


async def test_consent_create_and_list(client):
    h = await register_headers(client)
    r = await client.post(
        f"{API}/consents", json={"consent_type": "CREDIT_REPORT", "consent_version": "v1"}, headers=h
    )
    assert r.status_code == 201
    assert r.json()["data"]["status"] == "GRANTED"
    assert "credit" in r.json()["data"]["purpose"].lower()

    r = await client.get(f"{API}/consents", headers=h)
    data = r.json()["data"]
    current = {c["consent_type"]: c for c in data["current"]}
    assert current["CREDIT_REPORT"]["status"] == "GRANTED"
    assert current["DATA_PROCESSING"]["status"] is None
    assert len(data["history"]) == 1


async def test_consent_unsupported_version(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/consents", json={"consent_type": "CREDIT_REPORT", "consent_version": "v9"}, headers=h)
    assert r.status_code == 400
    assert r.json()["error_code"] == "CONSENT_VERSION_UNSUPPORTED"


async def test_credit_fetch_requires_consent(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/credit/fetch", headers=h)
    assert r.status_code == 403
    assert r.json() == {"success": False, "message": "Credit consent is required", "error_code": "CONSENT_REQUIRED"}


async def test_credit_fetch_after_revoked_consent(client):
    h = await register_headers(client)
    await give_credit_consent(client, h)
    await client.post(
        f"{API}/consents", json={"consent_type": "CREDIT_REPORT", "consent_version": "v1", "status": "REVOKED"}, headers=h
    )
    r = await client.post(f"{API}/credit/fetch", headers=h)
    assert r.status_code == 403
    r = await client.get(f"{API}/consents", headers=h)
    assert len(r.json()["data"]["history"]) == 2  # audit trail keeps both


async def test_credit_fetch_good_profile(client):
    h = await register_headers(client, "9876543210")  # last digit 0 -> 780
    await give_credit_consent(client, h)
    r = await client.post(f"{API}/credit/fetch", headers=h)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["credit_score"] == 780
    assert data["provider"] == "DUMMY"
    assert len(data["accounts"]) == 3
    assert data["summary"]["max_dpd"] == 0
    assert "raw_report" not in data


async def test_credit_profiles_are_deterministic(client):
    h = await register_headers(client, "9876543215")  # -> 692
    await give_credit_consent(client, h)
    assert (await client.post(f"{API}/credit/fetch", headers=h)).json()["data"]["credit_score"] == 692

    h = await register_headers(client, "9876543218")  # -> 615
    await give_credit_consent(client, h)
    data = (await client.post(f"{API}/credit/fetch", headers=h)).json()["data"]
    assert data["credit_score"] == 615
    assert len(data["accounts"]) == 4
    assert data["summary"]["max_dpd"] > 0
    assert data["summary"]["credit_card_utilization_percent"] > 80


async def test_credit_fetch_twice_conflict(client):
    h = await register_headers(client)
    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)
    r = await client.post(f"{API}/credit/fetch", headers=h)
    assert r.status_code == 409
    assert r.json()["error_code"] == "CREDIT_REPORT_ALREADY_EXISTS"


async def test_credit_no_hit(client):
    h = await register_headers(client, "9876540000")
    await give_credit_consent(client, h)
    r = await client.post(f"{API}/credit/fetch", headers=h)
    assert r.status_code == 404
    assert r.json()["error_code"] == "CREDIT_REPORT_UNAVAILABLE"


async def test_credit_report_and_accounts_retrieval(client):
    h = await register_headers(client)
    r = await client.get(f"{API}/credit/report", headers=h)
    assert r.status_code == 404
    assert r.json()["error_code"] == "CREDIT_REPORT_NOT_FOUND"

    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)
    r = await client.get(f"{API}/credit/report", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["credit_score"] == 780
    r = await client.get(f"{API}/credit/accounts", headers=h)
    assert r.status_code == 200
    types = sorted(a["account_type"] for a in r.json()["data"])
    assert types == ["AUTO_LOAN", "CREDIT_CARD", "PERSONAL_LOAN"]
