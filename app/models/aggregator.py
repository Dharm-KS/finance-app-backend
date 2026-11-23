"""Third-party account-aggregator data (bank accounts, investments, loans, ...).

Each section of the provider's report gets its own table, with columns that mirror the
provider's fields; nested sub-objects without a natural table of their own are kept as JSON.
The untouched payload is kept in ``agg_reports`` for audit / re-parsing.

"Current" data for a connection = the rows of its latest report: a new report replaces the
connection's previous rows (raw reports are kept).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.models.base import Base, BigIntPK, CreatedAtMixin, IdMixin, Money, TimestampMixin, UTCDateTime, enum_column
from app.models.enums import AggregatorConnectionStatus

if TYPE_CHECKING:
    from app.models.user import User


def Qty() -> Numeric:  # noqa: N802 - shares / unit prices need more precision than money
    return Numeric(24, 8, asdecimal=True)


def Rate() -> Numeric:  # noqa: N802 - percentages / weightings
    return Numeric(9, 4, asdecimal=True)


LongText = Text().with_variant(mysql.LONGTEXT(), "mysql")


def _user_fk():
    return mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)


def _connection_fk():
    return mapped_column(BigIntPK, ForeignKey("agg_connections.id", ondelete="CASCADE"), index=True, nullable=False)


def _report_fk():
    return mapped_column(BigIntPK, ForeignKey("agg_reports.id", ondelete="CASCADE"), index=True, nullable=False)


_CHILDREN = {"cascade": "all, delete-orphan", "passive_deletes": True}


# ---- connection + raw reports ------------------------------------------------------------------

class AggregatorConnection(IdMixin, TimestampMixin, Base):
    """One link between a user and the aggregator (established with an OTP)."""

    __tablename__ = "agg_connections"

    user_id: Mapped[int] = _user_fk()
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[AggregatorConnectionStatus] = mapped_column(
        enum_column(AggregatorConnectionStatus, 20), nullable=False
    )
    otp_hash: Mapped[str | None] = mapped_column(String(128))
    otp_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_sync_hash: Mapped[str | None] = mapped_column(String(64))  # combined hash of the last synced reports
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user: Mapped["User"] = relationship()


class AggregatorReport(IdMixin, CreatedAtMixin, Base):
    """The untouched provider response."""

    __tablename__ = "agg_reports"
    __table_args__ = (Index("ix_agg_reports_connection_id_created_at", "connection_id", "created_at"),)

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = deferred(mapped_column(JSON, nullable=False))
    section_counts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


# ---- user_information ----------------------------------------------------------------------------

class AggCustomerInfo(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_customer_info"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_id: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_place: Mapped[str | None] = mapped_column(String(120))
    job: Mapped[str | None] = mapped_column(String(160))
    marital_status: Mapped[str | None] = mapped_column(String(30))
    country: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    cell_phone: Mapped[str | None] = mapped_column(String(30))


# ---- accounts ------------------------------------------------------------------------------------

class AggAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_accounts"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(40))
    code: Mapped[str | None] = mapped_column(String(64))  # IBAN
    name: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_available: Mapped[Decimal | None] = mapped_column(Money())
    balance_current: Mapped[Decimal | None] = mapped_column(Money())
    interest_rate: Mapped[Decimal | None] = mapped_column(Rate())
    owners: Mapped[list | None] = mapped_column(JSON)

    transactions: Mapped[list["AggAccountTransaction"]] = relationship(back_populates="account", **_CHILDREN)


class AggAccountTransaction(IdMixin, Base):
    __tablename__ = "agg_account_transactions"
    __table_args__ = (Index("ix_agg_account_transactions_account_id_value_date", "account_id", "value_date"),)

    account_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("agg_accounts.id", ondelete="CASCADE"), nullable=False
    )
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    operation_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    balance: Mapped[Decimal | None] = mapped_column(Money())
    description: Mapped[str | None] = mapped_column(String(500))
    category_type: Mapped[int | None] = mapped_column(Integer)
    additional_info: Mapped[list | None] = mapped_column(JSON)
    transfer_details: Mapped[dict | None] = mapped_column(JSON)

    account: Mapped[AggAccount] = relationship(back_populates="transactions")


# ---- portfolios ----------------------------------------------------------------------------------

class AggPortfolio(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_portfolios"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(40))  # funds, pension-plans, crypto, stocks
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_value: Mapped[Decimal | None] = mapped_column(Money())
    weighted_return: Mapped[Decimal | None] = mapped_column(Rate())
    annualized_volatility: Mapped[Decimal | None] = mapped_column(Rate())
    yield_amount: Mapped[Decimal | None] = mapped_column(Money())  # provider field "yield"
    contributions: Mapped[Decimal | None] = mapped_column(Money())
    withholdings: Mapped[Decimal | None] = mapped_column(Money())
    contracting_date: Mapped[date | None] = mapped_column(Date)
    linked_account: Mapped[str | None] = mapped_column(String(64))
    owners: Mapped[list | None] = mapped_column(JSON)

    positions: Mapped[list["AggPortfolioPosition"]] = relationship(back_populates="portfolio", **_CHILDREN)
    transactions: Mapped[list["AggPortfolioTransaction"]] = relationship(back_populates="portfolio", **_CHILDREN)


class AggPortfolioPosition(IdMixin, Base):
    """One line of a portfolio's ``composition``. The instrument id is an ISIN, DGS code or ticker."""

    __tablename__ = "agg_portfolio_positions"

    portfolio_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("agg_portfolios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument_id: Mapped[str | None] = mapped_column(String(40))
    instrument_id_type: Mapped[str | None] = mapped_column(String(10))  # ISIN | DGS | ticker
    description: Mapped[str | None] = mapped_column(String(200))
    currency: Mapped[str | None] = mapped_column(String(3))
    weighting: Mapped[Decimal | None] = mapped_column(Rate())
    shares: Mapped[Decimal | None] = mapped_column(Qty())
    price: Mapped[Decimal | None] = mapped_column(Qty())
    total_amount: Mapped[Decimal | None] = mapped_column(Money())
    market_mic: Mapped[str | None] = mapped_column(String(10))
    reference_currency: Mapped[str | None] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Qty())
    value_time: Mapped[str | None] = mapped_column(String(30))

    portfolio: Mapped[AggPortfolio] = relationship(back_populates="positions")


