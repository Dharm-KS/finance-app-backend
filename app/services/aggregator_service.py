"""Third-party aggregator: connect with an OTP, then store each report section in its own table.

A sync replaces the connection's previous rows with the new reports' rows (the raw reports are
kept). If the reports are byte-for-byte the same as the last sync, nothing is rewritten and the
caller is told the data didn't change - so agents aren't regenerated for nothing.
"""

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ErrorCode, NotFoundError
from app.core.security import hash_otp, verify_otp_hash
from app.core.time import ensure_utc, utcnow
from app.models.aggregator import (
    SECTION_MODELS,
    AggAccount,
    AggAccountTransaction,
    AggCard,
    AggCardTransaction,
    AggCustomerInfo,
    AggDeposit,
    AggLease,
    AggLeaseInstallment,
    AggLoan,
    AggLoanInstallment,
    AggPortfolio,
    AggPortfolioPosition,
    AggPortfolioTransaction,
    AggProperty,
    AggReceipt,
    AggregatorConnection,
    AggregatorReport,
)
from app.models.enums import AggregatorConnectionStatus
from app.models.user import User
from app.services.fx import convert, reporting_currency
from app.services.providers.aggregator import AggregatorError, AggregatorProvider

OTP_TTL = timedelta(minutes=5)
MAX_OTP_ATTEMPTS = 5


# ---- parsing helpers -----------------------------------------------------------------------------

def _dec(v: Any) -> Decimal | None:
    return None if v is None or v == "" else Decimal(str(v))


def _date(v: Any) -> date | None:
    return date.fromisoformat(str(v)[:10]) if v else None


def _instrument(item: dict) -> tuple[str | None, str | None, str | None]:
    """Composition / transaction lines identify the instrument by ISIN, DGS code or ticker."""
    for key in ("ISIN", "DGS", "ticker"):
        if item.get(key):
            return item[key], key, item.get(f"{key}_description") or item.get("description")
    return None, None, item.get("description")


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate(report: Any) -> dict:
    if not isinstance(report, dict) or report.get("success") is not True or not isinstance(report.get("payload"), dict):
        raise AppError(422, "Report must be an object with success=true and a payload object", ErrorCode.INVALID_REPORT)
    return report["payload"]


# ---- connections ---------------------------------------------------------------------------------

async def list_connections(db: AsyncSession, user: User) -> list[AggregatorConnection]:
    stmt = select(AggregatorConnection).where(AggregatorConnection.user_id == user.id).order_by(AggregatorConnection.id)
    return list((await db.execute(stmt)).scalars())


