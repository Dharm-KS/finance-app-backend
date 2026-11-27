"""Aggregator import -> 8 agents + Chief -> recommendations, chat, persistence and updates."""

import copy
import json
from pathlib import Path

import pytest

from tests.conftest import API, RISK_PROFILE, register_headers

FIXTURES = Path(__file__).resolve().parents[1] / "app/services/providers/aggregator/fixtures"


MONEY = {"annual_income": 6000000, "monthly_spend": 260000, "cash_reserve": 1850000, "currency": "INR"}


async def _answer_screens(client, h) -> None:
    """The onboarding screens after the bank step (money, equity skipped, risk, goals, preferences)."""
    for method, path, body in [
        ("PUT", "/financial-profile", MONEY),
        ("POST", "/onboarding/skip", {"step": "EQUITY"}),
        ("PUT", "/risk-profile", {**RISK_PROFILE, "single_stock_limit_percent": 10}),
        ("PUT", "/goals/selection", {"goals": [{"goal_type": "EMERGENCY_FUND"}]}),
        ("PUT", "/preferences", {}),
    ]:
        r = await client.request(method, f"{API}{path}", json=body, headers=h)
        assert r.status_code in (200, 201), r.text


async def _connect(client, h, onboard: bool = True) -> dict:
    """Answer the screens, then connect the bank: the connection completes onboarding, so it analyses."""
    if onboard:
        await _answer_screens(client, h)
    r = await client.post(f"{API}/aggregator/connections", headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["data"]["connection"]["id"]
    r = await client.post(f"{API}/aggregator/connections/{cid}/verify-otp", json={"otp": "123456"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fixtures() -> list[dict]:
    return [json.loads((FIXTURES / n).read_text()) for n in ("report_bank_checking.json", "report_bank_savings.json")]


async def test_connect_imports_every_section(client):
    h = await register_headers(client)
    data = await _connect(client, h)
    assert data["data_changed"] is True
    assert data["connection"]["status"] == "ACTIVE"
    assert data["analysis"]["status"] == "COMPLETED"
    assert [rep["sections"]["portfolios"] for rep in data["reports"]] == [4, 4]

    r = await client.get(f"{API}/aggregator/data", headers=h)
    counts = r.json()["data"]["counts"]
    assert counts == {
        "user_information": 2, "accounts": 2, "portfolios": 8, "cards": 2, "loans": 2, "properties": 2,
        "receipts": 7, "leases": 2, "deposits": 2, "account_transactions": 88,
    }


async def test_wrong_aggregator_otp(client):
    h = await register_headers(client)
    cid = (await client.post(f"{API}/aggregator/connections", headers=h)).json()["data"]["connection"]["id"]
    r = await client.post(f"{API}/aggregator/connections/{cid}/verify-otp", json={"otp": "000000"}, headers=h)
    assert r.status_code == 400
    assert r.json()["error_code"] == "OTP_INVALID"


async def test_agents_and_chief_are_ready(client):
    h = await register_headers(client)
    await _connect(client, h)
    s = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]
    assert s["ready"] is True and s["running"] is False and s["stale"] is False
    assert {a["key"]: a["status"] for a in s["agents"]} == {k: "READY" for k in (
        "INVESTMENT", "TAX", "INSURANCE", "LOAN", "BUDGET", "RSU", "ESTATE", "GOAL", "CHIEF")}

    o = (await client.get(f"{API}/advisor/overview", headers=h)).json()["data"]
    assert o["ready"] and o["headline"].startswith("Top priority")
    assert o["currency"] == "INR"
    assert o["fx_rates"] == {"EUR": 100.0}
    assert [st["step"] for st in o["steps"]] == list(range(1, len(o["steps"]) + 1))
    keys = {st["key"] for st in o["steps"]}
    assert {"diversify-single-stock", "get-term-life", "deploy-idle-cash"} <= keys
    merged = next(st for st in o["steps"] if st["key"] == "diversify-single-stock")
    assert set(merged["agents"]) >= {"RSU", "INVESTMENT"}  # same action from two agents, merged
    assert any(c["title"].startswith("Selling company stock") for c in o["conflicts"])
    assert len(o["agents"]) == 8


async def test_agent_detail_has_no_personal_identifiers(client):
    h = await register_headers(client)
    await _connect(client, h)
    r = await client.get(f"{API}/advisor/agents/rsu", headers=h)
    a = r.json()["data"]
    assert a["key"] == "RSU" and a["health"] == "ACTION_NEEDED"
    assert a["metrics"][0]["label"] == "Employer stock"
    blob = json.dumps(a) + json.dumps((await client.get(f"{API}/advisor/profile", headers=h)).json())
    for pii in ("ANTONIO", "05249217L", "ES5599996121358988109440", "CALLE DE LA MAQUINA", "+34600123456"):
        assert pii not in blob
    assert (await client.get(f"{API}/advisor/agents/nope", headers=h)).status_code == 404


async def test_unchanged_refresh_does_not_reanalyse(client):
    h = await register_headers(client)
    cid = (await _connect(client, h))["connection"]["id"]
    r = await client.post(f"{API}/aggregator/connections/{cid}/refresh", headers=h)
    assert r.json()["data"]["data_changed"] is False
    assert r.json()["data"]["analysis"] is None


async def test_new_report_regenerates_only_affected_agents(client):
    h = await register_headers(client)
    cid = (await _connect(client, h))["connection"]["id"]
    reports = _fixtures()
    updated = copy.deepcopy(reports)
    updated[0]["payload"]["leases"][0]["financials"]["initial_fee"] = 600.0  # only the car lease changes

    r = await client.post(f"{API}/aggregator/connections/{cid}/reports", json={"reports": updated}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["data_changed"] is True
    s = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]
    assert s["last_run"]["agents_regenerated"] == ["LOAN", "CHIEF"]
    assert "BUDGET" in s["last_run"]["agents_unchanged"]
    versions = {a["key"]: a["version"] for a in s["agents"]}
    assert versions["LOAN"] == 2 and versions["BUDGET"] == 1 and versions["CHIEF"] == 2


async def test_invalid_report_is_rejected(client):
    h = await register_headers(client)
    cid = (await _connect(client, h))["connection"]["id"]
    r = await client.post(f"{API}/aggregator/connections/{cid}/reports", json={"reports": [{"success": False}]}, headers=h)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_REPORT"


async def test_recommendation_status_survives_regeneration(client):
    h = await register_headers(client)
    await _connect(client, h)
    first = (await client.get(f"{API}/advisor/recommendations", headers=h)).json()["data"]["steps"][0]
    r = await client.patch(f"{API}/advisor/recommendations/{first['id']}", json={"status": "DONE"}, headers=h)
    assert r.json()["data"]["status"] == "DONE"

    await client.post(f"{API}/advisor/refresh", json={"force": True}, headers=h)
    recs = (await client.get(f"{API}/advisor/recommendations", headers=h)).json()["data"]
    assert first["key"] not in {s["key"] for s in recs["steps"]}
    assert recs["completed"][0]["key"] == first["key"]
    assert recs["steps"][0]["step"] == 1


async def test_chat(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/advisor/chat", json={"message": "hi"}, headers=h)
    assert r.status_code == 409 and r.json()["error_code"] == "ADVISOR_NOT_READY"

    await _connect(client, h)
    r = await client.post(f"{API}/advisor/chat", json={"message": "Should I prepay my mortgage?"}, headers=h)
    assert r.status_code == 200, r.text
    answer = r.json()["data"]["answer"]
    assert answer["role"] == "assistant" and answer["agents"] == ["LOAN"]
    assert "Loan Agent" in answer["content"]
    r = await client.post(f"{API}/advisor/chat", json={"message": "What should I do first?"}, headers=h)
    assert "Top priority" in r.json()["data"]["answer"]["content"]

    hist = (await client.get(f"{API}/advisor/chat", headers=h)).json()["data"]["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]


async def test_extra_form_data_updates_the_estate_agent(client):
    h = await register_headers(client)
    await _connect(client, h)
    before = (await client.get(f"{API}/advisor/agents/ESTATE", headers=h)).json()["data"]
    assert "make-will" in {r["key"] for r in before["recommendations"]}

    r = await client.post(f"{API}/advisor/extra-data", json={"category": "ESTATE", "data": {"has_will": True}}, headers=h)
    assert r.status_code == 201
    after = (await client.get(f"{API}/advisor/agents/ESTATE", headers=h)).json()["data"]
    assert "make-will" not in {r["key"] for r in after["recommendations"]}
    assert after["version"] == before["version"] + 1


async def test_cross_user_isolation(client):
    alice = await register_headers(client, "9876543210", "Alice")
    bob = await register_headers(client, "9876543215", "Bob")
    cid = (await _connect(client, alice))["connection"]["id"]
    rec_id = (await client.get(f"{API}/advisor/recommendations", headers=alice)).json()["data"]["steps"][0]["id"]

    assert (await client.post(f"{API}/aggregator/connections/{cid}/refresh", headers=bob)).status_code == 404
    assert (await client.patch(f"{API}/advisor/recommendations/{rec_id}", json={"status": "DONE"}, headers=bob)).status_code == 404
    assert (await client.get(f"{API}/advisor/overview", headers=bob)).json()["data"]["ready"] is False
    assert (await client.get(f"{API}/aggregator/data", headers=bob)).json()["data"]["counts"]["accounts"] == 0


async def test_web_ui_is_served(client):
    r = await client.get("/app/")
    assert r.status_code == 200 and "<title>" in r.text


# ---- Claude provider (mocked client: no network, no key needed) ----------------------------------

class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Usage:
    input_tokens = cache_read_input_tokens = output_tokens = 1


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.content, self.stop_reason, self.usage, self.model = [_Block(text)], stop, _Usage(), "claude-opus-5-5"


class _FakeMessages:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    async def create(self, **kw):
        self.calls.append(kw)
        return self.resp


@pytest.fixture
def claude(monkeypatch):
    from app.core.config import settings
    from app.services.advisor.llm import ClaudeProvider

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    p = ClaudeProvider()
    return p


async def test_claude_agent_call_shape_and_parsing(claude):
    from app.services.advisor.agents import AGENTS_BY_KEY
    from app.models.enums import AgentKey

    good = {"summary": "s", "health": "WATCH", "findings": [], "data_gaps": [],
            "recommendations": [{"key": "k", "title": "t", "why": "w", "action_steps": ["a"], "impact": "LOW",
                                 "effort": "LOW", "timeframe": "NOW", "amount": 0}]}
    fake = _FakeMessages(_Resp(json.dumps(good)))
    claude.client.beta.messages = fake
    out = await claude.agent_insight(AGENTS_BY_KEY[AgentKey.LOAN], {"currency": "EUR", "metrics": []}, None)
    assert out["recommendations"][0]["key"] == "k"
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_claude_refusal_raises(claude):
    from app.services.advisor.llm import LLMError

    claude.client.beta.messages = _FakeMessages(_Resp("{}", stop="refusal"))
    with pytest.raises(LLMError):
        await claude.chief_insight({"currency": "EUR", "balance_sheet": {}, "cashflow": {}, "personal": {},
                                    "risk_profile": None, "goals": [], "agents": {}, "previous_recommendations": []})


def test_chat_routing_matches_word_starts():
    from app.services.advisor.llm import route_question

    assert route_question("Should I prepay my mortgage or invest my spare cash?") == ["LOAN", "INVESTMENT"]
    assert route_question("When is my next RSU vest?") == ["RSU"]
    assert route_question("hello") == []


async def test_everything_is_shown_in_rupees(client):
    h = await register_headers(client)
    await _connect(client, h)
    # stored data keeps the provider's currency; what the customer sees is converted (EUR at 100 by default)
    data = (await client.get(f"{API}/aggregator/data", headers=h)).json()["data"]
    assert data["currency"] == "INR"
    checking = next(a for a in data["accounts"] if a["subtype"] == "checking")
    assert checking["balance"] == 6551158 and checking["original_currency"] == "EUR"

    profile = (await client.get(f"{API}/advisor/profile", headers=h)).json()["data"]
    assert profile["currency"] == "INR"
    assert profile["balance_sheet"]["cash"] == round((65511.58 + 25115.64) * 100, 2)
    assert profile["fx"]["rates_used"] == {"EUR": 100.0}

    o = (await client.get(f"{API}/advisor/overview", headers=h)).json()["data"]
    assert "₹" in o["summary"] and "€" not in o["summary"]
    assert all(s["currency"] == "INR" for s in o["steps"])


def test_rupee_formatting_uses_indian_grouping():
    from app.services.advisor.agents import money

    assert money(53733838.4, "INR") == "₹5,37,33,838"
    assert money(-386400, "INR") == "-₹3,86,400"


# ---- flow: bank first, analysis only after every onboarding screen --------------------------------

async def test_bank_connect_is_first_step_and_analysis_waits_for_onboarding(client):
    h = await register_headers(client)
    st = (await client.get(f"{API}/onboarding/status", headers=h)).json()["data"]
    assert st["current_step"] == "BANK_CONNECT"

    data = await _connect(client, h, onboard=False)  # first screen after login
    assert data["analysis"] is None  # nothing runs on bank data alone
    st = (await client.get(f"{API}/onboarding/status", headers=h)).json()["data"]
    assert st["bank_connected_completed"] is True and st["current_step"] == "FINANCIAL_PROFILE"

    s = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]
    assert s["phase"] == "WAITING_FOR_ONBOARDING" and s["next_onboarding_step"] == "FINANCIAL_PROFILE"
    assert s["progress"] == {"completed": 0, "total": 9}
    r = await client.post(f"{API}/advisor/refresh", json={}, headers=h)
    assert r.status_code == 409 and r.json()["error_code"] == "ONBOARDING_INCOMPLETE"

    await _answer_screens(client, h)  # saving the last screen starts the analysis
    s = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]
    assert s["phase"] == "READY" and s["onboarding_completed"] is True
    assert s["progress"] == {"completed": 9, "total": 9}
    assert s["last_run"]["trigger"] == "PROFILE_UPDATE"

    # the plan uses the screens' answers too (risk screen: 10% single-stock limit)
    rsu = (await client.get(f"{API}/advisor/agents/RSU", headers=h)).json()["data"]
    assert rsu["facts"]["single_stock_limit_pct"] == 10
    o = (await client.get(f"{API}/advisor/overview", headers=h)).json()["data"]
    assert o["phase"] == "READY" and o["steps"] and o["preview_steps"] == []


async def test_bank_step_can_be_skipped(client):
    h = await register_headers(client)
    r = await client.post(f"{API}/onboarding/skip", json={"step": "BANK_CONNECT"}, headers=h)
    assert r.json()["data"]["bank_skipped"] is True
    await _answer_screens(client, h)
    s = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]
    assert s["phase"] == "READY"  # screens alone are enough for a first plan

    # with no bank data, the Money screen drives the numbers
    prof = (await client.get(f"{API}/advisor/profile", headers=h)).json()["data"]
    domains = prof.get("domains", prof)
    assert domains["data_sources"]["filled_from_money_screen"] == ["cashflow", "cash"]
    assert domains["cashflow"]["monthly_salary"] == 500000  # 60L / 12
    assert domains["balance_sheet"]["cash"] == 1850000
    budget = (await client.get(f"{API}/advisor/agents/BUDGET", headers=h)).json()["data"]
    assert budget["facts"]["monthly_spend"] == 260000


async def test_bank_data_wins_over_money_screen(client):
    h = await register_headers(client)
    await _connect(client, h)
    domains = (await client.get(f"{API}/advisor/profile", headers=h)).json()["data"]
    domains = domains.get("domains", domains)
    assert domains["data_sources"]["filled_from_money_screen"] == []
    assert domains["cashflow"].get("source") != "MONEY_SCREEN"
    assert domains["self_reported"]["annual_income"] == 6000000  # still given to the agents for comparison


async def test_editing_a_screen_after_onboarding_reanalyses(client):
    h = await register_headers(client)
    await _connect(client, h)
    before = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]["last_run"]["id"]
    await client.put(f"{API}/risk-profile", json={**RISK_PROFILE, "single_stock_limit_percent": 50}, headers=h)
    run = (await client.get(f"{API}/advisor/status", headers=h)).json()["data"]["last_run"]
    assert run["id"] > before and "RSU" in run["agents_regenerated"]