class AggPortfolioTransaction(IdMixin, Base):
    __tablename__ = "agg_portfolio_transactions"

    portfolio_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("agg_portfolios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_pending: Mapped[bool | None] = mapped_column(Boolean)
    operation_date: Mapped[date | None] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    operation_type: Mapped[str | None] = mapped_column(String(60))
    shares: Mapped[Decimal | None] = mapped_column(Qty())
    price: Mapped[Decimal | None] = mapped_column(Qty())
    total_amount: Mapped[Decimal | None] = mapped_column(Money())
    currency: Mapped[str | None] = mapped_column(String(3))
    instrument_id: Mapped[str | None] = mapped_column(String(40))

    portfolio: Mapped[AggPortfolio] = relationship(back_populates="transactions")


# ---- cards ---------------------------------------------------------------------------------------

class AggCard(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_cards"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str | None] = mapped_column(String(20))
    subtype: Mapped[str | None] = mapped_column(String(20))  # debit | credit
    code: Mapped[str | None] = mapped_column(String(32))  # masked PAN
    name: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_available: Mapped[Decimal | None] = mapped_column(Money())
    balance_limit: Mapped[Decimal | None] = mapped_column(Money())
    balance_disposed: Mapped[Decimal | None] = mapped_column(Money())
    linked_account: Mapped[str | None] = mapped_column(String(64))
    owners: Mapped[list | None] = mapped_column(JSON)

    transactions: Mapped[list["AggCardTransaction"]] = relationship(back_populates="card", **_CHILDREN)


class AggCardTransaction(IdMixin, Base):
    __tablename__ = "agg_card_transactions"

    card_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("agg_cards.id", ondelete="CASCADE"), index=True, nullable=False)
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    settled: Mapped[bool | None] = mapped_column(Boolean)
    operation_date: Mapped[date | None] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(String(500))
    category_type: Mapped[int | None] = mapped_column(Integer)
    additional_info: Mapped[list | None] = mapped_column(JSON)

    card: Mapped[AggCard] = relationship(back_populates="transactions")


# ---- loans ---------------------------------------------------------------------------------------

class AggLoan(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_loans"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_number: Mapped[str | None] = mapped_column(String(64))
    loan_type: Mapped[str | None] = mapped_column(String(80))
    constitution_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    granted_capital: Mapped[Decimal | None] = mapped_column(Money())
    pending_amount: Mapped[Decimal | None] = mapped_column(Money())
    next_installment: Mapped[Decimal | None] = mapped_column(Money())
    linked_account: Mapped[str | None] = mapped_column(String(64))
    interest_rate: Mapped[Decimal | None] = mapped_column(Rate())
    expiration_date: Mapped[date | None] = mapped_column(Date)
    pending_receipts: Mapped[int | None] = mapped_column(Integer)
    holders: Mapped[list | None] = mapped_column(JSON)

    installments: Mapped[list["AggLoanInstallment"]] = relationship(
        back_populates="loan", order_by="AggLoanInstallment.installment_date", **_CHILDREN
    )


class AggLoanInstallment(IdMixin, Base):
    """``amortization_made`` (receipt_paid) and ``amortization_pending`` (receipt_scheduled)."""

    __tablename__ = "agg_loan_installments"

    loan_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("agg_loans.id", ondelete="CASCADE"), index=True, nullable=False)
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    installment_date: Mapped[date | None] = mapped_column("date", Date)
    amortized: Mapped[Decimal | None] = mapped_column(Money())
    interest: Mapped[Decimal | None] = mapped_column(Money())
    total: Mapped[Decimal | None] = mapped_column(Money())
    pending_capital: Mapped[Decimal | None] = mapped_column(Money())
    operation_type: Mapped[str | None] = mapped_column(String(30))

    loan: Mapped[AggLoan] = relationship(back_populates="installments")


# ---- properties ----------------------------------------------------------------------------------

class AggProperty(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_properties"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255))
    purpose: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    trading_price: Mapped[Decimal | None] = mapped_column(Money())
    trading_year: Mapped[int | None] = mapped_column(Integer)
    historic_prices: Mapped[list | None] = mapped_column(JSON)


# ---- receipts (direct debits) --------------------------------------------------------------------

class AggReceipt(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_receipts"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    issuer: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(255))
    account: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(20))
    amount: Mapped[Decimal | None] = mapped_column(Money())
    last_receipt_date: Mapped[date | None] = mapped_column(Date)
    pdf_file: Mapped[str | None] = deferred(mapped_column(LongText))  # base64 PDF, never sent to the LLM
    pdf_file_settled: Mapped[bool | None] = mapped_column(Boolean)


# ---- leases --------------------------------------------------------------------------------------

class AggLease(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_leases"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(40))
    contract_number: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(160))
    provider: Mapped[dict | None] = mapped_column(JSON)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int | None] = mapped_column(Integer)
    payment_frequency: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20))
    linked_account: Mapped[str | None] = mapped_column(String(64))
    holders: Mapped[list | None] = mapped_column(JSON)
    asset: Mapped[dict | None] = mapped_column(JSON)
    financials: Mapped[dict | None] = mapped_column(JSON)
    totals: Mapped[dict | None] = mapped_column(JSON)

    installments: Mapped[list["AggLeaseInstallment"]] = relationship(
        back_populates="lease", order_by="AggLeaseInstallment.installment_date", **_CHILDREN
    )