async def get_connection(db: AsyncSession, user: User, connection_id: int) -> AggregatorConnection:
    conn = (
        await db.execute(
            select(AggregatorConnection).where(
                AggregatorConnection.id == connection_id, AggregatorConnection.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if conn is None:
        raise NotFoundError("Connection not found", ErrorCode.CONNECTION_NOT_FOUND)
    return conn


async def start_connection(db: AsyncSession, user: User, provider: AggregatorProvider) -> AggregatorConnection:
    """Create a connection and send the customer an OTP from the aggregator."""
    otp = provider.generate_otp()
    conn = AggregatorConnection(
        user_id=user.id, provider=provider.name, status=AggregatorConnectionStatus.PENDING_OTP,
        otp_expires_at=utcnow() + OTP_TTL, otp_attempts=0,
    )
    db.add(conn)
    await db.flush()
    conn.otp_hash = hash_otp(otp, f"agg-{conn.id}")
    await provider.send_otp(user.mobile, otp)
    await db.commit()
    return conn


async def verify_connection(
    db: AsyncSession, user: User, connection_id: int, otp: str, provider: AggregatorProvider
) -> tuple[AggregatorConnection, dict]:
    conn = await get_connection(db, user, connection_id)
    if conn.status != AggregatorConnectionStatus.PENDING_OTP or not conn.otp_hash:
        raise AppError(400, "This connection is not waiting for an OTP", ErrorCode.OTP_NOT_REQUESTED)
    if conn.otp_expires_at and utcnow() > ensure_utc(conn.otp_expires_at):
        raise AppError(400, "OTP has expired. Start the connection again.", ErrorCode.OTP_EXPIRED)
    conn.otp_attempts += 1
    if not verify_otp_hash(otp, f"agg-{conn.id}", conn.otp_hash):
        if conn.otp_attempts >= MAX_OTP_ATTEMPTS:
            conn.status = AggregatorConnectionStatus.FAILED
            await db.commit()
            raise AppError(429, "Too many incorrect attempts. Start the connection again.", ErrorCode.OTP_TOO_MANY_ATTEMPTS)
        await db.commit()
        raise AppError(400, f"Invalid OTP. {MAX_OTP_ATTEMPTS - conn.otp_attempts} attempt(s) remaining.", ErrorCode.OTP_INVALID)

    try:
        reports = await provider.fetch_reports(user.mobile)
    except AggregatorError:
        await db.commit()  # keep the attempt count
        raise AppError(503, "Could not fetch data from the provider. Please try again.", ErrorCode.AGGREGATOR_UNAVAILABLE)

    conn.status = AggregatorConnectionStatus.ACTIVE
    conn.otp_hash = None
    conn.connected_at = utcnow()
    result = await sync_reports(db, user, conn, reports)
    return conn, result


async def refresh_connection(
    db: AsyncSession, user: User, connection_id: int, provider: AggregatorProvider
) -> tuple[AggregatorConnection, dict]:
    conn = await _active(db, user, connection_id)
    try:
        reports = await provider.fetch_reports(user.mobile)
    except AggregatorError:
        raise AppError(503, "Could not fetch data from the provider. Please try again.", ErrorCode.AGGREGATOR_UNAVAILABLE)
    return conn, await sync_reports(db, user, conn, reports)


async def push_reports(db: AsyncSession, user: User, connection_id: int, reports: list[dict]) -> tuple[AggregatorConnection, dict]:
    """Test helper: store reports supplied by the caller, as if the provider had sent them."""
    conn = await _active(db, user, connection_id)
    return conn, await sync_reports(db, user, conn, reports)


async def _active(db: AsyncSession, user: User, connection_id: int) -> AggregatorConnection:
    conn = await get_connection(db, user, connection_id)
    if conn.status != AggregatorConnectionStatus.ACTIVE:
        raise AppError(409, "Connection is not active. Verify its OTP first.", ErrorCode.CONNECTION_NOT_ACTIVE)
    return conn


# ---- sync ----------------------------------------------------------------------------------------

async def sync_reports(db: AsyncSession, user: User, conn: AggregatorConnection, reports: list[dict]) -> dict:
    """Store reports for a connection. Returns ``{"changed": bool, "reports": [...counts]}``. Commits."""
    payloads = [_validate(r) for r in reports]
    combined = payload_hash(reports)
    conn.last_synced_at = utcnow()
    if conn.last_sync_hash == combined:
        await db.commit()
        return {"changed": False, "reports": []}

    # Replace the connection's current rows (children go with their parents via FK cascade).
    for model in SECTION_MODELS.values():
        await db.execute(delete(model).where(model.connection_id == conn.id))

    summaries = []
    for raw, payload in zip(reports, payloads, strict=True):
        counts = {k: (len(v) if isinstance(v, list) else 1) for k, v in payload.items()}
        report = AggregatorReport(
            user_id=user.id, connection_id=conn.id, provider=conn.provider,
            payload_hash=payload_hash(raw), payload=raw, section_counts=counts,
        )
        db.add(report)
        await db.flush()
        _store_payload(db, user.id, conn.id, report.id, payload)
        summaries.append({"report_id": report.id, "sections": counts})

    conn.last_sync_hash = combined
    await db.flush()
    await db.commit()
    return {"changed": True, "reports": summaries}


def _store_payload(db: AsyncSession, user_id: int, conn_id: int, report_id: int, p: dict) -> None:
    ids = {"user_id": user_id, "connection_id": conn_id, "report_id": report_id}

    if info := p.get("user_information"):
        db.add(AggCustomerInfo(
            **ids, external_id=info.get("ID"), name=info.get("name"), email=info.get("email"),
            gender=info.get("gender"), birth_date=_date(info.get("birth_date")), birth_place=info.get("birth_place"),
            job=info.get("job"), marital_status=info.get("marital_status"), country=info.get("country"),
            city=info.get("city"), address=info.get("address"), postal_code=info.get("postal_code"),
            cell_phone=info.get("cell_phone"),
        ))

    for a in p.get("accounts") or []:
        bal = a.get("balances") or {}
        db.add(AggAccount(
            **ids, external_uuid=a["uuid"], subtype=a.get("subtype"), code=a.get("code"), name=a.get("name"),
            currency=a.get("currency", "EUR"), balance_available=_dec(bal.get("available")),
            balance_current=_dec(bal.get("current")), interest_rate=_dec(a.get("interest_rate")),
            owners=a.get("owners"),
            transactions=[
                AggAccountTransaction(
                    external_uuid=t["uuid"], value_date=_date(t.get("value_date")),
                    operation_date=_date(t.get("operation_date")), amount=_dec(t.get("amount")) or Decimal("0"),
                    balance=_dec(t.get("balance")), description=(t.get("description") or "")[:500],
                    category_type=(t.get("categorization") or {}).get("type"),
                    additional_info=t.get("additional_info"), transfer_details=t.get("transfer_details"),
                )
                for t in a.get("transactions") or []
            ],
        ))

    for pf in p.get("portfolios") or []:
        positions = []
        for c in pf.get("composition") or []:
            iid, itype, desc = _instrument(c)
            positions.append(AggPortfolioPosition(
                instrument_id=iid, instrument_id_type=itype, description=desc, currency=c.get("currency"),
                weighting=_dec(c.get("weighting")), shares=_dec(c.get("shares")), price=_dec(c.get("price")),
                total_amount=_dec(c.get("total_amount")), market_mic=c.get("MIC"),
                reference_currency=c.get("reference_currency"), exchange_rate=_dec(c.get("exchange_rate")),
                value_time=c.get("value_time"),
            ))
        txs = []
        for t in pf.get("transactions") or []:
            iid, _, _ = _instrument(t)
            txs.append(AggPortfolioTransaction(
                external_uuid=t["uuid"], operation_pending=t.get("operation_pending"),
                operation_date=_date(t.get("operation_date")), value_date=_date(t.get("value_date")),
                operation_type=t.get("operation_type"), shares=_dec(t.get("shares")), price=_dec(t.get("price")),
                total_amount=_dec(t.get("total_amount")), currency=t.get("currency"), instrument_id=iid,
            ))
        db.add(AggPortfolio(
            **ids, external_uuid=pf["uuid"], subtype=pf.get("subtype"), code=pf.get("code"), name=pf.get("name"),
            currency=pf.get("currency", "EUR"), total_value=_dec(pf.get("total_value")),
            weighted_return=_dec(pf.get("weighted_return")), annualized_volatility=_dec(pf.get("annualized_volatility")),
            yield_amount=_dec(pf.get("yield")), contributions=_dec(pf.get("contributions")),
            withholdings=_dec(pf.get("withholdings")), contracting_date=_date(pf.get("contracting_date")),
            linked_account=pf.get("linked_account"), owners=pf.get("owners"),
            positions=positions, transactions=txs,
        ))

    for c in p.get("cards") or []:
        bal = c.get("balances") or {}
        db.add(AggCard(
            **ids, external_uuid=c["uuid"], status=c.get("status"), subtype=c.get("subtype"), code=c.get("code"),
            name=c.get("name"), currency=c.get("currency", "EUR"), balance_available=_dec(bal.get("available")),
            balance_limit=_dec(bal.get("limit")), balance_disposed=_dec(bal.get("disposed")),
            linked_account=c.get("linked_account"), owners=c.get("owner") or c.get("owners"),
            transactions=[
                AggCardTransaction(
                    external_uuid=t["uuid"], settled=t.get("settled"), operation_date=_date(t.get("operation_date")),
                    value_date=_date(t.get("value_date")), amount=_dec(t.get("amount")) or Decimal("0"),
                    currency=t.get("currency"), description=(t.get("description") or "")[:500],
                    category_type=(t.get("categorization") or {}).get("type"), additional_info=t.get("additional_info"),
                )
                for t in c.get("transactions") or []
            ],
        ))

    for ln in p.get("loans") or []:
        inst = [(i, "receipt_paid") for i in ln.get("amortization_made") or []]
        inst += [(i, "receipt_scheduled") for i in ln.get("amortization_pending") or []]
        db.add(AggLoan(
            **ids, external_uuid=ln["uuid"], contract_number=ln.get("contract_number"), loan_type=ln.get("loan_type"),
            constitution_date=_date(ln.get("constitution_date")), currency=ln.get("currency", "EUR"),
            granted_capital=_dec(ln.get("granted_capital")), pending_amount=_dec(ln.get("pending_amount")),
            next_installment=_dec(ln.get("next_installment")), linked_account=ln.get("linked_account"),
            interest_rate=_dec(ln.get("interest_rate")), expiration_date=_date(ln.get("expiration_date")),
            pending_receipts=ln.get("pending_receipts"), holders=ln.get("holders"),
            installments=[
                AggLoanInstallment(
                    external_uuid=i["uuid"], installment_date=_date(i.get("date")), amortized=_dec(i.get("amortized")),
                    interest=_dec(i.get("interest")), total=_dec(i.get("total")),
                    pending_capital=_dec(i.get("pending_capital")), operation_type=i.get("operation_type") or kind,
                )
                for i, kind in inst
            ],
        ))

    for pr in p.get("properties") or []:
        db.add(AggProperty(
            **ids, external_uuid=pr["uuid"], code=pr.get("code"), description=pr.get("description"),
            purpose=pr.get("purpose"), currency=pr.get("currency", "EUR"), trading_price=_dec(pr.get("trading_price")),
            trading_year=pr.get("trading_year"), historic_prices=pr.get("historic_prices"),
        ))

    for r in p.get("receipts") or []:
        db.add(AggReceipt(
            **ids, issuer=r.get("issuer"), description=r.get("description"), account=r.get("account"),
            status=r.get("status"), amount=_dec(r.get("amount")), last_receipt_date=_date(r.get("last_receipt_date")),
            pdf_file=r.get("pdf_file"), pdf_file_settled=r.get("pdf_file_settled"),
        ))

    for ls in p.get("leases") or []:
        installments = (ls.get("installments") or {})
        rows = [(i, "paid") for i in installments.get("paid") or []] + [
            (i, "pending") for i in installments.get("scheduled") or []
        ]
        db.add(AggLease(
            **ids, external_uuid=ls["uuid"], subtype=ls.get("subtype"), contract_number=ls.get("contract_number"),
            name=ls.get("name"), provider=ls.get("provider"), currency=ls.get("currency", "EUR"),
            start_date=_date(ls.get("start_date")), end_date=_date(ls.get("end_date")),
            term_months=ls.get("term_months"), payment_frequency=ls.get("payment_frequency"), status=ls.get("status"),
            linked_account=ls.get("linked_account"), holders=ls.get("holders"), asset=ls.get("asset"),
            financials=ls.get("financials"), totals=ls.get("totals"),
            installments=[
                AggLeaseInstallment(
                    external_uuid=i["uuid"], installment_date=_date(i.get("date")), value_date=_date(i.get("value_date")),
                    currency=i.get("currency"), total=_dec(i.get("total")), breakdown=i.get("breakdown"),
                    status=i.get("status") or kind,
                )
                for i, kind in rows
            ],
        ))

    for d in p.get("deposits") or []:
        db.add(AggDeposit(
            **ids, external_uuid=d["uuid"], code=d.get("code"), name=d.get("name"), currency=d.get("currency", "EUR"),
            principal=_dec(d.get("principal")), pending_principal=_dec(d.get("pending_principal")),
            start_date=_date(d.get("start_date")), maturity_date=_date(d.get("maturity_date")),
            payment_frequency=d.get("payment_frequency"), capitalization=d.get("capitalization"),
            rate_type=d.get("rate_type"), nominal_interest_rate=_dec(d.get("nominal_interest_rate")),
            linked_account=d.get("linked_account"), accrued_interest=_dec(d.get("accrued_interest")),
            expected_interest_total=_dec(d.get("expected_interest_total")),
            withholding_tax_rate=_dec(d.get("withholding_tax_rate")), status=d.get("status"),
            auto_renewal=d.get("auto_renewal"), early_withdrawal=d.get("early_withdrawal"), owners=d.get("owners"),
            interest_movements=d.get("interest_movements"), principal_movements=d.get("principal_movements"),
        ))


# ---- read side -----------------------------------------------------------------------------------

async def data_summary(db: AsyncSession, user: User) -> dict:
    """Counts and headline values of the stored data, per section. Amounts in the reporting currency (INR)."""
    out: dict[str, Any] = {}
    for section, model in SECTION_MODELS.items():
        out[section] = (await db.execute(select(func.count(model.id)).where(model.user_id == user.id))).scalar_one()

    accounts = list((await db.execute(select(AggAccount).where(AggAccount.user_id == user.id))).scalars())
    portfolios = list((await db.execute(select(AggPortfolio).where(AggPortfolio.user_id == user.id))).scalars())
    loans = list((await db.execute(select(AggLoan).where(AggLoan.user_id == user.id))).scalars())
    deposits = list((await db.execute(select(AggDeposit).where(AggDeposit.user_id == user.id))).scalars())
    tx_count = (
        await db.execute(
            select(func.count(AggAccountTransaction.id)).join(AggAccount).where(AggAccount.user_id == user.id)
        )
    ).scalar_one()
    cur = reporting_currency()
    return {
        "currency": cur,
        "counts": {**out, "account_transactions": tx_count},
        "accounts": [
            {"id": a.id, "name": a.name, "subtype": a.subtype, "currency": cur, "original_currency": a.currency,
             "balance": convert(a.balance_current, a.currency)}
            for a in accounts
        ],
        "portfolios": [
            {"id": p.id, "name": p.name, "subtype": p.subtype, "currency": cur, "original_currency": p.currency,
             "total_value": convert(p.total_value, p.currency), "weighted_return": p.weighted_return}
            for p in portfolios
        ],
        "loans": [
            {"id": ln.id, "loan_type": ln.loan_type, "currency": cur, "original_currency": ln.currency,
             "pending_amount": convert(ln.pending_amount, ln.currency), "interest_rate": ln.interest_rate,
             "next_installment": convert(ln.next_installment, ln.currency)}
            for ln in loans
        ],
        "deposits": [
            {"id": d.id, "name": d.name, "currency": cur, "original_currency": d.currency,
             "principal": convert(d.principal, d.currency), "nominal_interest_rate": d.nominal_interest_rate,
             "maturity_date": d.maturity_date}
            for d in deposits
        ],
    }
