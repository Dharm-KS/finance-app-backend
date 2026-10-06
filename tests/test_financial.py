from tests.conftest import API, EQUITY, FINANCIAL_PROFILE, RISK_PROFILE, give_credit_consent, register_headers


# ---- financial profile -----------------------------------------------------------------------

async def test_financial_profile_prefilled_from_credit(client):
    h = await register_headers(client, "9876543210")
    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)

    r = await client.get(f"{API}/financial-profile", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["is_saved"] is False
    assert data["prefill_source"] == "CREDIT_REPORT"
    assert set(data["prefilled_fields"]) == {"monthly_emi", "total_debt"}
    # 240000 personal loan + 410000 auto loan + 32000 card
    assert data["profile"]["total_debt"] == 682000
    assert data["profile"]["monthly_emi"] == 27950


async def test_financial_profile_put_and_get(client):
    h = await register_headers(client)
    r = await client.put(f"{API}/financial-profile", json=FINANCIAL_PROFILE, headers=h)
    assert r.status_code == 200, r.text
    r = await client.get(f"{API}/financial-profile", headers=h)
    data = r.json()["data"]
    assert data["is_saved"] is True
    assert data["profile"]["monthly_spend"] == 65000

    # user can edit (override) prefilled values
    r = await client.put(f"{API}/financial-profile", json={**FINANCIAL_PROFILE, "total_debt": 100000.50}, headers=h)
    assert r.json()["data"]["profile"]["total_debt"] == 100000.5


async def test_financial_profile_validation(client):
    h = await register_headers(client)
    for bad in ({"monthly_spend": -1}, {"age": 12}, {"annual_income": 10.123}, {"currency": "XYZ"}):
        r = await client.put(f"{API}/financial-profile", json={**FINANCIAL_PROFILE, **bad}, headers=h)
        assert r.status_code == 422, bad
        assert r.json()["success"] is False


# ---- equity ----------------------------------------------------------------------------------

async def test_equity_crud(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/equity", json=EQUITY, headers=h)
    assert r.status_code == 201, r.text
    holding = r.json()["data"]
    assert holding["source"] == "MANUAL"
    assert holding["ticker"] == "ACME"
    hid = holding["id"]

    await client.post(f"{API}/equity", json={**EQUITY, "security_name": "Other Co", "ticker": "OTH"}, headers=h)
    r = await client.get(f"{API}/equity", headers=h)
    data = r.json()["data"]
    assert len(data["holdings"]) == 2
    assert data["total_vested_value"] == 5000000

    r = await client.put(f"{API}/equity/{hid}", json={"vested_value": 2700000}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["vested_value"] == 2700000
    assert r.json()["data"]["employer_name"] == "Acme Technologies"

    r = await client.delete(f"{API}/equity/{hid}", headers=h)
    assert r.status_code == 200
    r = await client.put(f"{API}/equity/{hid}", json={"vested_value": 1}, headers=h)
    assert r.status_code == 404
    assert r.json()["error_code"] == "EQUITY_HOLDING_NOT_FOUND"


async def test_equity_validation(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/equity", json={**EQUITY, "vested_value": -5}, headers=h)
    assert r.status_code == 422
    r = await client.post(f"{API}/equity", json={**EQUITY, "as_of_date": "2999-01-01"}, headers=h)
    assert r.status_code == 422


# ---- risk ------------------------------------------------------------------------------------

async def test_risk_profile_get_put(client):
    h = await register_headers(client)
    r = await client.get(f"{API}/risk-profile", headers=h)
    assert r.status_code == 404
    assert r.json()["error_code"] == "RISK_PROFILE_NOT_FOUND"

    r = await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)
    assert r.status_code == 200
    r = await client.get(f"{API}/risk-profile", headers=h)
    assert r.json()["data"]["risk_tolerance"] == "BALANCED"
    assert r.json()["data"]["single_stock_limit_percent"] == 35

    r = await client.put(f"{API}/risk-profile", json={**RISK_PROFILE, "risk_tolerance": "GROWTH"}, headers=h)
    assert r.json()["data"]["risk_tolerance"] == "GROWTH"


async def test_risk_profile_validation(client):
    h = await register_headers(client)
    for bad in (
        {"max_drawdown_percent": 101},
        {"single_stock_limit_percent": -1},
        {"planning_horizon_years": 0},
        {"planning_horizon_years": 51},
        {"risk_tolerance": "YOLO"},
    ):
        r = await client.put(f"{API}/risk-profile", json={**RISK_PROFILE, **bad}, headers=h)
        assert r.status_code == 422, bad
