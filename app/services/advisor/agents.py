"""The 8 specialist agents.

Each agent has:
- ``domains``: which parts of the customer profile it reads,
- ``facts()``: deterministic numbers computed in code (the LLM never computes money),
- ``offline()``: rule-based insight used when no LLM is configured (and as a safety net),
- ``focus``: what the LLM should look at when Claude is enabled.

Recommendation ``key``s are stable slugs. Agents use the same key for the same action
(e.g. ``deploy-idle-cash``) so the Chief agent can merge them, and the customer's status on a
recommendation survives regenerations.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.time import utctoday
from app.models.enums import AgentKey
from app.services.advisor.profile import CustomerProfile

SYMBOLS = {"EUR": "€", "INR": "₹", "USD": "$", "GBP": "£", "SGD": "S$", "AED": "AED "}
IMPACT_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _indian_grouping(n: int) -> str:
    """1234567 -> '12,34,567' (lakh / crore grouping)."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups) + "," + tail


def money(v: float | None, cur: str) -> str:
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    n = round(abs(v))
    digits = _indian_grouping(n) if cur == "INR" else f"{n:,}"
    return f"{sign}{SYMBOLS.get(cur, cur + ' ')}{digits}"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def metric(label: str, value: Any, unit: str = "") -> dict:
    return {"label": label, "value": value, "unit": unit}


def finding(title: str, detail: str, severity: str = "INFO") -> dict:
    return {"title": title, "detail": detail, "severity": severity}


def rec(key: str, title: str, why: str, steps: list[str], impact: str, effort: str = "LOW",
        timeframe: str = "THIS_MONTH", amount: float | None = None) -> dict:
    return {"key": key, "title": title, "why": why, "action_steps": steps, "impact": impact, "effort": effort,
            "timeframe": timeframe, "amount": round(amount, 2) if amount else 0}


def insight(summary: str, health: str, findings: list, recs: list, gaps: list) -> dict:
    return {"summary": summary, "health": health, "findings": findings, "recommendations": recs, "data_gaps": gaps}


def _months_until(iso: str | None) -> int | None:
    if not iso:
        return None
    d, t = date.fromisoformat(iso), utctoday()
    return (d.year - t.year) * 12 + d.month - t.month


def _cf(p: CustomerProfile) -> dict:
    return p.get("cashflow") or {}


def _bs(p: CustomerProfile) -> dict:
    return p.get("balance_sheet") or {}


def _income(cf: dict) -> float:
    return (cf.get("monthly_salary") or 0) + (cf.get("monthly_other_income") or 0)


# ==== BUDGET =========================================================================================

def budget_facts(p: CustomerProfile) -> dict:
    cf, bs, cur = _cf(p), _bs(p), p.currency
    liquid = (bs.get("cash") or 0) + (bs.get("deposits") or 0)
    essential = cf.get("monthly_essential_spend") or 0
    cats = {k: v for k, v in (cf.get("monthly_by_category") or {}).items()
            if k not in {"SAVINGS_TRANSFER", "PENSION_CONTRIBUTION", "FUND_INVESTMENT", "CRYPTO", "STOCKS", "TRANSFER_OUT"}}
    em = round(liquid / essential, 1) if essential else None
    self_rep = p.get("self_reported") or {}
    return {
        "currency": cur,
        "months_covered": cf.get("months_covered", 0),
        "monthly_income": round(_income(cf), 2),
        "monthly_salary": cf.get("monthly_salary"),
        "monthly_spend": cf.get("monthly_spend"),
        "monthly_essential_spend": essential,
        "monthly_discretionary_spend": cf.get("monthly_discretionary_spend"),
        "monthly_saving_investing": cf.get("monthly_saving_investing"),
        "monthly_transfers_out": cf.get("monthly_transfers_out"),
        "savings_rate_pct": cf.get("savings_rate_pct"),
        "top_spend_categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])[:6]),
        "cash_withdrawals_monthly": cats.get("CASH_WITHDRAWAL", 0),
        "buy_now_pay_later_monthly": cats.get("BUY_NOW_PAY_LATER", 0),
        "liquid_cash": round(liquid, 2),
        "emergency_fund_months": em,
        "recurring_bills": p.get("recurring_bills") or [],
        "self_reported_monthly_spend": self_rep.get("monthly_spend"),
        "metrics": [
            metric("Monthly income", round(_income(cf), 2), cur),
            metric("Monthly spending", cf.get("monthly_spend"), cur),
            metric("Savings rate", cf.get("savings_rate_pct"), "%"),
            metric("Emergency fund", em, "months"),
        ],
    }


