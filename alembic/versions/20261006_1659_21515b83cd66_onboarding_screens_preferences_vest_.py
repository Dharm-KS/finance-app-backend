"""onboarding screens: preferences, vest date, goal inputs

Revision ID: 21515b83cd66
Revises: 428326f2f324
Create Date: 2026-10-06 16:59:04.650322+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21515b83cd66'
down_revision: Union[str, None] = '428326f2f324'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_preferences',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('insight_tone', sa.Enum('CONCISE', 'BALANCED', 'DETAILED', name='insighttone', native_enum=False, length=20), nullable=False),
    sa.Column('vesting_alerts', sa.Boolean(), nullable=False),
    sa.Column('tax_deadline_alerts', sa.Boolean(), nullable=False),
    sa.Column('weekly_digest', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_preferences_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_preferences')),
    sa.UniqueConstraint('user_id', name=op.f('uq_user_preferences_user_id'))
    )
    with op.batch_alter_table('equity_holdings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('next_vest_date', sa.Date(), nullable=True))

    with op.batch_alter_table('financial_goals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inputs', sa.JSON(), nullable=True))

    with op.batch_alter_table('financial_profiles', schema=None) as batch_op:
        batch_op.alter_column('employment_type',
               existing_type=sa.VARCHAR(length=30),
               nullable=True)
        batch_op.alter_column('age',
               existing_type=sa.INTEGER(),
               nullable=True)

    with op.batch_alter_table('onboarding', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferences_completed', sa.Boolean(), server_default=sa.text('0'), nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('onboarding', schema=None) as batch_op:
        batch_op.drop_column('preferences_completed')

    with op.batch_alter_table('financial_profiles', schema=None) as batch_op:
        batch_op.alter_column('age',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.alter_column('employment_type',
               existing_type=sa.VARCHAR(length=30),
               nullable=False)

    with op.batch_alter_table('financial_goals', schema=None) as batch_op:
        batch_op.drop_column('inputs')

    with op.batch_alter_table('equity_holdings', schema=None) as batch_op:
        batch_op.drop_column('next_vest_date')

    op.drop_table('user_preferences')