def test_preview_steps_merge_finished_agents():
    from app.models.advisor import AgentState
    from app.models.enums import AgentKey, AgentStatus
    from app.services.advisor.engine import _preview_steps, _progress

    def rec(key, impact, amount=0):
        return {"key": key, "title": key, "why": "w", "action_steps": ["a"], "impact": impact, "effort": "LOW",
                "timeframe": "NOW", "amount": amount}

    states = {
        AgentKey.RSU: AgentState(agent_key=AgentKey.RSU, status=AgentStatus.READY,
                                 insight={"recommendations": [rec("diversify-single-stock", "HIGH", 5)]}),
        AgentKey.INVESTMENT: AgentState(agent_key=AgentKey.INVESTMENT, status=AgentStatus.READY,
                                        insight={"recommendations": [rec("deploy-idle-cash", "MEDIUM", 9),
                                                                     rec("diversify-single-stock", "HIGH", 5)]}),
        AgentKey.TAX: AgentState(agent_key=AgentKey.TAX, status=AgentStatus.RUNNING, insight=None),
    }
    steps = _preview_steps(states)
    assert [s["key"] for s in steps] == ["diversify-single-stock", "deploy-idle-cash"]  # HIGH impact first
    assert sorted(steps[0]["agents"]) == ["INVESTMENT", "RSU"]  # same action from two agents, shown once
    assert _progress(states) == {"completed": 2, "total": 9}


async def test_api_docs_page_is_served_encrypted(client):
    r = await client.get("/api-docs")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "const PAYLOAD" in r.text and "Open docs" in r.text
    assert "client_secret" not in r.text and "/auth/token" not in r.text  # docs only readable with the password