def budget_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    if not f["months_covered"]:
        return insight("No bank transactions yet, so spending can't be analysed.", "WATCH", [], [],
                       ["Connect a bank account to analyse income and spending."])
    em, sr = f["emergency_fund_months"], f["savings_rate_pct"]
    essential = f["monthly_essential_spend"] or 0
    finds.append(finding(
        "Where the money goes",
        f"Average monthly income {money(f['monthly_income'], cur)}, spending {money(f['monthly_spend'], cur)} "
        f"({money(essential, cur)} essential), saving or investing {money(f['monthly_saving_investing'], cur)}.",
    ))
    if em is not None and em > 12:
        excess = f["liquid_cash"] - 6 * essential
        finds.append(finding("Large idle cash balance", f"Cash and deposits cover {em} months of essential spending; "
                             "6 months is a common target.", "WARNING"))
        recs.append(rec("deploy-idle-cash", "Put idle cash to work",
                        f"About {money(excess, cur)} sits above a 6-month emergency fund, earning little.",
                        ["Keep 6 months of essential spending as your emergency fund",
                         "Move the rest into investments that match your risk profile, in a few instalments"],
                        "HIGH", "LOW", "THIS_MONTH", excess))
    elif em is not None and em < 3:
        gap = 6 * essential - f["liquid_cash"]
        finds.append(finding("Thin emergency fund", f"Cash covers only {em} months of essential spending.", "CRITICAL"))
        recs.append(rec("build-emergency-fund", "Build a 6-month emergency fund",
                        f"You need about {money(gap, cur)} more to cover 6 months of essential spending.",
                        ["Set up an automatic monthly transfer to a savings account",
                         "Pause non-essential investing until the fund is complete"], "HIGH", "MEDIUM", "THIS_QUARTER", gap))
    if sr is not None and sr < 20:
        need = 0.2 * f["monthly_income"] - (f["monthly_saving_investing"] or 0)
        recs.append(rec("raise-savings-rate", "Raise your savings rate to 20%",
                        f"You save {pct(sr)} of income; 20% builds long-term wealth faster.",
                        [f"Automate an extra {money(need, cur)} a month into savings on payday"], "MEDIUM", "MEDIUM",
                        "THIS_MONTH", need))
    if f["cash_withdrawals_monthly"] > 0.08 * (f["monthly_spend"] or 1):
        recs.append(rec("track-cash-spending", "Track your cash withdrawals",
                        f"About {money(f['cash_withdrawals_monthly'], cur)} a month leaves as cash, which can't be analysed.",
                        ["Pay by card where possible so spending shows up in your budget"], "LOW"))
    if f["buy_now_pay_later_monthly"] > 0:
        recs.append(rec("avoid-bnpl", "Avoid buy-now-pay-later plans",
                        "Instalment purchases add hidden fixed commitments to your budget.",
                        ["Pay off the current plan and use savings for future purchases"], "LOW"))
    if f["months_covered"] < 6:
        gaps.append(f"Only {f['months_covered']} months of transactions; 6–12 months gives more reliable averages.")
    health = "ACTION_NEEDED" if (em is not None and em < 3) or (sr is not None and sr < 5) else (
        "GOOD" if (sr or 0) >= 20 and em is not None and 3 <= em <= 12 else "WATCH")
    summary = (f"You spend {money(f['monthly_spend'], cur)} a month against {money(f['monthly_income'], cur)} income "
               f"and save {pct(sr)}. Cash covers {em} months of essentials.")
    return insight(summary, health, finds, recs, gaps)


# ==== LOAN ===========================================================================================

def loan_facts(p: CustomerProfile) -> dict:
    cf, bs, cur = _cf(p), _bs(p), p.currency
    loans, leases = p.get("loans") or [], p.get("leases") or []
    service = sum(ln.get("monthly_installment") or 0 for ln in loans) + sum(ls.get("monthly") or 0 for ls in leases if ls.get("status") == "active")
    income = _income(cf)
    total = sum(ln.get("pending") or 0 for ln in loans)
    wrate = round(sum((ln.get("pending") or 0) * (ln.get("rate") or 0) for ln in loans) / total, 2) if total else None
    best_savings_rate = max([d.get("rate") or 0 for d in p.get("deposits") or []] +
                            [a.get("interest_rate") or 0 for a in p.get("accounts") or []] + [0])
    dti = round(service / income * 100, 1) if income else None
    return {
        "currency": cur,
        "loans": loans,
        "leases": [{k: ls.get(k) for k in ("name", "monthly", "remaining_installments", "total_pending", "end_date",
                                          "early_termination", "purchase_option")} for ls in leases],
        "total_debt": round(total, 2),
        "lease_outstanding": bs.get("lease_outstanding"),
        "monthly_debt_service": round(service, 2),
        "debt_to_income_pct": dti,
        "weighted_interest_rate": wrate,
        "interest_remaining_total": round(sum(ln.get("interest_remaining") or 0 for ln in loans), 2),
        "best_savings_rate": best_savings_rate,
        "liquid_cash": round((bs.get("cash") or 0) + (bs.get("deposits") or 0), 2),
        "metrics": [
            metric("Total debt", round(total, 2), cur),
            metric("Monthly repayments", round(service, 2), cur),
            metric("Debt-to-income", dti, "%"),
            metric("Average loan rate", wrate, "%"),
        ],
    }


