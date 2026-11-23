"""LLM providers for the advisor.

- ``OfflineProvider``: deterministic rule engine. No API key, no cost; used by default and in tests.
- ``ClaudeProvider``: Claude via the Anthropic API. Structured JSON output (validated against the
  same Pydantic models), cached system prompts, server-side refusal fallbacks.

Numbers always come from the backend's ``facts``; the model explains, prioritizes and writes.
"""

import json
import logging
import re
from abc import ABC, abstractmethod

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.advisor import AGENT_JSON_SCHEMA, CHIEF_JSON_SCHEMA, AgentInsight, ChiefInsight
from app.services.advisor.agents import AgentSpec, money
from app.services.advisor.chief import offline_chief

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """The model couldn't produce a usable answer (API error, refusal, invalid output)."""


SHARED_KEYS = ("deploy-idle-cash", "build-emergency-fund", "diversify-single-stock", "plan-equity-tax",
               "keep-low-rate-mortgage", "prepay-expensive-debt", "get-term-life", "make-will")

CHAT_KEYWORDS = {
    "LOAN": ("loan", "mortgage", "emi", "prepay", "lease", "debt", "repay", "interest rate"),
    "TAX": ("tax", "gain", "deduct", "allowance"),
    "INSURANCE": ("insur", "life cover", "health cover", "policy"),
    "INVESTMENT": ("invest", "portfolio", "fund", "stock", "crypto", "diversif", "allocation"),
    "BUDGET": ("spend", "budget", "saving", "expense", "cash", "emergency", "bills"),
    "RSU": ("rsu", "employer", "vest", "esop", "company stock"),
    "ESTATE": ("will", "estate", "beneficiar", "inherit", "attorney"),
    "GOAL": ("goal", "retire", "house", "education", "target", "sabbatical"),
}


def route_question(message: str) -> list[str]:
    text = message.lower()
    # match at the start of a word, so "vest" doesn't match "invest"
    hits = [(sum(len(re.findall(rf"\b{re.escape(w)}", text)) for w in words), key) for key, words in CHAT_KEYWORDS.items()]
    return [key for n, key in sorted(hits, reverse=True) if n][:2]


class LLMProvider(ABC):
    name: str
    model: str | None = None

    @abstractmethod
    async def agent_insight(self, spec: AgentSpec, facts: dict, previous: dict | None) -> dict: ...

    @abstractmethod
    async def chief_insight(self, context: dict) -> dict: ...

    @abstractmethod
    async def chat(self, context: dict, history: list[dict], message: str) -> tuple[str, list[str]]: ...


# ---- offline -------------------------------------------------------------------------------------

class OfflineProvider(LLMProvider):
    name = "offline"

    async def agent_insight(self, spec: AgentSpec, facts: dict, previous: dict | None) -> dict:
        return AgentInsight.model_validate(spec.offline(facts)).model_dump()

    async def chief_insight(self, context: dict) -> dict:
        return ChiefInsight.model_validate(offline_chief(context)).model_dump()

    async def chat(self, context: dict, history: list[dict], message: str) -> tuple[str, list[str]]:
        agents = route_question(message)
        cur = context.get("currency")
        parts = []
        if not agents:
            chief = context.get("chief") or {}
            parts.append(chief.get("headline") or "Here's where you stand.")
            if chief.get("summary"):
                parts.append(chief["summary"])
            steps = [r for r in context.get("recommendations", []) if r["status"] in ("OPEN", "IN_PROGRESS")][:3]
            if steps:
                parts.append("Your next steps:\n" + "\n".join(f"{i}. {r['title']} — {r['why']}" for i, r in enumerate(steps, 1)))
        for key in agents:
            a = context["agents"].get(key)
            if not a:
                continue
            parts.append(f"{a['name']}: {a.get('summary') or 'No analysis yet.'}")
            for r in (a.get("recommendations") or [])[:2]:
                amount = f" ({money(r['amount'], cur)})" if r.get("amount") else ""
                parts.append(f"• {r['title']}{amount}: {r['why']}")
        parts.append("(Answered from your saved analysis. Turn on Claude for free-form conversation.)")
        return "\n\n".join(parts), agents or ["CHIEF"]


# ---- Claude --------------------------------------------------------------------------------------

AGENT_SYSTEM = """You are one specialist in a team of financial-analysis agents working for one customer of a \
personal-finance app. You write that customer's analysis for your area.

Rules:
- Use only the numbers in FACTS. They were computed by the backend; never recompute, invent or estimate other figures. \
If something you need is missing, say so in data_gaps.
- Amounts are in the customer's main currency (given as CURRENCY). Write amounts with the currency symbol.
- Tax and legal rules depend on the customer's country; describe them as things to confirm, not as certainties.
- You give educational insights, not regulated investment advice: no specific products, providers or tickers to buy.
- Be specific and plain: short sentences, concrete numbers, no jargon.
- At most 4 findings and 4 recommendations, most important first. Each recommendation needs 1-3 concrete action steps.
- Recommendation keys are stable kebab-case ids. Reuse the key from PREVIOUS INSIGHT when it is the same action. \
For these actions always use exactly these keys so other agents' advice can be merged: """ + ", ".join(SHARED_KEYS) + """.
- amount is the money involved in the action (0 when not applicable).
- health: GOOD (nothing important to do), WATCH (worth attention), ACTION_NEEDED (a real risk or a costly gap)."""