class AggLeaseInstallment(IdMixin, Base):
    __tablename__ = "agg_lease_installments"

    lease_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("agg_leases.id", ondelete="CASCADE"), index=True, nullable=False)
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    installment_date: Mapped[date | None] = mapped_column("date", Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    total: Mapped[Decimal | None] = mapped_column(Money())
    breakdown: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(20))  # paid | pending

    lease: Mapped[AggLease] = relationship(back_populates="installments")


# ---- deposits ------------------------------------------------------------------------------------

class AggDeposit(IdMixin, TimestampMixin, Base):
    __tablename__ = "agg_deposits"

    user_id: Mapped[int] = _user_fk()
    connection_id: Mapped[int] = _connection_fk()
    report_id: Mapped[int] = _report_fk()
    external_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    principal: Mapped[Decimal | None] = mapped_column(Money())
    pending_principal: Mapped[Decimal | None] = mapped_column(Money())
    start_date: Mapped[date | None] = mapped_column(Date)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    payment_frequency: Mapped[str | None] = mapped_column(String(30))
    capitalization: Mapped[str | None] = mapped_column(String(30))
    rate_type: Mapped[str | None] = mapped_column(String(20))
    nominal_interest_rate: Mapped[Decimal | None] = mapped_column(Rate())
    linked_account: Mapped[str | None] = mapped_column(String(64))
    accrued_interest: Mapped[Decimal | None] = mapped_column(Money())
    expected_interest_total: Mapped[Decimal | None] = mapped_column(Money())
    withholding_tax_rate: Mapped[Decimal | None] = mapped_column(Rate())
    status: Mapped[str | None] = mapped_column(String(20))
    auto_renewal: Mapped[dict | None] = mapped_column(JSON)
    early_withdrawal: Mapped[dict | None] = mapped_column(JSON)
    owners: Mapped[list | None] = mapped_column(JSON)
    interest_movements: Mapped[list | None] = mapped_column(JSON)
    principal_movements: Mapped[list | None] = mapped_column(JSON)


# Top-level section tables, in report order (used for replace-on-new-report and summaries).
SECTION_MODELS = {
    "user_information": AggCustomerInfo,
    "accounts": AggAccount,
    "portfolios": AggPortfolio,
    "cards": AggCard,
    "loans": AggLoan,
    "properties": AggProperty,
    "receipts": AggReceipt,
    "leases": AggLease,
    "deposits": AggDeposit,
}