def loan_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    if not f["loans"] and not f["leases"]:
        return insight("No loans or leases found.", "GOOD", [], [], [])
    dti, wrate = f["debt_to_income_pct"], f["weighted_interest_rate"]
    finds.append(finding("Debt overview", f"{money(f['total_debt'], cur)} outstanding; repayments of "
                         f"{money(f['monthly_debt_service'], cur)} a month ({pct(dti)} of income). "
                         f"{money(f['interest_remaining_total'], cur)} of interest is still scheduled."))
    types = [ln.get("type") for ln in f["loans"]]
    if len(types) != len(set(types)):
        gaps.append("Two loans of the same type are recorded. Confirm whether one is a second property or a duplicate.")
    if wrate is not None and wrate < 3:
        recs.append(rec("keep-low-rate-mortgage", "Keep your low-rate mortgage; don't rush to prepay",
                        f"At {pct(wrate)} the loan costs less than you can reasonably expect from a diversified portfolio "
                        f"over time, and close to what your best savings rate pays ({pct(f['best_savings_rate'])}).",
                        ["Keep paying the scheduled instalments", "Invest surplus cash instead of prepaying"],
                        "MEDIUM", "LOW", "THIS_YEAR"))
    elif wrate is not None and wrate > (f["best_savings_rate"] or 0) + 3 and f["liquid_cash"] > 0:
        part = min(f["liquid_cash"] * 0.3, f["total_debt"])
        recs.append(rec("prepay-expensive-debt", "Prepay part of your most expensive loan",
                        f"Your loans cost {pct(wrate)}, well above what your cash earns.",
                        ["Ask the lender for prepayment charges", "Prepay with cash above your emergency fund"],
                        "HIGH", "LOW", "THIS_QUARTER", part))
    for ls in f["leases"]:
        m = _months_until(ls.get("end_date"))
        if m is not None and 0 <= m <= 9:
            recs.append(rec("plan-lease-end", f"Plan for the end of your lease ({ls['end_date']})",
                            f"The lease ends in about {m} months; deciding early avoids a rushed, expensive choice.",
                            ["Compare renewing, a new lease and buying a car outright",
                             "Check the return conditions and mileage limit",
                             "Put the monthly fee you'll save (or the deposit you'll need) into your budget"],
                            "MEDIUM", "LOW", "THIS_QUARTER"))
            break
    health = "ACTION_NEEDED" if (dti or 0) > 40 else "WATCH" if (dti or 0) > 30 else "GOOD"
    summary = (f"You owe {money(f['total_debt'], cur)} at an average {pct(wrate)}; repayments take {pct(dti)} of income.")
    return insight(summary, health, finds, recs, gaps)


# ==== INVESTMENT =====================================================================================

def _employer_tokens(p: CustomerProfile) -> list[str]:
    return (p.get("equity_comp") or {}).get("employer_name_tokens") or []


def investment_facts(p: CustomerProfile) -> dict:
    bs, cur = _bs(p), p.currency
    invest = p.get("investments") or []
    by_type: dict[str, float] = {}
    positions: dict[str, dict] = {}
    for pf in invest:
        by_type[pf["type"]] = by_type.get(pf["type"], 0) + (pf["value"] or 0)
        for pos in pf["positions"]:
            key = pos.get("id") or pos.get("name")
            agg = positions.setdefault(key, {"name": pos["name"], "id": pos.get("id"), "value": 0.0, "portfolio_type": pf["type"]})
            agg["value"] += pos.get("value") or 0
    investable = sum(by_type.values())
    net = bs.get("net_worth") or 0
    top = sorted(positions.values(), key=lambda x: -x["value"])[:6]
    for t in top:
        t["value"] = round(t["value"], 2)
        t["pct_of_investments"] = round(t["value"] / investable * 100, 1) if investable else None
        t["pct_of_net_worth"] = round(t["value"] / net * 100, 1) if net > 0 else None
    single = [t for t in top if t["portfolio_type"] == "stocks" and "FONDO" not in (t["name"] or "").upper()]
    financial = (bs.get("cash") or 0) + (bs.get("deposits") or 0) + investable + (bs.get("pension") or 0)
    alloc = {"cash": bs.get("cash") or 0, "deposits": bs.get("deposits") or 0, **by_type, "pension": bs.get("pension") or 0}
    alloc_pct = {k: round(v / financial * 100, 1) for k, v in alloc.items()} if financial else {}
    risk = p.get("risk") or {}
    return {
        "currency": cur,
        "investable_assets": round(investable, 2),
        "pension_assets": bs.get("pension"),
        "allocation_pct": alloc_pct,
        "portfolios": [{k: pf.get(k) for k in ("type", "value", "contributions", "gain", "return_pct", "since")} for pf in invest],
        "top_positions": top,
        "largest_single_stock": single[0] if single else None,
        "crypto_pct_of_investments": round(by_type.get("crypto", 0) / investable * 100, 1) if investable else None,
        "cash_pct_of_financial_assets": alloc_pct.get("cash"),
        "risk_profile": risk or None,
        "age": (p.get("personal") or {}).get("age"),
        "metrics": [
            metric("Investments", round(investable, 2), cur),
            metric("Pension", bs.get("pension"), cur),
            metric("Largest stock", single[0]["pct_of_investments"] if single else None, "%"),
            metric("Cash share", alloc_pct.get("cash"), "%"),
        ],
    }


