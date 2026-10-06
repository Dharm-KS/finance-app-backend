"""Dummy credit bureau used for the MVP.

Profile selection is deterministic, based on the LAST DIGIT of the user's mobile number:

    last digit 0-3  -> PROFILE_GOOD     (score 780)
    last digit 4-6  -> PROFILE_AVERAGE  (score 692)
    last digit 7-9  -> PROFILE_RISKY    (score 615)

Special case: a mobile ending in ``0000`` returns NO_HIT (no bureau record) so the
"credit report unavailable" flow can be tested.

The raw payload intentionally uses a bureau-like shape with its own field names; it is
normalised by :func:`_normalise`, exactly as a real CIBIL integration would have to do.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.core.time import utctoday
from app.models.enums import CreditAccountStatus, CreditAccountType, CreditProviderName, CreditReportStatus
from app.services.providers.credit.base import (
    CreditAccountData,
    CreditProvider,
    CreditReportData,
    CreditSubject,
)

PROFILE_GOOD = "GOOD_780"
PROFILE_AVERAGE = "AVERAGE_692"
PROFILE_RISKY = "RISKY_615"

DUMMY_PROFILES: dict[str, dict[str, Any]] = {
    PROFILE_GOOD: {
        "score": 780,
        "summary": "Good credit history, all payments on time",
        "enquiries": [],
        "tradelines": [
            {
                "accountType": "PERSONAL_LOAN", "memberName": "HDFC Bank", "accountNumber": "XXXXXXXX4821",
                "sanctionedAmount": "500000.00", "currentBalance": "240000.00", "emiAmount": "11250.00",
                "interestRate": "10.75", "tenure": 48, "remainingTenure": 22, "status": "ACTIVE",
                "maxDpd": 0, "dateOpened": "2023-08-05",
            },
            {
                "accountType": "AUTO_LOAN", "memberName": "ICICI Bank", "accountNumber": "XXXXXXXX7710",
                "sanctionedAmount": "800000.00", "currentBalance": "410000.00", "emiAmount": "16700.00",
                "interestRate": "9.10", "tenure": 60, "remainingTenure": 28, "status": "ACTIVE",
                "maxDpd": 0, "dateOpened": "2022-02-14",
            },
            {
                "accountType": "CREDIT_CARD", "memberName": "Axis Bank", "accountNumber": "XXXXXXXXXXXX3390",
                "sanctionedAmount": "300000.00", "creditLimit": "300000.00", "currentBalance": "32000.00",
                "status": "ACTIVE", "maxDpd": 0, "dateOpened": "2019-06-21",
            },
        ],
    },
    PROFILE_AVERAGE: {
        "score": 692,
        "summary": "Average credit profile with a recent enquiry",
        "enquiries": [
            {"daysAgo": 18, "memberName": "Kotak Mahindra Bank", "purpose": "PERSONAL_LOAN", "amount": "200000.00"}
        ],
        "tradelines": [
            {
                "accountType": "PERSONAL_LOAN", "memberName": "Bajaj Finance", "accountNumber": "XXXXXXXX1187",
                "sanctionedAmount": "300000.00", "currentBalance": "185000.00", "emiAmount": "9800.00",
                "interestRate": "13.50", "tenure": 36, "remainingTenure": 21, "status": "ACTIVE",
                "maxDpd": 0, "dateOpened": "2025-01-10",
            },
            {
                "accountType": "CREDIT_CARD", "memberName": "SBI Card", "accountNumber": "XXXXXXXXXXXX5521",
                "sanctionedAmount": "150000.00", "creditLimit": "150000.00", "currentBalance": "62000.00",
                "status": "ACTIVE", "maxDpd": 0, "dateOpened": "2021-03-02",
            },
            {
                "accountType": "CONSUMER_LOAN", "memberName": "HDB Financial Services", "accountNumber": "XXXXXXXX0942",
                "sanctionedAmount": "45000.00", "currentBalance": "18000.00", "emiAmount": "3750.00",
                "interestRate": "16.00", "tenure": 12, "remainingTenure": 5, "status": "ACTIVE",
                "maxDpd": 0, "dateOpened": "2026-01-15",
            },
        ],
    },
    PROFILE_RISKY: {
        "score": 615,
        "summary": "High credit-card utilisation and historical late payments",
        "enquiries": [
            {"daysAgo": 25, "memberName": "Tata Capital", "purpose": "PERSONAL_LOAN", "amount": "150000.00"},
            {"daysAgo": 70, "memberName": "IDFC First Bank", "purpose": "CREDIT_CARD", "amount": "100000.00"},
        ],
        "tradelines": [
            {
                "accountType": "PERSONAL_LOAN", "memberName": "Tata Capital", "accountNumber": "XXXXXXXX6634",
                "sanctionedAmount": "400000.00", "currentBalance": "310000.00", "emiAmount": "13900.00",
                "interestRate": "15.25", "tenure": 36, "remainingTenure": 27, "status": "ACTIVE",
                "maxDpd": 30, "dateOpened": "2025-07-01",
            },
            {
                "accountType": "CREDIT_CARD", "memberName": "HDFC Bank", "accountNumber": "XXXXXXXXXXXX8812",
                "sanctionedAmount": "100000.00", "creditLimit": "100000.00", "currentBalance": "92000.00",
                "status": "ACTIVE", "maxDpd": 60, "dateOpened": "2020-11-11",
            },
            {
                "accountType": "CREDIT_CARD", "memberName": "RBL Bank", "accountNumber": "XXXXXXXXXXXX2045",
                "sanctionedAmount": "50000.00", "creditLimit": "50000.00", "currentBalance": "46500.00",
                "status": "ACTIVE", "maxDpd": 0, "dateOpened": "2022-09-30",
            },
            {
                "accountType": "GOLD_LOAN", "memberName": "Muthoot Finance", "accountNumber": "XXXXXXXX3307",
                "sanctionedAmount": "120000.00", "currentBalance": "0.00", "status": "CLOSED",
                "interestRate": "12.00", "tenure": 12, "remainingTenure": 0,
                "maxDpd": 90, "dateOpened": "2023-04-18", "dateClosed": "2024-04-30",
            },
        ],
    },
}


def select_profile_key(mobile: str) -> str:
    last = int(mobile[-1])
    if last <= 3:
        return PROFILE_GOOD
    if last <= 6:
        return PROFILE_AVERAGE
    return PROFILE_RISKY


def _dec(v: str | None) -> Decimal | None:
    return Decimal(v) if v is not None else None


def _date(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def _build_raw(profile_key: str, subject: CreditSubject, report_date: date, reference: str) -> dict[str, Any]:
    p = DUMMY_PROFILES[profile_key]
    return {
        "bureau": "DUMMY",
        "controlNumber": reference,
        "reportDate": report_date.isoformat(),
        "consumer": {"name": subject.name, "mobile": subject.mobile},
        "scoreDetails": [{"type": "CREDITVISION", "version": "3.0", "value": p["score"]}],
        "profileKey": profile_key,
        "summary": p["summary"],
        "accounts": p["tradelines"],
        "enquiries": [
            {**{k: v for k, v in e.items() if k != "daysAgo"},
             "enquiryDate": (report_date - timedelta(days=e["daysAgo"])).isoformat()}
            for e in p["enquiries"]
        ],
    }


def _normalise(raw: dict[str, Any]) -> tuple[int, list[CreditAccountData]]:
    score = int(raw["scoreDetails"][0]["value"])
    accounts = [
        CreditAccountData(
            account_type=CreditAccountType(t["accountType"]),
            lender_name=t["memberName"],
            account_number_masked=t["accountNumber"],
            sanctioned_amount=Decimal(t["sanctionedAmount"]),
            current_balance=Decimal(t["currentBalance"]),
            credit_limit=_dec(t.get("creditLimit")),
            emi_amount=_dec(t.get("emiAmount")),
            interest_rate=_dec(t.get("interestRate")),
            tenure_months=t.get("tenure"),
            remaining_months=t.get("remainingTenure"),
            account_status=CreditAccountStatus(t["status"]),
            dpd=int(t.get("maxDpd", 0)),
            opened_date=_date(t.get("dateOpened")),
            closed_date=_date(t.get("dateClosed")),
        )
        for t in raw["accounts"]
    ]
    return score, accounts


class DummyCreditProvider(CreditProvider):
    name = CreditProviderName.DUMMY

    async def fetch_report(self, subject: CreditSubject) -> CreditReportData:
        today = utctoday()
        reference = f"DUMMY-{today:%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"

        if subject.mobile.endswith("0000"):
            return CreditReportData(
                provider=self.name, report_type="CONSUMER_CIR", report_reference=reference,
                report_status=CreditReportStatus.NO_HIT, credit_score=None, score_date=None,
                report_date=today, raw_report={"bureau": "DUMMY", "controlNumber": reference, "hit": False},
            )

        raw = _build_raw(select_profile_key(subject.mobile), subject, today, reference)
        score, accounts = _normalise(raw)
        return CreditReportData(
            provider=self.name,
            report_type="CONSUMER_CIR",
            report_reference=reference,
            report_status=CreditReportStatus.SUCCESS,
            credit_score=score,
            score_date=today,
            report_date=today,
            accounts=accounts,
            raw_report=raw,
        )
