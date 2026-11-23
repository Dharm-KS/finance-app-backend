"""aggregator data and ai advisor

Revision ID: cf79a2491a85
Revises: 21515b83cd66
Create Date: 2026-11-20 08:48:13.587957+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'cf79a2491a85'
down_revision: Union[str, None] = '21515b83cd66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('advisor_recommendations',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('rec_key', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('why', sa.Text(), nullable=False),
    sa.Column('impact', sa.String(length=10), nullable=False),
    sa.Column('risk', sa.String(length=10), nullable=False),
    sa.Column('effort', sa.String(length=10), nullable=False),
    sa.Column('timeframe', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('agents', sa.JSON(), nullable=False),
    sa.Column('action_steps', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'IN_PROGRESS', 'DONE', 'DISMISSED', name='recommendationstatus', native_enum=False, length=20), nullable=False),
    sa.Column('status_changed_at', sa.DateTime(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_advisor_recommendations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_advisor_recommendations')),
    sa.UniqueConstraint('user_id', 'rec_key', name=op.f('uq_advisor_recommendations_user_id_rec_key'))
    )
    with op.batch_alter_table('advisor_recommendations', schema=None) as batch_op:
        batch_op.create_index('ix_advisor_recommendations_user_id_active_priority', ['user_id', 'active', 'priority'], unique=False)

    op.create_table('agent_states',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('agent_key', sa.Enum('INVESTMENT', 'TAX', 'INSURANCE', 'LOAN', 'BUDGET', 'RSU', 'ESTATE', 'GOAL', 'CHIEF', name='agentkey', native_enum=False, length=20), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'READY', 'FAILED', name='agentstatus', native_enum=False, length=20), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=True),
    sa.Column('facts', sa.JSON(), nullable=True),
    sa.Column('insight', sa.JSON(), nullable=True),
    sa.Column('provider', sa.String(length=30), nullable=True),
    sa.Column('model', sa.String(length=60), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('generated_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agent_states_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_states')),
    sa.UniqueConstraint('user_id', 'agent_key', name=op.f('uq_agent_states_user_id_agent_key'))
    )
    op.create_table('agg_connections',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('status', sa.Enum('PENDING_OTP', 'ACTIVE', 'FAILED', name='aggregatorconnectionstatus', native_enum=False, length=20), nullable=False),
    sa.Column('otp_hash', sa.String(length=128), nullable=True),
    sa.Column('otp_expires_at', sa.DateTime(), nullable=True),
    sa.Column('otp_attempts', sa.Integer(), nullable=False),
    sa.Column('connected_at', sa.DateTime(), nullable=True),
    sa.Column('last_sync_hash', sa.String(length=64), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_connections_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_connections'))
    )
    with op.batch_alter_table('agg_connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_connections_user_id'), ['user_id'], unique=False)

    op.create_table('analysis_runs',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('trigger', sa.String(length=30), nullable=False),
    sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'FAILED', name='analysisrunstatus', native_enum=False, length=20), nullable=False),
    sa.Column('agents_regenerated', sa.JSON(), nullable=False),
    sa.Column('agents_unchanged', sa.JSON(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_analysis_runs_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_runs'))
    )
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.create_index('ix_analysis_runs_user_id_created_at', ['user_id', 'created_at'], unique=False)

    op.create_table('chat_messages',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', name='chatrole', native_enum=False, length=10), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('agents', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_chat_messages_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_messages'))
    )
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.create_index('ix_chat_messages_user_id_created_at', ['user_id', 'created_at'], unique=False)

    op.create_table('customer_extra_data',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('extracted_by', sa.String(length=30), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_customer_extra_data_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_extra_data'))
    )
    with op.batch_alter_table('customer_extra_data', schema=None) as batch_op:
        batch_op.create_index('ix_customer_extra_data_user_id_category', ['user_id', 'category'], unique=False)

    op.create_table('agg_reports',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('section_counts', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_reports_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_reports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_reports'))
    )
    with op.batch_alter_table('agg_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_reports_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index('ix_agg_reports_connection_id_created_at', ['connection_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_reports_user_id'), ['user_id'], unique=False)

    op.create_table('agg_accounts',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('subtype', sa.String(length=40), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('balance_available', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('balance_current', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('interest_rate', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('owners', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_accounts_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_accounts_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_accounts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_accounts'))
    )
    with op.batch_alter_table('agg_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_accounts_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_accounts_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_accounts_user_id'), ['user_id'], unique=False)

    op.create_table('agg_cards',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('subtype', sa.String(length=20), nullable=True),
    sa.Column('code', sa.String(length=32), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('balance_available', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('balance_limit', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('balance_disposed', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('linked_account', sa.String(length=64), nullable=True),
    sa.Column('owners', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_cards_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_cards_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_cards_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_cards'))
    )
    with op.batch_alter_table('agg_cards', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_cards_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_cards_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_cards_user_id'), ['user_id'], unique=False)

    op.create_table('agg_customer_info',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_id', sa.String(length=40), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('gender', sa.String(length=20), nullable=True),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('birth_place', sa.String(length=120), nullable=True),
    sa.Column('job', sa.String(length=160), nullable=True),
    sa.Column('marital_status', sa.String(length=30), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('cell_phone', sa.String(length=30), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_customer_info_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_customer_info_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_customer_info_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_customer_info'))
    )
    with op.batch_alter_table('agg_customer_info', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_customer_info_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_customer_info_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_customer_info_user_id'), ['user_id'], unique=False)

    op.create_table('agg_deposits',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('principal', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('pending_principal', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('maturity_date', sa.Date(), nullable=True),
    sa.Column('payment_frequency', sa.String(length=30), nullable=True),
    sa.Column('capitalization', sa.String(length=30), nullable=True),
    sa.Column('rate_type', sa.String(length=20), nullable=True),
    sa.Column('nominal_interest_rate', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('linked_account', sa.String(length=64), nullable=True),
    sa.Column('accrued_interest', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('expected_interest_total', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('withholding_tax_rate', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('auto_renewal', sa.JSON(), nullable=True),
    sa.Column('early_withdrawal', sa.JSON(), nullable=True),
    sa.Column('owners', sa.JSON(), nullable=True),
    sa.Column('interest_movements', sa.JSON(), nullable=True),
    sa.Column('principal_movements', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_deposits_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_deposits_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_deposits_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_deposits'))
    )
    with op.batch_alter_table('agg_deposits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_deposits_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_deposits_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_deposits_user_id'), ['user_id'], unique=False)

    op.create_table('agg_leases',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('subtype', sa.String(length=40), nullable=True),
    sa.Column('contract_number', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('provider', sa.JSON(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('term_months', sa.Integer(), nullable=True),
    sa.Column('payment_frequency', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('linked_account', sa.String(length=64), nullable=True),
    sa.Column('holders', sa.JSON(), nullable=True),
    sa.Column('asset', sa.JSON(), nullable=True),
    sa.Column('financials', sa.JSON(), nullable=True),
    sa.Column('totals', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_leases_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_leases_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_leases_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_leases'))
    )
    with op.batch_alter_table('agg_leases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_leases_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_leases_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_leases_user_id'), ['user_id'], unique=False)

    op.create_table('agg_loans',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('contract_number', sa.String(length=64), nullable=True),
    sa.Column('loan_type', sa.String(length=80), nullable=True),
    sa.Column('constitution_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('granted_capital', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('pending_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('next_installment', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('linked_account', sa.String(length=64), nullable=True),
    sa.Column('interest_rate', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('expiration_date', sa.Date(), nullable=True),
    sa.Column('pending_receipts', sa.Integer(), nullable=True),
    sa.Column('holders', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_loans_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_loans_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_loans_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_loans'))
    )
    with op.batch_alter_table('agg_loans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_loans_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_loans_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_loans_user_id'), ['user_id'], unique=False)

    op.create_table('agg_portfolios',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('subtype', sa.String(length=40), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('total_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('weighted_return', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('annualized_volatility', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('yield_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contributions', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('withholdings', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('contracting_date', sa.Date(), nullable=True),
    sa.Column('linked_account', sa.String(length=64), nullable=True),
    sa.Column('owners', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_portfolios_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_portfolios_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_portfolios_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_portfolios'))
    )
    with op.batch_alter_table('agg_portfolios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_portfolios_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_portfolios_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_portfolios_user_id'), ['user_id'], unique=False)

    op.create_table('agg_properties',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('purpose', sa.String(length=80), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('trading_price', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('trading_year', sa.Integer(), nullable=True),
    sa.Column('historic_prices', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_properties_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_properties_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_properties_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_properties'))
    )
    with op.batch_alter_table('agg_properties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_properties_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_properties_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_properties_user_id'), ['user_id'], unique=False)

    op.create_table('agg_receipts',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('connection_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('report_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('issuer', sa.String(length=160), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('account', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('last_receipt_date', sa.Date(), nullable=True),
    sa.Column('pdf_file', sa.Text().with_variant(mysql.LONGTEXT(), 'mysql'), nullable=True),
    sa.Column('pdf_file_settled', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['agg_connections.id'], name=op.f('fk_agg_receipts_connection_id_agg_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['agg_reports.id'], name=op.f('fk_agg_receipts_report_id_agg_reports'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agg_receipts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_receipts'))
    )
    with op.batch_alter_table('agg_receipts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_receipts_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_receipts_report_id'), ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agg_receipts_user_id'), ['user_id'], unique=False)

    op.create_table('agg_account_transactions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('value_date', sa.Date(), nullable=True),
    sa.Column('operation_date', sa.Date(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('balance', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('category_type', sa.Integer(), nullable=True),
    sa.Column('additional_info', sa.JSON(), nullable=True),
    sa.Column('transfer_details', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['agg_accounts.id'], name=op.f('fk_agg_account_transactions_account_id_agg_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_account_transactions'))
    )
    with op.batch_alter_table('agg_account_transactions', schema=None) as batch_op:
        batch_op.create_index('ix_agg_account_transactions_account_id_value_date', ['account_id', 'value_date'], unique=False)

    op.create_table('agg_card_transactions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('card_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('settled', sa.Boolean(), nullable=True),
    sa.Column('operation_date', sa.Date(), nullable=True),
    sa.Column('value_date', sa.Date(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('category_type', sa.Integer(), nullable=True),
    sa.Column('additional_info', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['card_id'], ['agg_cards.id'], name=op.f('fk_agg_card_transactions_card_id_agg_cards'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_card_transactions'))
    )
    with op.batch_alter_table('agg_card_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_card_transactions_card_id'), ['card_id'], unique=False)

    op.create_table('agg_lease_installments',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('lease_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('value_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('total', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('breakdown', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.ForeignKeyConstraint(['lease_id'], ['agg_leases.id'], name=op.f('fk_agg_lease_installments_lease_id_agg_leases'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_lease_installments'))
    )
    with op.batch_alter_table('agg_lease_installments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_lease_installments_lease_id'), ['lease_id'], unique=False)

    op.create_table('agg_loan_installments',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('loan_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('amortized', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('interest', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('total', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('pending_capital', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('operation_type', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['loan_id'], ['agg_loans.id'], name=op.f('fk_agg_loan_installments_loan_id_agg_loans'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_loan_installments'))
    )
    with op.batch_alter_table('agg_loan_installments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_loan_installments_loan_id'), ['loan_id'], unique=False)

    op.create_table('agg_portfolio_positions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('portfolio_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('instrument_id', sa.String(length=40), nullable=True),
    sa.Column('instrument_id_type', sa.String(length=10), nullable=True),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('weighting', sa.Numeric(precision=9, scale=4), nullable=True),
    sa.Column('shares', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('price', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('market_mic', sa.String(length=10), nullable=True),
    sa.Column('reference_currency', sa.String(length=3), nullable=True),
    sa.Column('exchange_rate', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('value_time', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['portfolio_id'], ['agg_portfolios.id'], name=op.f('fk_agg_portfolio_positions_portfolio_id_agg_portfolios'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_portfolio_positions'))
    )
    with op.batch_alter_table('agg_portfolio_positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_portfolio_positions_portfolio_id'), ['portfolio_id'], unique=False)

    op.create_table('agg_portfolio_transactions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('portfolio_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('external_uuid', sa.String(length=64), nullable=False),
    sa.Column('operation_pending', sa.Boolean(), nullable=True),
    sa.Column('operation_date', sa.Date(), nullable=True),
    sa.Column('value_date', sa.Date(), nullable=True),
    sa.Column('operation_type', sa.String(length=60), nullable=True),
    sa.Column('shares', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('price', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('instrument_id', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['portfolio_id'], ['agg_portfolios.id'], name=op.f('fk_agg_portfolio_transactions_portfolio_id_agg_portfolios'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agg_portfolio_transactions'))
    )
    with op.batch_alter_table('agg_portfolio_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agg_portfolio_transactions_portfolio_id'), ['portfolio_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('agg_portfolio_transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_portfolio_transactions_portfolio_id'))

    op.drop_table('agg_portfolio_transactions')
    with op.batch_alter_table('agg_portfolio_positions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_portfolio_positions_portfolio_id'))

    op.drop_table('agg_portfolio_positions')
    with op.batch_alter_table('agg_loan_installments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_loan_installments_loan_id'))

    op.drop_table('agg_loan_installments')
    with op.batch_alter_table('agg_lease_installments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_lease_installments_lease_id'))

    op.drop_table('agg_lease_installments')
    with op.batch_alter_table('agg_card_transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_card_transactions_card_id'))

    op.drop_table('agg_card_transactions')
    with op.batch_alter_table('agg_account_transactions', schema=None) as batch_op:
        batch_op.drop_index('ix_agg_account_transactions_account_id_value_date')

    op.drop_table('agg_account_transactions')
    with op.batch_alter_table('agg_receipts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_receipts_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_receipts_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_receipts_connection_id'))

    op.drop_table('agg_receipts')
    with op.batch_alter_table('agg_properties', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_properties_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_properties_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_properties_connection_id'))

    op.drop_table('agg_properties')
    with op.batch_alter_table('agg_portfolios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_portfolios_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_portfolios_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_portfolios_connection_id'))

    op.drop_table('agg_portfolios')
    with op.batch_alter_table('agg_loans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_loans_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_loans_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_loans_connection_id'))

    op.drop_table('agg_loans')
    with op.batch_alter_table('agg_leases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_leases_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_leases_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_leases_connection_id'))

    op.drop_table('agg_leases')
    with op.batch_alter_table('agg_deposits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_deposits_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_deposits_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_deposits_connection_id'))

    op.drop_table('agg_deposits')
    with op.batch_alter_table('agg_customer_info', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_customer_info_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_customer_info_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_customer_info_connection_id'))

    op.drop_table('agg_customer_info')
    with op.batch_alter_table('agg_cards', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_cards_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_cards_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_cards_connection_id'))

    op.drop_table('agg_cards')
    with op.batch_alter_table('agg_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_accounts_user_id'))
        batch_op.drop_index(batch_op.f('ix_agg_accounts_report_id'))
        batch_op.drop_index(batch_op.f('ix_agg_accounts_connection_id'))

    op.drop_table('agg_accounts')
    with op.batch_alter_table('agg_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_reports_user_id'))
        batch_op.drop_index('ix_agg_reports_connection_id_created_at')
        batch_op.drop_index(batch_op.f('ix_agg_reports_connection_id'))

    op.drop_table('agg_reports')
    with op.batch_alter_table('customer_extra_data', schema=None) as batch_op:
        batch_op.drop_index('ix_customer_extra_data_user_id_category')

    op.drop_table('customer_extra_data')
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_chat_messages_user_id_created_at')

    op.drop_table('chat_messages')
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_analysis_runs_user_id_created_at')

    op.drop_table('analysis_runs')
    with op.batch_alter_table('agg_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agg_connections_user_id'))

    op.drop_table('agg_connections')
    op.drop_table('agent_states')
    with op.batch_alter_table('advisor_recommendations', schema=None) as batch_op:
        batch_op.drop_index('ix_advisor_recommendations_user_id_active_priority')

    op.drop_table('advisor_recommendations')