def investment_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    if not f["investable_assets"]:
        return insight("No investment accounts connected yet.", "WATCH", [], [], ["Connect your investment accounts."])
    finds.append(finding("Portfolio mix", ", ".join(f"{k} {v}%" for k, v in f["allocation_pct"].items())))
    ls = f["largest_single_stock"]
    limit = (f["risk_profile"] or {}).get("single_stock_limit_pct") or 25
    if ls and (ls["pct_of_investments"] or 0) > limit:
        excess = ls["value"] - f["investable_assets"] * limit / 100
        finds.append(finding("Heavy single-stock exposure",
                             f"{ls['name']} is {pct(ls['pct_of_investments'])} of your investments "
                             f"({pct(ls['pct_of_net_worth'])} of net worth).", "WARNING"))
        recs.append(rec("diversify-single-stock", f"Reduce your concentration in {ls['name']}",
                        f"One company is {pct(ls['pct_of_investments'])} of your investments; a bad year for it would hit "
                        f"your wealth hard. Bringing it to {limit:.0f}% means diversifying about {money(excess, cur)}.",
                        ["Sell in stages (for example a quarter at a time)", "Reinvest into broad, low-cost index funds",
                         "Coordinate the timing with the tax agent's advice"], "HIGH", "MEDIUM", "THIS_QUARTER", excess))
    if (f["crypto_pct_of_investments"] or 0) > 10:
        recs.append(rec("cap-crypto", "Cap crypto at a small share of investments",
                        f"Crypto is {pct(f['crypto_pct_of_investments'])} of investments and very volatile.",
                        ["Stop new crypto purchases until it's under 5–10%"], "MEDIUM"))
    if (f["cash_pct_of_financial_assets"] or 0) > 15:
        recs.append(rec("deploy-idle-cash", "Put idle cash to work",
                        f"Cash is {pct(f['cash_pct_of_financial_assets'])} of your financial assets, a drag on long-term returns.",
                        ["Keep 6 months of expenses in cash", "Invest the rest gradually in diversified funds"],
                        "HIGH", "LOW", "THIS_MONTH"))
    if not f["risk_profile"]:
        gaps.append("Risk profile not set; limits use defaults (single stock 25%).")
    health = "ACTION_NEEDED" if recs and recs[0]["impact"] == "HIGH" else "WATCH" if recs else "GOOD"
    summary = (f"You hold {money(f['investable_assets'], cur)} in investments plus {money(f['pension_assets'], cur)} in pensions."
               + (f" {ls['name']} makes up {pct(ls['pct_of_investments'])} of investments." if ls else ""))
    return insight(summary, health, finds, recs, gaps)


# ==== TAX ============================================================================================

def tax_facts(p: CustomerProfile) -> dict:
    cf, cur = _cf(p), p.currency
    invest = p.get("investments") or []
    gains = {}
    for pf in invest:
        gains[pf["type"]] = round(gains.get(pf["type"], 0) + (pf.get("gain") or 0), 2)
    redemptions = [a for pf in invest for a in pf.get("recent_activity") or [] if "redemption" in (a.get("type") or "")]
    deposits = p.get("deposits") or []
    return {
        "currency": cur,
        "country": (p.get("personal") or {}).get("country"),
        "net_salary_annualised": round((cf.get("monthly_salary") or 0) * 12, 2),
        "unrealised_gains_by_type": gains,
        "recent_sales": redemptions,
        "pension_gain": round(sum(pf.get("gain") or 0 for pf in p.get("pension") or []), 2),
        "pension_contributions_annualised": round((cf.get("monthly_by_category") or {}).get("PENSION_CONTRIBUTION", 0) * 12, 2),
        "deposit_interest_expected": round(sum(d.get("expected_interest_total") or 0 for d in deposits), 2),
        "deposit_withholding_rate": max([d.get("withholding_tax_rate") or 0 for d in deposits] + [0]),
        "employer_stock_value": round(sum(x.get("value") or 0 for x in (p.get("equity_comp") or {}).get("employer_stock_in_portfolio") or []), 2),
        "declared_unvested_equity": round(sum(h.get("unvested") or 0 for h in (p.get("equity_comp") or {}).get("declared_holdings") or []), 2),
        "metrics": [
            metric("Unrealised gains", round(sum(v for v in gains.values() if v > 0), 2), cur),
            metric("Unrealised losses", round(sum(v for v in gains.values() if v < 0), 2), cur),
            metric("Pension contributions / yr", round((cf.get("monthly_by_category") or {}).get("PENSION_CONTRIBUTION", 0) * 12, 2), cur),
        ],
    }


