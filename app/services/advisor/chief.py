"""Chief Financial Intelligence Agent: combines the specialists into one prioritized plan.

``build_chief_context`` collects the specialists' insights (the knowledge layer) and the key
numbers. ``offline_chief`` is the rule-based version (no LLM); the Claude version gets the same
context and returns the same shape.
"""

from typing import Any

from app.services.advisor.agents import IMPACT_RANK, money
from app.services.advisor.profile import CustomerProfile

# Why one area is acted on before another: protect first, then remove waste, then grow.
AGENT_WEIGHT = {"BUDGET": 3, "LOAN": 3, "INSURANCE": 4, "TAX": 2, "RSU": 3, "INVESTMENT": 3, "ESTATE": 2, "GOAL": 1}
RISK_OVERRIDES = {"get-term-life": "HIGH", "build-emergency-fund": "HIGH", "diversify-single-stock": "HIGH",
                  "make-will": "MEDIUM", "deploy-idle-cash": "LOW", "keep-low-rate-mortgage": "LOW"}
EFFORT_PENALTY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
MAX_RECOMMENDATIONS = 10


def build_chief_context(profile: CustomerProfile, agent_insights: dict[str, dict], agent_names: dict[str, str],
                        agent_metrics: dict[str, list], previous: list[dict]) -> dict[str, Any]:
    cf = profile.get("cashflow") or {}
    return {
        "currency": profile.currency,
        "balance_sheet": profile.get("balance_sheet"),
        "cashflow": {k: cf.get(k) for k in ("monthly_salary", "monthly_other_income", "monthly_spend",
                                             "monthly_saving_investing", "savings_rate_pct", "months_covered")},
        "personal": profile.get("personal"),
        "risk_profile": profile.get("risk"),
        "goals": profile.get("goals"),
        "agents": {
            k: {"name": agent_names[k], "metrics": agent_metrics.get(k, []), **v} for k, v in sorted(agent_insights.items())
        },
        "previous_recommendations": previous,
    }


def _merge(context: dict) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for agent_key, ins in context["agents"].items():
        for r in ins.get("recommendations") or []:
            m = merged.get(r["key"])
            if m is None:
                merged[r["key"]] = {**r, "agents": [agent_key]}
                continue
            m["agents"].append(agent_key)
            if IMPACT_RANK[r["impact"]] > IMPACT_RANK[m["impact"]]:
                m["impact"] = r["impact"]
            # keep the first agent's title / why / steps / amount together so the text stays consistent
    return merged


def _conflicts(keys: set[str], cur: str, context: dict) -> list[dict]:
    out = []
    if {"diversify-single-stock", "plan-equity-tax"} <= keys:
        out.append({
            "title": "Selling company stock vs. the tax bill",
            "agents": ["RSU", "INVESTMENT", "TAX"],
            "detail": "Diversifying employer stock lowers risk but realises gains that are taxed.",
            "resolution": "Sell in stages spread across tax years, and pair sales with any investment losses where the "
                          "rules allow; never let the tax delay the plan for more than a year.",
        })
    if "deploy-idle-cash" in keys and ({"plan-lease-end", "plan-equity-tax", "get-term-life"} & keys):
        out.append({
            "title": "Investing idle cash vs. known costs coming up",
            "agents": ["BUDGET", "INVESTMENT", "LOAN", "TAX"],
            "detail": "Some cash will be needed soon (lease change, tax on sales, new insurance premiums).",
            "resolution": "Keep 6 months of expenses plus the next 9 months of known costs in cash; invest only the rest, "
                          "in instalments.",
        })
    if "deploy-idle-cash" in keys and "prepay-expensive-debt" in keys:
        out.append({
            "title": "Invest the cash or repay debt?",
            "agents": ["LOAN", "INVESTMENT"],
            "detail": "Both want the same surplus cash.",
            "resolution": "Repay debt that costs more than you can safely earn first; invest the remainder.",
        })
    return out


def offline_chief(context: dict) -> dict:
    cur = context["currency"]
    merged = _merge(context)
    ranked = []
    for key, r in merged.items():
        risk = RISK_OVERRIDES.get(key, r["impact"])
        score = (IMPACT_RANK[r["impact"]] * 10 + IMPACT_RANK[risk] * 5
                 + max(AGENT_WEIGHT.get(a, 1) for a in r["agents"]) - EFFORT_PENALTY[r["effort"]])
        ranked.append((score, key, {**r, "risk": risk}))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    recs = [{**r, "priority": i} for i, (_, _, r) in enumerate(ranked[:MAX_RECOMMENDATIONS], start=1)]

    healths = [a.get("health") for a in context["agents"].values()]
    health = ("ACTION_NEEDED" if healths.count("ACTION_NEEDED") >= 2
              else "WATCH" if "ACTION_NEEDED" in healths or "WATCH" in healths else "GOOD")
    bs = context.get("balance_sheet") or {}
    top = recs[0]["title"] if recs else "Keep going: nothing urgent right now"
    themes = " and ".join(f"'{r['title']}'" for r in recs[1:3])
    summary = (f"Net worth is {money(bs.get('net_worth'), cur)} ({money(bs.get('liquid_net_worth'), cur)} liquid, "
               f"{money(bs.get('total_liabilities'), cur)} owed). "
               f"{len(recs)} actions are ranked by impact and risk; after the first, focus on {themes}." if recs else
               f"Net worth is {money(bs.get('net_worth'), cur)}. No urgent actions.")
    return {
        "headline": f"Top priority: {top}",
        "summary": summary,
        "health": health,
        "conflicts": _conflicts(set(merged), cur, context),
        "recommendations": recs,
    }
