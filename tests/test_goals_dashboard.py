from tests.conftest import API, EQUITY, FINANCIAL_PROFILE, RISK_PROFILE, give_credit_consent, register_headers


async def _full_profile(client, h):
    await client.put(f"{API}/financial-profile", json=FINANCIAL_PROFILE, headers=h)
    await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)
    await client.post(f"{API}/equity", json=EQUITY, headers=h)


async def test_goals_crud(client):
    h = await register_headers(client)
    await client.put(f"{API}/financial-profile", json=FINANCIAL_PROFILE, headers=h)

    # auto-calculated: 6 x 65,000
    r = await client.post(f"{API}/goals", json={"goal_type": "EMERGENCY_FUND", "priority": "ESSENTIAL"}, headers=h)
    assert r.status_code == 201, r.text
    goal = r.json()["data"]
    assert goal["target_amount"] == 390000
    assert goal["current_amount"] == 390000  # defaults to cash reserve (capped at target)
    assert goal["name"] == "Emergency fund (6 months)"
    gid = goal["id"]

    r = await client.post(
        f"{API}/goals",
        json={"goal_type": "HOME_DOWN_PAYMENT", "target_amount": 2500000, "current_amount": 250000, "target_date": "2030-01-01"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["data"]["progress_percent"] == 10

    r = await client.get(f"{API}/goals", headers=h)
    assert len(r.json()["data"]["goals"]) == 2

    r = await client.put(f"{API}/goals/{gid}", json={"status": "COMPLETED"}, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "COMPLETED"

    r = await client.delete(f"{API}/goals/{gid}", headers=h)
    assert r.status_code == 200
    r = await client.delete(f"{API}/goals/{gid}", headers=h)
    assert r.status_code == 404
    assert r.json()["error_code"] == "GOAL_NOT_FOUND"


async def test_goal_target_required(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/goals", json={"goal_type": "HOME_DOWN_PAYMENT"}, headers=h)
    assert r.status_code == 422
    assert r.json()["error_code"] == "GOAL_TARGET_REQUIRED"
    r = await client.post(f"{API}/goals", json={"goal_type": "EMERGENCY_FUND"}, headers=h)  # no profile yet
    assert r.status_code == 422


async def test_concentration_goal_flags_above_target(client):
    h = await register_headers(client)
    # net worth = 1,000,000 cash + 0 inv + 2,500,000 equity - 0 debt = 3,500,000 ... make it 5,000,000:
    profile = {**FINANCIAL_PROFILE, "cash_reserve": 1500000, "investments": 1000000, "total_debt": 0}
    await client.put(f"{API}/financial-profile", json=profile, headers=h)
    await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)
    await client.post(f"{API}/equity", json=EQUITY, headers=h)  # 25L vested -> NW 50L -> 50%

    r = await client.post(f"{API}/goals", json={"goal_type": "REDUCE_SINGLE_STOCK_CONCENTRATION"}, headers=h)
    goal = r.json()["data"]
    details = goal["calculation"]["details"]
    assert details["current_concentration_percent"] == 50
    assert details["status"] == "ABOVE_TARGET"
    assert goal["target_amount"] == 750000  # 25L - 35% of 50L
    assert goal["is_at_risk"] is True


async def test_goal_suggestions(client):
    h = await register_headers(client)
    await _full_profile(client, h)
    r = await client.get(f"{API}/goals/suggestions", headers=h)
    by_type = {s["goal_type"]: s for s in r.json()["data"]}
    assert by_type["EMERGENCY_FUND"]["calculation"]["suggested_target_amount"] == 390000
    assert by_type["EQUITY_TAX_RESERVE"]["calculation"]["suggested_target_amount"] == 360000  # 30% of 12L
    assert by_type["HOME_DOWN_PAYMENT"]["calculation"]["suggested_target_amount"] is None


async def test_onboarding_status_progression(client):
    h = await register_headers(client)

    async def step():
        r = await client.get(f"{API}/onboarding/status", headers=h)
        assert r.status_code == 200
        return r.json()["data"]["current_step"]

    assert await step() == "FINANCIAL_PROFILE"
    await client.put(f"{API}/financial-profile", json=FINANCIAL_PROFILE, headers=h)
    assert await step() == "EQUITY"
    r = await client.post(f"{API}/onboarding/skip", json={"step": "EQUITY"}, headers=h)
    assert r.json()["data"]["equity_skipped"] is True
    assert await step() == "RISK"
    await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)
    assert await step() == "GOALS"
    await client.post(f"{API}/goals", json={"goal_type": "EMERGENCY_FUND"}, headers=h)
    assert await step() == "PREFERENCES"
    await client.put(f"{API}/preferences", json={"insight_tone": "BALANCED"}, headers=h)
    assert await step() == "COMPLETED"

    r = await client.get(f"{API}/onboarding/status", headers=h)
    assert r.json()["data"]["onboarding_completed"] is True

    # login reports where to resume
    r = await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": "123456"})
    assert r.json()["data"]["next_step"] == "COMPLETED"


async def test_onboarding_skip_only_optional_steps(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/onboarding/skip", json={"step": "CREDIT"}, headers=h)
    assert r.status_code == 422


async def test_dashboard(client):
    h = await register_headers(client, "9876543210")
    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)
    await _full_profile(client, h)
    await client.post(f"{API}/goals", json={"goal_type": "EMERGENCY_FUND"}, headers=h)
    await client.post(f"{API}/goals", json={"goal_type": "REDUCE_SINGLE_STOCK_CONCENTRATION"}, headers=h)

    r = await client.get(f"{API}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    # 450,000 + 1,200,000 + 2,500,000 - 682,000
    assert d["net_worth"] == 3468000
    assert d["cash"] == 450000
    assert d["investments"] == 1200000
    assert d["equity"] == 2500000
    assert d["unvested_equity"] == 1200000
    assert d["debt"] == 682000
    assert d["credit_score"] == 780
    assert d["risk"] == {"profile": "BALANCED", "max_drawdown": 18, "single_stock_limit": 35, "planning_horizon_years": 10}
    assert d["goals"]["total"] == 2
    assert d["goals"]["at_risk"] == 1
    assert d["top_concentration"]["above_limit"] is True
    codes = {a["code"] for a in d["alerts"]}
    assert "SINGLE_STOCK_ABOVE_LIMIT" in codes
    assert d["onboarding_step"] == "PREFERENCES"


async def test_dashboard_with_no_data(client):
    h = await register_headers(client)
    r = await client.get(f"{API}/dashboard", headers=h)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["net_worth"] == 0
    assert d["risk"] is None
    assert d["onboarding_step"] == "FINANCIAL_PROFILE"


async def test_goal_priority_defaults_per_type(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/goals", json={"goal_type": "HOME_DOWN_PAYMENT", "target_amount": 100}, headers=h)
    assert r.json()["data"]["priority"] == "OPTIONAL"
    r = await client.post(
        f"{API}/goals", json={"goal_type": "HOME_DOWN_PAYMENT", "target_amount": 100, "priority": "ESSENTIAL"}, headers=h
    )
    assert r.json()["data"]["priority"] == "ESSENTIAL"