def tax_offline(f: dict) -> dict:
    cur, recs, finds = f["currency"], [], []
    losses = {k: v for k, v in f["unrealised_gains_by_type"].items() if v < 0}
    gains_total = sum(v for v in f["unrealised_gains_by_type"].values() if v > 0)
    finds.append(finding("Gains on paper", f"Unrealised gains of about {money(gains_total, cur)}"
                         + (f"; losses in {', '.join(losses)} of {money(sum(losses.values()), cur)}." if losses else ".")))
    if f["recent_sales"]:
        finds.append(finding("Recent sales", f"{len(f['recent_sales'])} fund redemption(s) this period may create a taxable gain.",
                             "WARNING"))
    if losses and gains_total > 0:
        recs.append(rec("harvest-crypto-loss" if "crypto" in losses else "harvest-losses", "Use investment losses to offset gains",
                        f"Selling positions at a loss ({money(sum(losses.values()), cur)}) can offset taxable gains, where your "
                        "tax rules allow it.", ["Check the offsetting and repurchase rules with a tax adviser",
                                               "Time the sale in the same tax year as your gains"], "MEDIUM", "LOW", "THIS_QUARTER"))
    if f["employer_stock_value"] or f["declared_unvested_equity"]:
        recs.append(rec("plan-equity-tax", "Plan the tax on selling or vesting company stock",
                        "Diversifying employer stock realises gains; spreading sales across tax years can lower the bill.",
                        ["Estimate the gain on each lot before selling", "Split sales across tax years",
                         "Set aside cash for tax due on vests"], "MEDIUM", "MEDIUM", "THIS_QUARTER"))
    if f["pension_contributions_annualised"]:
        recs.append(rec("check-pension-allowance", "Check you're using your pension tax allowance",
                        f"You contribute about {money(f['pension_contributions_annualised'], cur)} a year; contributions are "
                        "often tax-deductible up to a yearly limit.", ["Confirm your yearly limit and top up before year end"],
                        "LOW", "LOW", "THIS_YEAR"))
    gaps = ["Gross salary, tax regime and deductions are unknown, so tax estimates are indicative only.",
            "Cost basis of each holding is unknown; realised-gain estimates need purchase prices."]
    country = f["country"] or "your country"
    summary = f"Tax picture for {country}: about {money(gains_total, cur)} of unrealised gains to manage when you sell."
    return insight(summary, "WATCH", finds, recs, gaps)


# ==== INSURANCE ======================================================================================

def insurance_facts(p: CustomerProfile) -> dict:
    cf, bs, cur = _cf(p), _bs(p), p.currency
    ins = p.get("insurance") or {}
    personal = p.get("personal") or {}
    texts = " ".join((x.get("description") or "").upper() for x in ins.get("detected_payments") or []) + " " + str(ins.get("from_forms")).upper()
    annual_income = round(_income(cf) * 12, 2)
    debt = bs.get("loans") or 0
    return {
        "currency": cur,
        "age": personal.get("age"),
        "marital_status": personal.get("marital_status"),
        "dependents": personal.get("dependents"),
        "detected_policies": ins.get("detected_payments") or [],
        "lease_includes_insurance": ins.get("lease_includes_insurance"),
        "has_life_cover": "VIDA" in texts or "LIFE" in texts,
        "has_health_cover": any(w in texts for w in ("SALUD", "HEALTH", "SANITAS", "ADESLAS", "DKV")),
        "has_home_cover": "HOGAR" in texts or "HOME" in texts,
        "has_car_cover": "AUTOMOVIL" in texts or "AUTO" in texts,
        "declared_cover": ins.get("declared_cover"),
        "annual_income": annual_income,
        "mortgage_debt": debt,
        "suggested_life_cover": round(debt + 5 * annual_income, 2),
        "metrics": [
            metric("Policies detected", len(ins.get("detected_payments") or [])),
            metric("Mortgage debt", debt, cur),
            metric("Suggested life cover", round(debt + 5 * annual_income, 2), cur),
        ],
    }


