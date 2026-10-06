"""The 5 calibration screens: Money, Equity, Risk, Goals, Preferences.

Numbers follow the app prototype: income 60L, spend 2.6L/month, cash 18.5L.
"""

from datetime import date, timedelta

from tests.conftest import API, RISK_PROFILE, give_credit_consent, register_headers

MONEY = {"annual_income": 6000000, "monthly_spend": 260000, "cash_reserve": 1850000, "currency": "INR"}
EQUITY = {"employer_name": "Helio Systems", "ticker": "helo", "vested_value": 2500000, "unvested_value": 1200000}


# ---- 1. Money -----------------------------------------------------------------------------------

async def test_money_screen_saves_four_fields_and_returns_tiles(client):
    h = await register_headers(client)
    r = await client.put(f"{API}/financial-profile", json=MONEY, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["is_saved"] is True
    assert d["summary"] == {"monthly_surplus": 240000, "runway_months": 7.1}
    assert d["profile"]["age"] is None and d["profile"]["employment_type"] is None
    assert d["profile"]["total_debt"] == 0


async def test_money_screen_uses_credit_debt_and_keeps_unsent_fields(client):
    h = await register_headers(client, "9876543210")
    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)

    r = await client.put(f"{API}/financial-profile", json=MONEY, headers=h)
    assert r.json()["data"]["profile"]["total_debt"] == 682000  # from the backend's credit data
    assert r.json()["data"]["profile"]["monthly_emi"] == 27950

    await client.put(f"{API}/financial-profile", json={**MONEY, "age": 34}, headers=h)
    r = await client.put(f"{API}/financial-profile", json={**MONEY, "cash_reserve": 2000000}, headers=h)
    profile = r.json()["data"]["profile"]
    assert profile["age"] == 34  # not sent, so kept
    assert profile["cash_reserve"] == 2000000


async def test_money_screen_requires_its_fields(client):
    h = await register_headers(client)
    r = await client.put(f"{API}/financial-profile", json={"annual_income": 6000000}, headers=h)
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert fields == {"monthly_spend", "cash_reserve"}


# ---- 2. Equity ----------------------------------------------------------------------------------

async def test_equity_screen_fields_and_defaults(client):
    h = await register_headers(client)
    await client.put(f"{API}/financial-profile", json={**MONEY, "currency": "USD"}, headers=h)
    vest = (date.today() + timedelta(days=60)).isoformat()
    r = await client.post(f"{API}/equity", json={**EQUITY, "next_vest_date": vest}, headers=h)
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert d["security_name"] == "Helio Systems"  # defaults to employer
    assert d["ticker"] == "HELO"
    assert d["currency"] == "USD"  # follows the reporting currency
    assert d["next_vest_date"] == vest


async def test_equity_next_vest_date_cannot_be_past(client):
    h = await register_headers(client)
    past = (date.today() - timedelta(days=1)).isoformat()
    r = await client.post(f"{API}/equity", json={**EQUITY, "next_vest_date": past}, headers=h)
    assert r.status_code == 422


# ---- 4. Goals -----------------------------------------------------------------------------------

async def _calibrated(client, h):
    await client.put(f"{API}/financial-profile", json=MONEY, headers=h)
    await client.post(f"{API}/equity", json=EQUITY, headers=h)
    await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)


async def test_goal_cards_match_the_screen(client):
    h = await register_headers(client)
    await _calibrated(client, h)
    r = await client.get(f"{API}/goals/suggestions", headers=h)
    cards = r.json()["data"]
    assert [c["goal_type"] for c in cards] == [
        "EMERGENCY_FUND", "EQUITY_TAX_RESERVE", "REDUCE_SINGLE_STOCK_CONCENTRATION", "HOME_DOWN_PAYMENT",
        "RETIREMENT_CORPUS", "CHILD_EDUCATION", "SABBATICAL_RUNWAY", "CLEAR_HIGH_INTEREST_DEBT", "PROTECTION_TOPUP",
    ]
    by = {c["goal_type"]: c for c in cards}
    target = lambda t: by[t]["calculation"]["suggested_target_amount"]  # noqa: E731
    assert target("EMERGENCY_FUND") == 1560000  # 6 x 2.6L = 15.60L
    assert target("RETIREMENT_CORPUS") == 78000000  # 25 x 31.2L = 7.80Cr
    assert target("SABBATICAL_RUNWAY") == 3120000  # 12 x 2.6L
    assert target("PROTECTION_TOPUP") == 90000000  # 15 x 60L
    assert target("EQUITY_TAX_RESERVE") == 360000  # 30% of 12L unvested
    assert by["HOME_DOWN_PAYMENT"]["category"] == "PROPERTY"
    assert by["CHILD_EDUCATION"]["category"] == "FAMILY"
    assert by["SABBATICAL_RUNWAY"]["category"] == "FREEDOM"
    assert by["HOME_DOWN_PAYMENT"]["calculation"]["required_inputs"] == ["property_value"]
    assert set(by["CHILD_EDUCATION"]["calculation"]["required_inputs"]) == {"education_cost_today", "years_to_admission"}
    assert target("CLEAR_HIGH_INTEREST_DEBT") is None  # no credit report yet


