"""Pluggable analysis engine.

The dashboard asks an :class:`InsightEngine` for alerts. Today that is a handful of transparent
rules; later an AI-backed engine can implement the same interface (and receive the same
``FinancialSnapshot``) without changing the dashboard API.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from app.models.goal import FinancialGoal
from app.services import goal_service
from app.services.credit_service import summarise
from app.services.financial_service import FinancialSnapshot


def _alert(code: str, severity: str, title: str, message: str) -> dict:
    return {"code": code, "severity": severity, "title": title, "message": message}


class InsightEngine(ABC):
    @abstractmethod
    def alerts(self, snapshot: FinancialSnapshot, goals: list[tuple[FinancialGoal, str | None]]) -> list[dict]:
        ...


class RuleBasedInsightEngine(InsightEngine):
    def alerts(self, s: FinancialSnapshot, goals: list[tuple[FinancialGoal, str | None]]) -> list[dict]:
        out: list[dict] = []

        conc = goal_service.concentration_analysis(s)
        if conc and conc["above_limit"] and conc["percent_of_net_worth"] is not None:
            out.append(_alert(
                "SINGLE_STOCK_ABOVE_LIMIT", "WARNING", "Single-stock concentration is high",
                f"{conc['security_name']} is {goal_service.fmt_pct(conc['percent_of_net_worth'])}% of your "
                f"net worth; your limit is {goal_service.fmt_pct(conc['limit_percent'])}%.",
            ))

        if s.profile and s.profile.monthly_spend > 0:
            months = s.cash / s.profile.monthly_spend
            if months < 3:
                out.append(_alert(
                    "LOW_EMERGENCY_FUND", "WARNING", "Emergency fund is thin",
                    f"Your cash covers about {months.quantize(Decimal('0.1'))} months of spending. Aim for 6.",
                ))

        if s.profile and s.profile.annual_income > 0:
            emi_ratio = s.profile.monthly_emi / (s.profile.annual_income / 12) * 100
            if emi_ratio > 40:
                out.append(_alert(
                    "HIGH_EMI_BURDEN", "WARNING", "EMIs take a large share of income",
                    f"EMIs are {emi_ratio.quantize(Decimal('0.1'))}% of monthly income (healthy: under 40%).",
                ))

        if s.credit_report:
            summary = summarise(s.credit_report)
            util = summary["credit_card_utilization_percent"]
            if util is not None and util > 30:
                out.append(_alert(
                    "HIGH_CREDIT_UTILIZATION", "WARNING", "Credit card utilisation is high",
                    f"You are using {goal_service.fmt_pct(util)}% of your card limits. Keeping it under 30% helps your score.",
                ))
            if summary["max_dpd"] > 0:
                out.append(_alert(
                    "PAST_DUE_HISTORY", "INFO", "Late payments on record",
                    f"Your report shows payments up to {summary['max_dpd']} days past due.",
                ))

        for goal, reason in goals:
            if reason:
                out.append(_alert("GOAL_AT_RISK", "INFO", f"{goal.name} is at risk", reason))

        if s.excluded_holdings:
            out.append(_alert(
                "CURRENCY_NOT_CONVERTED", "INFO", "Some holdings are not included",
                f"{len(s.excluded_holdings)} equity holding(s) are in a different currency from "
                f"{s.currency.value} and are excluded until currency conversion is supported.",
            ))
        return out


def get_insight_engine() -> InsightEngine:
    return RuleBasedInsightEngine()