def insurance_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    family = f["marital_status"] == "married" or (f["dependents"] or 0) > 0
    if not f["has_life_cover"] and (family or f["mortgage_debt"]):
        recs.append(rec("get-term-life", "Get term life cover",
                        f"No life cover was found, but you have {money(f['mortgage_debt'], cur)} of mortgage debt"
                        + (" and a family" if family else "") + ". A rule of thumb is debt plus 5 years of income: about "
                        f"{money(f['suggested_life_cover'], cur)}.",
                        ["Get quotes for term life insurance", "Check any cover your employer already provides",
                         "Name your spouse as beneficiary"], "HIGH", "LOW", "THIS_MONTH", f["suggested_life_cover"]))
    if f["has_car_cover"] and f["lease_includes_insurance"]:
        premium = sum(x.get("amount") or 0 for x in f["detected_policies"] if "AUTO" in (x.get("description") or "").upper())
        finds.append(finding("Possible double car insurance",
                             "Your car lease includes insurance, and you also pay a separate car policy.", "WARNING"))
        recs.append(rec("check-double-car-insurance", "Check if you're paying for car insurance twice",
                        f"The lease already includes insurance; the separate policy costs about {money(premium, cur)}.",
                        ["Compare both policies' cover", "Cancel the one you don't need at renewal"], "MEDIUM", "LOW",
                        "THIS_MONTH", premium))
    if f["mortgage_debt"] and not f["has_home_cover"]:
        recs.append(rec("confirm-home-insurance", "Confirm your home insurance",
                        "No home insurance payment was found; mortgages usually require it and it protects your biggest asset.",
                        ["Check if it's paid from another account or bundled with the mortgage"], "MEDIUM"))
    if not f["has_health_cover"]:
        recs.append(rec("review-health-cover", "Review your health cover",
                        "No health insurance payment was found.", ["Check employer health benefits",
                                                                    "Compare a family health policy"], "LOW"))
    gaps.append("Policies paid from accounts that aren't connected, or provided by your employer, aren't visible.")
    health = "ACTION_NEEDED" if any(r["key"] == "get-term-life" for r in recs) else "WATCH" if recs else "GOOD"
    summary = (f"{len(f['detected_policies'])} insurance payment(s) found. "
               + ("No life cover is visible for a family with a mortgage." if not f["has_life_cover"] else ""))
    return insight(summary.strip(), health, finds, recs, gaps)


# ==== RSU / EMPLOYER EQUITY ==========================================================================

def rsu_facts(p: CustomerProfile) -> dict:
    eq, bs, cf, cur = p.get("equity_comp") or {}, _bs(p), _cf(p), p.currency
    detected: dict[str, dict] = {}
    for x in eq.get("employer_stock_in_portfolio") or []:
        d = detected.setdefault(x.get("id") or x["name"], {"name": x["name"], "id": x.get("id"), "value": 0.0, "currency": x.get("currency")})
        d["value"] = round(d["value"] + (x.get("value") or 0), 2)
    declared = eq.get("declared_holdings") or []
    value = sum(d["value"] for d in detected.values()) + sum(h.get("vested") or 0 for h in declared)
    net = bs.get("net_worth") or 0
    investable = bs.get("investments") or 0
    limit = ((p.get("risk") or {}).get("single_stock_limit_pct")) or 10
    next_vests = sorted(h["next_vest_date"] for h in declared if h.get("next_vest_date"))
    return {
        "currency": cur,
        "declared_holdings": declared,
        "detected_employer_stock": list(detected.values()),
        "employer_name_hints": eq.get("employer_name_tokens") or [],
        "salary_payers": cf.get("salary_payers") or [],
        "employer_stock_value": round(value, 2),
        "unvested_value": round(sum(h.get("unvested") or 0 for h in declared), 2),
        "next_vest_date": next_vests[0] if next_vests else None,
        "pct_of_net_worth": round(value / net * 100, 1) if net > 0 else None,
        "pct_of_investments": round(value / investable * 100, 1) if investable else None,
        "single_stock_limit_pct": limit,
        "net_worth": net,
        "metrics": [
            metric("Employer stock", round(value, 2), cur),
            metric("Share of net worth", round(value / net * 100, 1) if net > 0 else None, "%"),
            metric("Unvested", round(sum(h.get("unvested") or 0 for h in declared), 2), cur),
        ],
    }


