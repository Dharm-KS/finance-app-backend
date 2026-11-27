"""Customer Financial Profile: one merged, PII-free view of everything we know about a customer.

Sources: third-party aggregator data (current rows of every active connection), the onboarding
answers (money, equity, risk, goals, preferences) and extra data from other forms. Agents read
only this profile - never names, IDs, account numbers, addresses or contact details.

All amounts are rounded floats in the reporting currency (INR): each is converted from its own
currency (see ``fx``). Rates and percentages are not converted.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.time import utctoday
from app.models.advisor import CustomerExtraData
from app.models.aggregator import (
    AggAccount,
    AggCard,
    AggCustomerInfo,
    AggDeposit,
    AggLease,
    AggLoan,
    AggPortfolio,
    AggProperty,
    AggReceipt,
    AggregatorConnection,
)
from app.models.enums import AggregatorConnectionStatus
from app.models.equity import EquityHolding
from app.models.financial_profile import FinancialProfile
from app.models.goal import FinancialGoal
from app.models.preferences import UserPreferences
from app.models.risk_profile import RiskProfile
from app.models.user import User
from app.services.fx import convert as cv
from app.services.fx import get_fx_provider, rates_used, reporting_currency


def r2(v: Any) -> float | None:
    if v is None:
        return None
    return round(float(v), 2)


# ---- transaction categorisation ------------------------------------------------------------------

# Order matters: first match wins. Keywords are matched on the upper-cased description.
OUTFLOW_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("SAVINGS_TRANSFER", ("CUENTA AHORRO",)),
    ("TRANSFER_OUT", ("TRASPASO EMITIDO", "TRANSF. A ", "NOMINA")),
    ("PENSION_CONTRIBUTION", ("PLAN PENSIONES", "PLAN DE PENSIONES")),
    ("FUND_INVESTMENT", ("FONDO DE INVERSION", "APORTACION FONDO")),
    ("CRYPTO", ("CRIPTO",)),
    ("STOCKS", ("BOLSA", "VALORES")),
    ("HOUSING_LOAN", ("PRESTAMO", "HIPOTEC")),
    ("VEHICLE_LEASE", ("RENTING",)),
    ("INSURANCE", ("SEGURO", "GENERALI", "MAPFRE", "ALLIANZ", "SANITAS", "AXA ")),
    ("UTILITIES", ("ENDESA", "NATURGY", "EMASESA", "IBERDROLA", "AGUA", "GAS ")),
    ("TELECOM", ("MOVISTAR", "ORANGE", "DIGI", "VODAFONE")),
    ("GROCERIES", ("MERCADONA", "SUPERMERC", "CARREFOUR", "LIDL", "COSTTO", "HORTICOLA", "ALIMEN", "DIA ")),
    ("BUY_NOW_PAY_LATER", ("PLAZOS",)),
    ("CREDIT_CARD_BILL", ("LIQUIDACION TARJ",)),
    ("CASH_WITHDRAWAL", ("CAJERO", "REINTEGRO", "RETIRADA", "DISPOSICION EFECTIVO")),
    ("SHOPPING", ("AMAZON", "TEMU", "CORTE INGLES", "PAYPAL")),
    ("FITNESS", ("GIMNASIO", "ALTAFIT", "FITMACHINE")),
    ("EATING_OUT", ("BAR ", "GELATO", "PANISHOP", "RESTAUR", "CAFE")),
    ("TRANSPORT", ("BOLT", "UBER", "CABIFY", "MOEVE", "REPSOL", "GASOLIN")),
    ("BANK_FEES", ("COMISION",)),
]
INFLOW_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("SALARY", ("NOMINA",)),
    ("INTEREST", ("INTERESES",)),
    ("INVESTMENT_REDEMPTION", ("REEMBOLSO",)),
    ("INTERNAL_TRANSFER", ("TRASPASO DESDE CUENTA", "CUENTA AHORRO")),
]
ESSENTIAL = {"HOUSING_LOAN", "VEHICLE_LEASE", "INSURANCE", "UTILITIES", "TELECOM", "GROCERIES"}
SAVING_INVESTING = {"SAVINGS_TRANSFER", "PENSION_CONTRIBUTION", "FUND_INVESTMENT", "CRYPTO", "STOCKS"}
# Outflows that are money moved elsewhere, not consumption.
NOT_SPEND = SAVING_INVESTING | {"TRANSFER_OUT"}
# Inflows that are not income (money moving between the customer's own accounts / investments).
NOT_INCOME = {"INTERNAL_TRANSFER", "INVESTMENT_REDEMPTION"}


def categorize(description: str | None, amount: float) -> str:
    text = f" {(description or '').upper()} "
    rules = INFLOW_RULES if amount > 0 else OUTFLOW_RULES
    for category, words in rules:
        if any(w in text for w in words):
            return category
    return "OTHER_INFLOW" if amount > 0 else "OTHER_SPEND"


_GENERIC_TOKENS = {"SA", "SL", "SAU", "INC", "LTD", "NOMINA", "ABONO", "REF", "FONDO", "THE", "AND", "GROUP"}


def _employer_tokens(salary_descriptions: list[str]) -> set[str]:
    tokens: Counter[str] = Counter()
    for d in salary_descriptions:
        for t in re.findall(r"[A-Z]{4,}", d.upper()):
            if t not in _GENERIC_TOKENS and not t.isdigit():
                tokens[t] += 1
    # tokens that appear on most salary credits identify the employer group
    need = max(1, len(salary_descriptions) // 2)
    return {t for t, n in tokens.items() if n >= need}


# ---- profile -------------------------------------------------------------------------------------

@dataclass
class CustomerProfile:
    currency: str
    domains: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.domains.get(name, default)


def _age(born: date | None) -> int | None:
    if not born:
        return None
    t = utctoday()
    return t.year - born.year - ((t.month, t.day) < (born.month, born.day))


async def build_profile(db: AsyncSession, user: User) -> CustomerProfile:
    uid = user.id
    active = select(AggregatorConnection.id).where(
        AggregatorConnection.user_id == uid, AggregatorConnection.status == AggregatorConnectionStatus.ACTIVE
    )

    async def rows(model, *options):
        stmt = select(model).where(model.user_id == uid, model.connection_id.in_(active)).order_by(model.id)
        for o in options:
            stmt = stmt.options(o)
        return list((await db.execute(stmt)).scalars())

    infos = await rows(AggCustomerInfo)
    accounts = await rows(AggAccount, selectinload(AggAccount.transactions))
    portfolios = await rows(AggPortfolio, selectinload(AggPortfolio.positions), selectinload(AggPortfolio.transactions))
    cards = await rows(AggCard)
    loans = await rows(AggLoan, selectinload(AggLoan.installments))
    properties = await rows(AggProperty)
    receipts = await rows(AggReceipt)
    leases = await rows(AggLease)
    deposits = await rows(AggDeposit)

    fin = (await db.execute(select(FinancialProfile).where(FinancialProfile.user_id == uid))).scalar_one_or_none()
    risk = (await db.execute(select(RiskProfile).where(RiskProfile.user_id == uid))).scalar_one_or_none()
    prefs = (await db.execute(select(UserPreferences).where(UserPreferences.user_id == uid))).scalar_one_or_none()
    equity = list((await db.execute(select(EquityHolding).where(EquityHolding.user_id == uid))).scalars())
    goals = list((await db.execute(select(FinancialGoal).where(FinancialGoal.user_id == uid))).scalars())
    extra = list((await db.execute(select(CustomerExtraData).where(CustomerExtraData.user_id == uid))).scalars())

    # Everything is shown in the reporting currency (INR); each amount is converted from its own
    # currency. Stored provider data keeps its original currency.
    currency = reporting_currency()
    seen = {a.currency for a in accounts} | {p.currency for p in portfolios} | {ln.currency for ln in loans} | \
        {dp.currency for dp in deposits} | {pr.currency for pr in properties} | {ls.currency for ls in leases}
    if fin:
        seen.add(fin.currency.value)
    seen |= {h.currency.value for h in equity}
    d: dict[str, Any] = {"currency": currency, "fx": {"rates_used": rates_used(seen), "source": get_fx_provider().source}}

    # personal (no identifiers)
    info = infos[-1] if infos else None
    d["personal"] = {
        "age": _age(info.birth_date) if info else (fin.age if fin else None),
        "marital_status": info.marital_status if info else None,
        "occupation": info.job if info else None,
        "country": info.country if info else None,
        "dependents": fin.dependents if fin else None,
        "employment_type": fin.employment_type.value if fin and fin.employment_type else None,
    }

    # accounts & cash
    d["accounts"] = [
        {"type": a.subtype, "balance": cv(a.balance_current, a.currency), "interest_rate": r2(a.interest_rate),
         "original_currency": a.currency}
        for a in accounts
    ]
    cash = sum(cv(a.balance_current, a.currency) or 0 for a in accounts)

    # cash flow from account transactions (card transactions mirror the linked account, so skipped)
    txs = [(t, cv(t.amount, a.currency) or 0.0) for a in accounts for t in a.transactions if t.value_date]
    d["cashflow"] = _cashflow(txs)

    # deposits
    d["deposits"] = [
        {
            "principal": cv(dp.pending_principal or dp.principal, dp.currency), "rate": r2(dp.nominal_interest_rate),
            "maturity_date": dp.maturity_date.isoformat() if dp.maturity_date else None,
            "auto_renewal": bool((dp.auto_renewal or {}).get("enabled")),
            "accrued_interest": cv(dp.accrued_interest, dp.currency), "withholding_tax_rate": r2(dp.withholding_tax_rate),
            "expected_interest_total": cv(dp.expected_interest_total, dp.currency),
        }
        for dp in deposits
    ]
    deposits_total = sum(cv(dp.pending_principal or dp.principal, dp.currency) or 0 for dp in deposits)

    # investments (pension plans kept separate: long-term and illiquid). Position values are in the
    # portfolio's currency (the provider gives them in its reference currency).
    def pf_view(p: AggPortfolio) -> dict:
        c = p.currency
        return {
            "type": p.subtype, "value": cv(p.total_value, c), "contributions": cv(p.contributions, c),
            "gain": cv(p.yield_amount, c), "return_pct": r2(p.weighted_return), "since": p.contracting_date.isoformat()
            if p.contracting_date else None, "original_currency": c,
            "positions": [
                {"name": pos.description, "id": pos.instrument_id, "value": cv(pos.total_amount, c),
                 "weight_pct": r2(pos.weighting), "listing_currency": pos.currency}
                for pos in sorted(p.positions, key=lambda x: -(x.total_amount or 0))
            ],
            "recent_activity": [
                {"date": t.operation_date.isoformat() if t.operation_date else None, "type": t.operation_type,
                 "amount": cv(t.total_amount, c), "instrument": t.instrument_id}
                for t in p.transactions
            ],
        }

    d["investments"] = [pf_view(p) for p in portfolios if p.subtype != "pension-plans"]
    d["pension"] = [pf_view(p) for p in portfolios if p.subtype == "pension-plans"]
    invest_total = sum(cv(p.total_value, p.currency) or 0 for p in portfolios if p.subtype != "pension-plans")
    pension_total = sum(cv(p.total_value, p.currency) or 0 for p in portfolios if p.subtype == "pension-plans")

    # loans
    today = utctoday()
    d["loans"] = []
    for ln in loans:
        scheduled = [i for i in ln.installments if i.operation_type == "receipt_scheduled"]
        c = ln.currency
        d["loans"].append({
            "type": ln.loan_type, "pending": cv(ln.pending_amount, c), "granted": cv(ln.granted_capital, c),
            "rate": r2(ln.interest_rate), "monthly_installment": cv(ln.next_installment, c),
            "remaining_installments": ln.pending_receipts,
            "end_date": ln.expiration_date.isoformat() if ln.expiration_date else None,
            "interest_remaining": cv(sum(float(i.interest or 0) for i in scheduled), c),
        })
    loans_total = sum(cv(ln.pending_amount, ln.currency) or 0 for ln in loans)

    # leases
    d["leases"] = []
    lease_outstanding = 0.0
    for ls in leases:
        fin_ = ls.financials or {}
        tot = ls.totals or {}
        lease_outstanding += cv(tot.get("principal_outstanding") or 0, ls.currency) or 0
        d["leases"].append({
            "name": ls.name, "asset": (ls.asset or {}).get("description"), "monthly": cv(fin_.get("initial_fee"), ls.currency),
            "remaining_installments": tot.get("remaining_installments"),
            "total_pending": cv(tot.get("total_pending"), ls.currency),
            "end_date": ls.end_date.isoformat() if ls.end_date else None, "status": ls.status,
            "services_included": fin_.get("services_included") or {},
            "early_termination": fin_.get("early_termination") or {}, "purchase_option": fin_.get("purchase_option"),
        })

    d["cards"] = [
        {"type": c.subtype, "status": c.status, "spent_this_period": cv(c.balance_disposed, c.currency),
         "limit": cv(c.balance_limit, c.currency)}
        for c in cards
    ]

    # properties: the same home can come from two institutions -> merge by description, keep latest value
    by_desc: dict[str, AggProperty] = {}
    for pr in properties:
        key = (pr.description or pr.external_uuid).strip().upper()
        prev = by_desc.get(key)
        if prev is None or (pr.trading_year or 0, pr.id) > (prev.trading_year or 0, prev.id):
            by_desc[key] = pr
    d["properties"] = []
    for pr in by_desc.values():
        hist = pr.historic_prices or []
        ten_years = next((h["price"] for h in hist if str(h.get("date", "")).startswith(str((pr.trading_year or today.year) - 10))), None)
        d["properties"].append({
            "description": pr.purpose, "value": cv(pr.trading_price, pr.currency), "value_year": pr.trading_year,
            "value_10y_ago": cv(ten_years, pr.currency),
        })
    d["properties_merged"] = len(properties) - len(by_desc)
    property_total = sum(cv(pr.trading_price, pr.currency) or 0 for pr in by_desc.values())

    # receipts carry no currency; they are debits on the customer's accounts
    acc_currency = accounts[0].currency if accounts else currency
    d["recurring_bills"] = [
        {"issuer": r.issuer, "description": r.description, "amount": cv(r.amount, acc_currency),
         "last_date": r.last_receipt_date.isoformat() if r.last_receipt_date else None}
        for r in receipts
    ]

    # insurance detected from payments + lease services + forms
    detected = []
    for t, amount in txs:
        if categorize(t.description, amount) == "INSURANCE":
            detected.append({"description": t.description, "amount": round(-amount, 2), "date": t.value_date.isoformat()})
    d["insurance"] = {
        "detected_payments": detected,
        "lease_includes_insurance": any((ls.financials or {}).get("services_included", {}).get("insurance") for ls in leases),
        "declared_cover": cv(fin.insurance_cover, fin.currency.value) if fin and fin.insurance_cover is not None else None,
        "from_forms": [e.data for e in extra if e.category == "INSURANCE"],
    }

    # employer equity: onboarding entries + stock positions that look like the employer's stock
    salary_desc = [t.description or "" for t, amount in txs if categorize(t.description, amount) == "SALARY"]
    employer_tokens = _employer_tokens(salary_desc)
    suspected = []
    for p in portfolios:
        if p.subtype != "stocks":
            continue
        for pos in p.positions:
            name = (pos.description or "").upper()
            if employer_tokens and any(tok in name for tok in employer_tokens):
                suspected.append({"name": pos.description, "id": pos.instrument_id, "value": cv(pos.total_amount, p.currency),
                                  "weight_in_portfolio_pct": r2(pos.weighting)})
    d["equity_comp"] = {
        "declared_holdings": [
            {"employer": h.employer_name, "security": h.security_name, "ticker": h.ticker,
             "vested": cv(h.vested_value, h.currency.value), "unvested": cv(h.unvested_value, h.currency.value),
             "next_vest_date": h.next_vest_date.isoformat() if h.next_vest_date else None}
            for h in equity
        ],
        "employer_stock_in_portfolio": suspected,
        "employer_name_tokens": sorted(employer_tokens),
    }

    # goals are sized from the onboarding answers, in the onboarding currency
    goal_cur = fin.currency.value if fin else currency
    d["goals"] = [
        {"type": g.goal_type.value, "name": g.name, "target": cv(g.target_amount, goal_cur),
         "saved": cv(g.current_amount, goal_cur),
         "target_date": g.target_date.isoformat() if g.target_date else None, "status": g.status.value,
         "priority": g.priority.value}
        for g in goals
    ]
    d["risk"] = {
        "tolerance": risk.risk_tolerance.value, "max_drawdown_pct": r2(risk.max_drawdown_percent),
        "single_stock_limit_pct": r2(risk.single_stock_limit_percent), "horizon_years": risk.planning_horizon_years,
    } if risk else None
    self_rep = {
        "annual_income": cv(fin.annual_income, fin.currency.value), "monthly_spend": cv(fin.monthly_spend, fin.currency.value),
        "cash_reserve": cv(fin.cash_reserve, fin.currency.value), "monthly_emi": cv(fin.monthly_emi, fin.currency.value),
        "total_debt": cv(fin.total_debt, fin.currency.value), "investments": cv(fin.investments, fin.currency.value),
    } if fin else None
    d["self_reported"] = self_rep

    # Bank data is measured, so it wins where it exists; the Money screen's answers fill whatever the
    # bank data doesn't cover (or everything, when the customer skipped connecting a bank).
    filled: list[str] = []
    if self_rep:
        if not d["cashflow"].get("months_covered") and (self_rep["annual_income"] or self_rep["monthly_spend"]):
            income, spend = (self_rep["annual_income"] or 0) / 12, self_rep["monthly_spend"] or 0
            emi = self_rep["monthly_emi"] or 0
            d["cashflow"] = {
                "source": "MONEY_SCREEN", "months_covered": 0,
                "monthly_salary": r2(income), "monthly_other_income": 0.0,
                "monthly_spend": r2(spend + emi),
                "monthly_essential_spend": r2(spend + emi),  # no breakdown: treat it all as essential (conservative)
                "monthly_discretionary_spend": None, "monthly_saving_investing": None, "monthly_transfers_out": None,
                "savings_rate_pct": round((income - spend - emi) / income * 100, 1) if income else None,
                "monthly_by_category": {"LOAN_PAYMENT": r2(emi)} if emi else {}, "salary_payers": [],
            }
            filled.append("cashflow")
        if not accounts and self_rep["cash_reserve"]:
            cash = self_rep["cash_reserve"]
            filled.append("cash")
        if not d["investments"] and self_rep["investments"]:
            invest_total = self_rep["investments"]
            filled.append("investments")
        if not loans and self_rep["total_debt"]:
            loans_total = self_rep["total_debt"]
            filled.append("loans")
    d["preferences"] = {
        "tone": prefs.insight_tone.value, "vesting_alerts": prefs.vesting_alerts,
        "tax_deadline_alerts": prefs.tax_deadline_alerts,
    } if prefs else None
    d["extra"] = {}
    for e in extra:
        d["extra"].setdefault(e.category, []).append(e.data)

    # balance sheet
    vested_declared = sum(cv(h.vested_value, h.currency.value) or 0 for h in equity)
    assets = cash + deposits_total + invest_total + pension_total + property_total + vested_declared
    liabilities = loans_total + lease_outstanding
    d["balance_sheet"] = {
        "cash": r2(cash), "deposits": r2(deposits_total), "investments": r2(invest_total), "pension": r2(pension_total),
        "property": r2(property_total), "declared_employer_equity": r2(vested_declared),
        "total_assets": r2(assets), "loans": r2(loans_total), "lease_outstanding": r2(lease_outstanding),
        "total_liabilities": r2(liabilities), "net_worth": r2(assets - liabilities),
        "liquid_net_worth": r2(cash + deposits_total + invest_total - liabilities),
    }
    d["data_sources"] = {
        "aggregator_connected": bool(infos or accounts or portfolios),
        "onboarding_profile": fin is not None,
        "filled_from_money_screen": filled,
        "extra_categories": sorted(d["extra"]),
    }
    return CustomerProfile(currency=currency, domains=d)


def _cashflow(txs: list[tuple[Any, float]]) -> dict:
    """``txs``: (transaction, amount already converted to the reporting currency)."""
    if not txs:
        return {"months_covered": 0}
    start = min(t.value_date for t, _ in txs)
    end = max(t.value_date for t, _ in txs)
    months = max(1.0, round(((end - start).days + 1) / 30.44, 1))
    by_cat: dict[str, float] = {}
    salary_payers: set[str] = set()
    for t, amt in txs:
        cat = categorize(t.description, amt)
        by_cat[cat] = by_cat.get(cat, 0.0) + amt
        if cat == "SALARY":
            salary_payers.add(re.sub(r"\b(NOMINA|ABONO|REF)\b|\d+", "", (t.description or "").upper()).strip(" |"))

    def monthly(cats) -> float:
        return round(abs(sum(v for c, v in by_cat.items() if c in cats)) / months, 2)

    spend_cats = {c for c, v in by_cat.items() if v < 0 and c not in NOT_SPEND}
    income = monthly({"SALARY"})
    other_income = monthly({c for c, v in by_cat.items() if v > 0 and c not in NOT_INCOME and c != "SALARY"})
    saving = monthly(SAVING_INVESTING)
    spend = monthly(spend_cats)
    total_income = income + other_income
    return {
        "period_start": start.isoformat(), "period_end": end.isoformat(), "months_covered": months,
        "monthly_salary": income, "monthly_other_income": other_income,
        "monthly_spend": spend, "monthly_essential_spend": monthly(ESSENTIAL & spend_cats),
        "monthly_discretionary_spend": monthly(spend_cats - ESSENTIAL),
        "monthly_saving_investing": saving,
        "monthly_transfers_out": monthly({"TRANSFER_OUT"}),
        "savings_rate_pct": round(saving / total_income * 100, 1) if total_income else None,
        "monthly_by_category": {
            c: round(abs(v) / months, 2) for c, v in sorted(by_cat.items(), key=lambda kv: kv[1]) if v < 0
        },
        "salary_payers": sorted(p for p in salary_payers if p),
    }
