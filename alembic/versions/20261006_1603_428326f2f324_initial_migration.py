"""initial migration

Revision ID: 428326f2f324
Revises: 
Create Date: 2026-10-06 16:03:13.602304+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '428326f2f324'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('mobile', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'BLOCKED', 'DELETED', name='userstatus', native_enum=False, length=20), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('mobile', name=op.f('uq_users_mobile')),
    sa.UniqueConstraint('uuid', name=op.f('uq_users_uuid'))
    )
    op.create_table('consents',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('consent_type', sa.Enum('CREDIT_REPORT', 'FINANCIAL_ANALYSIS', 'DATA_PROCESSING', name='consenttype', native_enum=False, length=30), nullable=False),
    sa.Column('consent_version', sa.String(length=20), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('GRANTED', 'REVOKED', name='consentstatus', native_enum=False, length=20), nullable=False),
    sa.Column('consented_at', sa.DateTime(), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_consents_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consents'))
    )
    op.create_index('ix_consents_user_id_consent_type_created_at', 'consents', ['user_id', 'consent_type', 'created_at'], unique=False)
    op.create_table('credit_reports',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('provider', sa.Enum('DUMMY', 'CIBIL', name='creditprovidername', native_enum=False, length=20), nullable=False),
    sa.Column('report_type', sa.String(length=40), nullable=False),
    sa.Column('report_reference', sa.String(length=64), nullable=False),
    sa.Column('credit_score', sa.Integer(), nullable=True),
    sa.Column('score_date', sa.Date(), nullable=True),
    sa.Column('report_date', sa.Date(), nullable=True),
    sa.Column('report_status', sa.Enum('PENDING', 'SUCCESS', 'FAILED', 'NO_HIT', name='creditreportstatus', native_enum=False, length=20), nullable=False),
    sa.Column('raw_report', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_credit_reports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credit_reports')),
    sa.UniqueConstraint('report_reference', name=op.f('uq_credit_reports_report_reference'))
    )
    op.create_index('ix_credit_reports_user_id_created_at', 'credit_reports', ['user_id', 'created_at'], unique=False)
    op.create_table('equity_holdings',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('employer_name', sa.String(length=120), nullable=False),
    sa.Column('security_name', sa.String(length=120), nullable=False),
    sa.Column('ticker', sa.String(length=20), nullable=True),
    sa.Column('vested_value', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('unvested_value', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.Enum('INR', 'USD', 'EUR', 'GBP', 'SGD', 'AED', name='currency', native_enum=False), nullable=False),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.Column('source', sa.Enum('MANUAL', name='equitysource', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_equity_holdings_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_equity_holdings'))
    )
    op.create_index(op.f('ix_equity_holdings_user_id'), 'equity_holdings', ['user_id'], unique=False)
    op.create_table('financial_goals',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('goal_type', sa.Enum('EMERGENCY_FUND', 'EQUITY_TAX_RESERVE', 'REDUCE_SINGLE_STOCK_CONCENTRATION', 'HOME_DOWN_PAYMENT', name='goaltype', native_enum=False, length=50), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('priority', sa.Enum('ESSENTIAL', 'IMPORTANT', 'OPTIONAL', name='goalpriority', native_enum=False, length=20), nullable=False),
    sa.Column('target_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('current_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('target_date', sa.Date(), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'COMPLETED', 'PAUSED', name='goalstatus', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_financial_goals_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_financial_goals'))
    )
    op.create_index('ix_financial_goals_user_id_status', 'financial_goals', ['user_id', 'status'], unique=False)
    op.create_table('financial_profiles',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('annual_income', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.Enum('INR', 'USD', 'EUR', 'GBP', 'SGD', 'AED', name='currency', native_enum=False), nullable=False),
    sa.Column('monthly_spend', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('cash_reserve', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('monthly_emi', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('total_debt', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('investments', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('employment_type', sa.Enum('SALARIED', 'SELF_EMPLOYED', 'BUSINESS_OWNER', 'STUDENT', 'RETIRED', 'UNEMPLOYED', 'OTHER', name='employmenttype', native_enum=False, length=30), nullable=False),
    sa.Column('age', sa.Integer(), nullable=False),
    sa.Column('dependents', sa.Integer(), nullable=True),
    sa.Column('insurance_cover', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_financial_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_financial_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_financial_profiles_user_id'))
    )
    op.create_table('onboarding',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('current_step', sa.Enum('REGISTRATION', 'CONSENT', 'CREDIT', 'FINANCIAL_PROFILE', 'EQUITY', 'RISK', 'GOALS', 'COMPLETED', name='onboardingstep', native_enum=False, length=30), nullable=False),
    sa.Column('registration_completed', sa.Boolean(), nullable=False),
    sa.Column('consent_completed', sa.Boolean(), nullable=False),
    sa.Column('credit_completed', sa.Boolean(), nullable=False),
    sa.Column('financial_profile_completed', sa.Boolean(), nullable=False),
    sa.Column('equity_completed', sa.Boolean(), nullable=False),
    sa.Column('equity_skipped', sa.Boolean(), nullable=False),
    sa.Column('risk_completed', sa.Boolean(), nullable=False),
    sa.Column('goals_completed', sa.Boolean(), nullable=False),
    sa.Column('onboarding_completed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_onboarding_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_onboarding')),
    sa.UniqueConstraint('user_id', name=op.f('uq_onboarding_user_id'))
    )
    op.create_table('otp_sessions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('mobile', sa.String(length=16), nullable=False),
    sa.Column('purpose', sa.Enum('REGISTER', 'LOGIN', name='otppurpose', native_enum=False, length=20), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'VERIFIED', 'EXPIRED', 'LOCKED', 'SUPERSEDED', name='otpstatus', native_enum=False, length=20), nullable=False),
    sa.Column('otp_hash', sa.String(length=128), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_otp_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_sessions')),
    sa.UniqueConstraint('uuid', name=op.f('uq_otp_sessions_uuid'))
    )
    op.create_index('ix_otp_sessions_mobile_purpose_status', 'otp_sessions', ['mobile', 'purpose', 'status'], unique=False)
    op.create_index(op.f('ix_otp_sessions_user_id'), 'otp_sessions', ['user_id'], unique=False)
    op.create_table('revoked_tokens',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_revoked_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_revoked_tokens')),
    sa.UniqueConstraint('jti', name=op.f('uq_revoked_tokens_jti'))
    )
    op.create_index(op.f('ix_revoked_tokens_expires_at'), 'revoked_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_user_id'), 'revoked_tokens', ['user_id'], unique=False)
    op.create_table('risk_profiles',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('risk_tolerance', sa.Enum('STEADY', 'BALANCED', 'GROWTH', name='risktolerance', native_enum=False, length=20), nullable=False),
    sa.Column('max_drawdown_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('single_stock_limit_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('planning_horizon_years', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('max_drawdown_percent >= 0 AND max_drawdown_percent <= 100', name=op.f('ck_risk_profiles_max_drawdown_range')),
    sa.CheckConstraint('planning_horizon_years >= 1 AND planning_horizon_years <= 50', name=op.f('ck_risk_profiles_horizon_range')),
    sa.CheckConstraint('single_stock_limit_percent >= 0 AND single_stock_limit_percent <= 100', name=op.f('ck_risk_profiles_single_stock_range')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_risk_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_risk_profiles_user_id'))
    )
    op.create_table('credit_accounts',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('credit_report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('account_type', sa.Enum('PERSONAL_LOAN', 'HOME_LOAN', 'AUTO_LOAN', 'EDUCATION_LOAN', 'CONSUMER_LOAN', 'GOLD_LOAN', 'CREDIT_CARD', 'OTHER', name='creditaccounttype', native_enum=False, length=30), nullable=False),
    sa.Column('lender_name', sa.String(length=120), nullable=False),
    sa.Column('account_number_masked', sa.String(length=32), nullable=False),
    sa.Column('sanctioned_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('current_balance', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('credit_limit', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('emi_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('interest_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('tenure_months', sa.Integer(), nullable=True),
    sa.Column('remaining_months', sa.Integer(), nullable=True),
    sa.Column('account_status', sa.Enum('ACTIVE', 'CLOSED', 'WRITTEN_OFF', 'SETTLED', name='creditaccountstatus', native_enum=False, length=20), nullable=False),
    sa.Column('dpd', sa.Integer(), nullable=False),
    sa.Column('opened_date', sa.Date(), nullable=True),
    sa.Column('closed_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['credit_report_id'], ['credit_reports.id'], name=op.f('fk_credit_accounts_credit_report_id_credit_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credit_accounts'))
    )
    op.create_index(op.f('ix_credit_accounts_credit_report_id'), 'credit_accounts', ['credit_report_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_credit_accounts_credit_report_id'), table_name='credit_accounts')
    op.drop_table('credit_accounts')
    op.drop_table('risk_profiles')
    op.drop_index(op.f('ix_revoked_tokens_user_id'), table_name='revoked_tokens')
    op.drop_index(op.f('ix_revoked_tokens_expires_at'), table_name='revoked_tokens')
    op.drop_table('revoked_tokens')
    op.drop_index(op.f('ix_otp_sessions_user_id'), table_name='otp_sessions')
    op.drop_index('ix_otp_sessions_mobile_purpose_status', table_name='otp_sessions')
    op.drop_table('otp_sessions')
    op.drop_table('onboarding')
    op.drop_table('financial_profiles')
    op.drop_index('ix_financial_goals_user_id_status', table_name='financial_goals')
    op.drop_table('financial_goals')
    op.drop_index(op.f('ix_equity_holdings_user_id'), table_name='equity_holdings')
    op.drop_table('equity_holdings')
    op.drop_index('ix_credit_reports_user_id_created_at', table_name='credit_reports')
    op.drop_table('credit_reports')
    op.drop_index('ix_consents_user_id_consent_type_created_at', table_name='consents')
    op.drop_table('consents')
    op.drop_table('users')