def rsu_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    if not f["employer_stock_value"] and not f["unvested_value"]:
        return insight("No employer stock found.", "GOOD", [], [], ["Add any RSUs or ESOPs on the equity screen."])
    names = ", ".join(d["name"] for d in f["detected_employer_stock"]) or ", ".join(h["security"] for h in f["declared_holdings"])
    finds.append(finding("Employer stock exposure", f"{names}: {money(f['employer_stock_value'], cur)}, "
                         f"{pct(f['pct_of_net_worth'])} of net worth and {pct(f['pct_of_investments'])} of investments."))
    if f["detected_employer_stock"] and f["salary_payers"]:
        finds.append(finding("Income and wealth tied to one employer",
                             "Your salary and a large holding depend on the same company group; a bad year could hit both.",
                             "WARNING"))
    if (f["pct_of_net_worth"] or 0) > f["single_stock_limit_pct"]:
        target = f["net_worth"] * f["single_stock_limit_pct"] / 100
        excess = f["employer_stock_value"] - target
        recs.append(rec("diversify-single-stock", "Diversify your employer stock in stages",
                        f"Employer stock is {pct(f['pct_of_net_worth'])} of net worth, above {f['single_stock_limit_pct']:.0f}%. "
                        f"Selling about {money(excess, cur)} over the next year brings it in line.",
                        ["Sell a quarter of the excess each quarter", "Reinvest in diversified index funds",
                         "Plan the tax with the tax agent first"], "HIGH", "MEDIUM", "THIS_QUARTER", excess))
    if f["unvested_value"]:
        recs.append(rec("plan-equity-tax", "Set aside cash for tax on upcoming vests",
                        f"{money(f['unvested_value'], cur)} is still to vest; vests are usually taxed as income.",
                        ["Estimate the tax on the next vest", "Keep that amount in cash until the tax is paid"],
                        "MEDIUM", "LOW", "THIS_QUARTER"))
    if f["detected_employer_stock"] and not f["declared_holdings"]:
        gaps.append("This holding was matched to your employer by name. Confirm it, and add any unvested RSUs on the equity screen.")
    health = "ACTION_NEEDED" if recs and recs[0]["impact"] == "HIGH" else "WATCH"
    return insight(f"Employer stock is {pct(f['pct_of_net_worth'])} of your net worth.", health, finds, recs, gaps)


# ==== ESTATE =========================================================================================

def estate_facts(p: CustomerProfile) -> dict:
    personal, bs, cur = p.get("personal") or {}, _bs(p), p.currency
    estate = (p.get("extra") or {}).get("ESTATE") or []
    flags = {k: v for e in estate for k, v in e.items()}
    return {
        "currency": cur,
        "age": personal.get("age"),
        "marital_status": personal.get("marital_status"),
        "dependents": personal.get("dependents"),
        "net_worth": bs.get("net_worth"),
        "property_value": bs.get("property"),
        "pension_value": bs.get("pension"),
        "investments": bs.get("investments"),
        "debts": bs.get("total_liabilities"),
        "has_will": flags.get("has_will"),
        "pension_beneficiaries_named": flags.get("pension_beneficiaries_named"),
        "has_power_of_attorney": flags.get("has_power_of_attorney"),
        "metrics": [
            metric("Net worth", bs.get("net_worth"), cur),
            metric("Home value", bs.get("property"), cur),
            metric("Pension", bs.get("pension"), cur),
        ],
    }


def estate_offline(f: dict) -> dict:
    cur, recs, gaps = f["currency"], [], []
    family = f["marital_status"] == "married" or (f["dependents"] or 0) > 0
    if not f["has_will"]:
        recs.append(rec("make-will", "Make or update your will",
                        f"You have a net worth of {money(f['net_worth'], cur)}, including your home"
                        + (" and a family to protect" if family else "") + ". Without a will, local law decides who inherits.",
                        ["List your assets and who should receive them", "Write the will with a notary or lawyer",
                         "Review it every few years or after big life events"], "HIGH" if family else "MEDIUM", "MEDIUM",
                        "THIS_QUARTER"))
    if f["pension_value"] and not f["pension_beneficiaries_named"]:
        recs.append(rec("name-pension-beneficiaries", "Name beneficiaries on your pension plans",
                        f"Your pension plans hold {money(f['pension_value'], cur)}; named beneficiaries usually avoid delays.",
                        ["Ask your pension provider for the beneficiary form"], "MEDIUM", "LOW", "THIS_MONTH"))
    if not f["has_power_of_attorney"]:
        recs.append(rec("power-of-attorney", "Set up a power of attorney",
                        "It lets someone you trust manage your finances if you can't.", ["Arrange it with a notary"],
                        "LOW", "MEDIUM", "THIS_YEAR"))
    if f["has_will"] is None:
        gaps.append("Will, beneficiaries and power of attorney aren't known yet; add them through the profile forms.")
    return insight(f"Estate of about {money(f['net_worth'], cur)} including your home; key documents are not confirmed yet.",
                   "WATCH" if recs else "GOOD", [], recs, gaps)


# ==== GOAL ===========================================================================================