async def test_goal_inputs_size_the_target(client):
    h = await register_headers(client)
    await _calibrated(client, h)
    r = await client.post(
        f"{API}/goals", json={"goal_type": "HOME_DOWN_PAYMENT", "inputs": {"property_value": 15000000}}, headers=h
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["target_amount"] == 4050000  # 27% of 1.5Cr
    r = await client.post(
        f"{API}/goals",
        json={"goal_type": "CHILD_EDUCATION", "inputs": {"education_cost_today": 2000000, "years_to_admission": 10}},
        headers=h,
    )
    assert r.json()["data"]["target_amount"] == 4317849.99  # 20L x 1.08^10
    assert r.json()["data"]["inputs"] == {"education_cost_today": 2000000, "years_to_admission": 10}


async def test_high_interest_debt_from_credit_report(client):
    h = await register_headers(client, "9876543218")  # risky profile: 15.25% loan + 2 cards
    await give_credit_consent(client, h)
    await client.post(f"{API}/credit/fetch", headers=h)
    await client.put(f"{API}/financial-profile", json=MONEY, headers=h)
    r = await client.get(f"{API}/goals/suggestions", headers=h)
    debt = next(c for c in r.json()["data"] if c["goal_type"] == "CLEAR_HIGH_INTEREST_DEBT")
    assert debt["calculation"]["suggested_target_amount"] == 310000 + 92000 + 46500


async def test_goal_selection_replaces_the_set(client):
    h = await register_headers(client)
    await _calibrated(client, h)
    six = ["EMERGENCY_FUND", "EQUITY_TAX_RESERVE", "REDUCE_SINGLE_STOCK_CONCENTRATION",
           "RETIREMENT_CORPUS", "SABBATICAL_RUNWAY", "PROTECTION_TOPUP"]
    r = await client.put(f"{API}/goals/selection", json={"goals": [{"goal_type": t} for t in six]}, headers=h)
    assert r.status_code == 200, r.text
    assert sorted(g["goal_type"] for g in r.json()["data"]["goals"]) == sorted(six)
    ef_id = next(g["id"] for g in r.json()["data"]["goals"] if g["goal_type"] == "EMERGENCY_FUND")

    # user goes back, unticks most, adds home with its input
    r = await client.put(
        f"{API}/goals/selection",
        json={"goals": [{"goal_type": "EMERGENCY_FUND"},
                        {"goal_type": "HOME_DOWN_PAYMENT", "inputs": {"property_value": 10000000}}]},
        headers=h,
    )
    goals = r.json()["data"]["goals"]
    assert sorted(g["goal_type"] for g in goals) == ["EMERGENCY_FUND", "HOME_DOWN_PAYMENT"]
    assert next(g["id"] for g in goals if g["goal_type"] == "EMERGENCY_FUND") == ef_id  # kept, not recreated


async def test_goal_selection_is_all_or_nothing(client):
    h = await register_headers(client)
    await _calibrated(client, h)
    r = await client.put(
        f"{API}/goals/selection",
        json={"goals": [{"goal_type": "EMERGENCY_FUND"}, {"goal_type": "HOME_DOWN_PAYMENT"}]},  # home lacks input
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "GOAL_TARGET_REQUIRED"
    assert "property_value" in r.json()["message"]
    assert (await client.get(f"{API}/goals", headers=h)).json()["data"]["goals"] == []


async def test_goal_selection_rejects_duplicates(client):
    h = await register_headers(client)
    r = await client.put(
        f"{API}/goals/selection", json={"goals": [{"goal_type": "EMERGENCY_FUND"}, {"goal_type": "EMERGENCY_FUND"}]},
        headers=h,
    )
    assert r.status_code == 422


# ---- 5. Preferences -----------------------------------------------------------------------------

async def test_preferences_defaults_and_save(client):
    h = await register_headers(client)
    r = await client.get(f"{API}/preferences", headers=h)
    d = r.json()["data"]
    assert d["is_saved"] is False
    assert (d["insight_tone"], d["vesting_alerts"], d["tax_deadline_alerts"], d["weekly_digest"]) == (
        "BALANCED", True, True, False
    )
    r = await client.put(f"{API}/preferences", json={"insight_tone": "DETAILED", "weekly_digest": True}, headers=h)
    d = r.json()["data"]
    assert d["is_saved"] is True
    assert d["insight_tone"] == "DETAILED" and d["weekly_digest"] is True and d["vesting_alerts"] is True


async def test_preferences_validation(client):
    h = await register_headers(client)
    r = await client.put(f"{API}/preferences", json={"insight_tone": "LOUD"}, headers=h)
    assert r.status_code == 422


# ---- whole journey ------------------------------------------------------------------------------

async def test_calibration_journey_and_resume(client):
    h = await register_headers(client, "9876543210")

    async def step():
        return (await client.get(f"{API}/onboarding/status", headers=h)).json()["data"]["current_step"]

    assert await step() == "FINANCIAL_PROFILE"
    await client.put(f"{API}/financial-profile", json=MONEY, headers=h)
    assert await step() == "EQUITY"
    await client.post(f"{API}/equity", json=EQUITY, headers=h)
    assert await step() == "RISK"
    await client.put(f"{API}/risk-profile", json=RISK_PROFILE, headers=h)
    assert await step() == "GOALS"

    # user closes the app here; logging in again resumes at GOALS
    await client.post(f"{API}/auth/login/request-otp", json={"mobile": "9876543210"})
    r = await client.post(f"{API}/auth/login/verify-otp", json={"mobile": "9876543210", "otp": "123456"})
    assert r.json()["data"]["next_step"] == "GOALS"

    await client.put(f"{API}/goals/selection", json={"goals": [{"goal_type": "EMERGENCY_FUND"}]}, headers=h)
    assert await step() == "PREFERENCES"
    await client.put(f"{API}/preferences", json={}, headers=h)
    assert await step() == "COMPLETED"