CHIEF_SYSTEM = """You are the Chief Financial Intelligence Agent of a personal-finance app. Specialist agents \
(budget, loan, investment, tax, insurance, RSU, estate, goal) have each analysed one area for this customer. You \
turn their work into one plan.

Your job:
- Understand the customer's whole position from BALANCE SHEET, CASH FLOW and the AGENTS' insights.
- Find relationships and conflicts between areas (for example, selling employer stock vs. the tax it triggers; \
investing idle cash vs. costs that are coming up) and say how to resolve each one.
- Produce at most 10 recommendations, prioritized by potential impact, the risk of not acting, effort, and the \
customer's goals and risk profile. priority 1 = do first; priorities are 1..N without gaps.
- Keep a specialist's key when you keep its recommendation; merge recommendations that are the same action \
(list every contributing agent in agents). Explain in why exactly why it matters for this customer, with numbers.
- PREVIOUS RECOMMENDATIONS shows what the customer has done or dismissed: do not re-suggest dismissed actions unless \
the situation changed, and acknowledge progress on done ones in the summary.
- Use only numbers that appear in the input. Educational insights, not regulated advice; no specific products.
- headline: one sentence, the single most important thing. summary: 2-4 sentences on the overall position."""

CHAT_SYSTEM = """You are the customer's personal financial intelligence assistant inside a personal-finance app. \
CONTEXT holds this customer's latest analysis from a team of specialist agents and the Chief agent.

- Answer from CONTEXT. Use its numbers; never invent figures. If the answer needs data you don't have, say what is \
missing and how the customer can add it (connect an account or fill in a form in the app).
- Be concise and practical: a direct answer first, then the reasoning, then next steps if useful. Plain text, short \
paragraphs or a short list. Use the customer's currency.
- Educational guidance, not regulated advice: no specific products or tickers; suggest a licensed adviser for \
complex tax or legal decisions.
- If asked about something unrelated to their finances, briefly steer back."""


def _dump(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self) -> None:
        self.model = settings.LLM_MODEL
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=180.0, max_retries=2)

    async def _create(self, *, system: list[dict], messages: list[dict], effort: str, schema: dict | None = None):
        output_config: dict = {"effort": effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            resp = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # on a safety decline, retry on the fallback model inside the same call
                system=system,
                messages=messages,
                output_config=output_config,
            )
        except anthropic.RateLimitError as e:
            raise LLMError("AI service is busy (rate limited)") from e
        except anthropic.AuthenticationError as e:
            raise LLMError("AI service rejected the API key") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"AI service error {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("AI service unreachable") from e
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"AI response stopped: {resp.stop_reason}")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise LLMError("AI response had no text")
        logger.info("claude call model=%s input=%s cache_read=%s output=%s", resp.model, resp.usage.input_tokens,
                    resp.usage.cache_read_input_tokens, resp.usage.output_tokens)
        return text

    async def _json(self, system: str, user: str, schema: dict, effort: str, model_cls: type[BaseModel]) -> dict:
        text = await self._create(
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}], effort=effort, schema=schema,
        )
        try:
            return model_cls.model_validate_json(text).model_dump()
        except ValidationError as e:
            raise LLMError("AI response didn't match the expected format") from e

    async def agent_insight(self, spec: AgentSpec, facts: dict, previous: dict | None) -> dict:
        facts_for_model = {k: v for k, v in facts.items() if k != "metrics"}
        user = (
            f"AGENT: {spec.name} - {spec.description}\nFOCUS: {spec.focus}\nCURRENCY: {facts.get('currency')}\n\n"
            f"FACTS:\n{_dump(facts_for_model)}\n\nPREVIOUS INSIGHT:\n{_dump(previous or {})}\n\n"
            "Write your insight for this customer."
        )
        system = AGENT_SYSTEM + f"\n\nYou are the {spec.name}: {spec.description}."
        return await self._json(system, user, AGENT_JSON_SCHEMA, settings.LLM_AGENT_EFFORT, AgentInsight)

    async def chief_insight(self, context: dict) -> dict:
        user = (
            f"CURRENCY: {context['currency']}\n\nBALANCE SHEET:\n{_dump(context['balance_sheet'])}\n\n"
            f"CASH FLOW:\n{_dump(context['cashflow'])}\n\nPERSONAL:\n{_dump(context['personal'])}\n\n"
            f"RISK PROFILE:\n{_dump(context['risk_profile'])}\n\nGOALS:\n{_dump(context['goals'])}\n\n"
            f"AGENTS:\n{_dump(context['agents'])}\n\nPREVIOUS RECOMMENDATIONS:\n{_dump(context['previous_recommendations'])}\n\n"
            "Write the customer's plan."
        )
        return await self._json(CHIEF_SYSTEM, user, CHIEF_JSON_SCHEMA, settings.LLM_CHIEF_EFFORT, ChiefInsight)

    async def chat(self, context: dict, history: list[dict], message: str) -> tuple[str, list[str]]:
        system = [
            {"type": "text", "text": CHAT_SYSTEM},
            # The analysis only changes when agents regenerate, so it caches across the conversation.
            {"type": "text", "text": f"CONTEXT:\n{_dump(context)}", "cache_control": {"type": "ephemeral"}},
        ]
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": message})
        text = await self._create(system=system, messages=messages, effort=settings.LLM_CHAT_EFFORT)
        return text.strip(), route_question(message) or ["CHIEF"]


def get_llm_provider() -> LLMProvider:
    if settings.LLM_PROVIDER.lower() == "claude":
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("LLM_PROVIDER=claude but ANTHROPIC_API_KEY is empty; using the offline rule engine")
            return OfflineProvider()
        return ClaudeProvider()
    return OfflineProvider()