def goal_facts(p: CustomerProfile) -> dict:
    cf, bs, cur = _cf(p), _bs(p), p.currency
    goals = []
    for g in p.get("goals") or []:
        months = _months_until(g.get("target_date"))
        remaining = max(0.0, (g.get("target") or 0) - (g.get("saved") or 0))
        goals.append({**g, "remaining": round(remaining, 2), "months_left": months,
                      "monthly_needed": round(remaining / months, 2) if months and months > 0 else None})
    annual_spend = (cf.get("monthly_spend") or 0) * 12
    retirement_assets = (bs.get("investments") or 0) + (bs.get("pension") or 0)
    surplus = _income(cf) - (cf.get("monthly_spend") or 0)
    age = (p.get("personal") or {}).get("age")
    return {
        "currency": cur,
        "goals": goals,
        "monthly_surplus": round(surplus, 2),
        "monthly_already_saving": cf.get("monthly_saving_investing"),
        "retirement_target_25x_spend": round(annual_spend * 25, 2),
        "retirement_assets": round(retirement_assets, 2),
        "retirement_progress_pct": round(retirement_assets / (annual_spend * 25) * 100, 1) if annual_spend else None,
        "years_to_65": (65 - age) if age else None,
        "metrics": [
            metric("Goals", len(goals)),
            metric("Monthly surplus", round(surplus, 2), cur),
            metric("Retirement progress", round(retirement_assets / (annual_spend * 25) * 100, 1) if annual_spend else None, "%"),
        ],
    }


def goal_offline(f: dict) -> dict:
    cur, recs, finds, gaps = f["currency"], [], [], []
    if not f["goals"]:
        recs.append(rec("set-goals", "Set your financial goals",
                        "Clear goals turn your monthly surplus of "
                        f"{money(f['monthly_surplus'], cur)} into a plan.", ["Pick your goals on the goals screen"],
                        "MEDIUM", "LOW", "THIS_MONTH"))
    for g in f["goals"]:
        if g["monthly_needed"] and g["monthly_needed"] > max(f["monthly_surplus"], 0):
            recs.append(rec(f"fund-goal-{g['type'].lower().replace('_', '-')}", f"Increase saving for '{g['name']}'",
                            f"It needs {money(g['monthly_needed'], cur)} a month to hit the date, more than your surplus.",
                            ["Move the target date, lower the target, or cut other spending"], "MEDIUM", "MEDIUM"))
    rp = f["retirement_progress_pct"]
    if rp is not None:
        finds.append(finding("Retirement check", f"Investments and pensions of {money(f['retirement_assets'], cur)} are {pct(rp)} "
                             f"of a 25× spending target ({money(f['retirement_target_25x_spend'], cur)})"
                             + (f", with {f['years_to_65']} years to 65." if f["years_to_65"] else ".")))
    health = "GOOD" if f["goals"] and not recs else "WATCH"
    return insight(f"{len(f['goals'])} goal(s) set; you have {money(f['monthly_surplus'], cur)} a month left after spending.",
                   health, finds, recs, gaps)


# ==== registry =======================================================================================

@dataclass(frozen=True)
class AgentSpec:
    key: AgentKey
    name: str
    description: str
    focus: str
    facts: Callable[[CustomerProfile], dict]
    offline: Callable[[dict], dict]
    version: int = 1  # bump to force regeneration after changing an agent's logic or prompt


AGENTS: list[AgentSpec] = [
    AgentSpec(AgentKey.BUDGET, "Budget Agent", "Income, spending, savings rate and emergency fund",
              "cash flow, spending categories, savings rate, emergency fund size, idle cash, recurring bills",
              budget_facts, budget_offline),
    AgentSpec(AgentKey.LOAN, "Loan Agent", "Mortgages, leases, repayments and debt strategy",
              "debt burden, interest cost, prepay-vs-invest, lease ends, refinancing", loan_facts, loan_offline),
    AgentSpec(AgentKey.INVESTMENT, "Investment Agent", "Portfolio mix, concentration, returns and cash drag",
              "asset allocation vs risk profile and age, concentration, crypto share, cash drag, fees",
              investment_facts, investment_offline),
    AgentSpec(AgentKey.TAX, "Tax Agent", "Gains, losses, interest, pension and equity tax",
              "tax on gains and interest, loss offsetting, pension allowances, timing of sales; say rules depend on the "
              "jurisdiction and must be confirmed", tax_facts, tax_offline),
    AgentSpec(AgentKey.INSURANCE, "Insurance Agent", "Life, health, home and car cover gaps",
              "cover gaps for the family and the mortgage, duplicate cover, cost", insurance_facts, insurance_offline),
    AgentSpec(AgentKey.RSU, "RSU Agent", "Employer stock, vesting and concentration",
              "employer-stock concentration, income-and-wealth correlation, diversification schedule, vest tax",
              rsu_facts, rsu_offline),
    AgentSpec(AgentKey.ESTATE, "Estate Agent", "Will, beneficiaries and protecting the family",
              "will, beneficiaries, power of attorney, how assets pass to the family", estate_facts, estate_offline),
    AgentSpec(AgentKey.GOAL, "Goal Agent", "Goals, monthly surplus and retirement progress",
              "goal funding, trade-offs between goals, retirement readiness", goal_facts, goal_offline),
]
AGENTS_BY_KEY = {a.key: a for a in AGENTS}
