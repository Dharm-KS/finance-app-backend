"""bank connect onboarding step

Connecting bank accounts becomes the first onboarding screen after the OTP login.

Revision ID: 7b3e9d2c4a61
Revises: cf79a2491a85
Create Date: 2026-11-27 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7b3e9d2c4a61'
down_revision: Union[str, None] = 'cf79a2491a85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('onboarding', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_connected_completed', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('bank_skipped', sa.Boolean(), server_default=sa.false(), nullable=False))
    # Users who already finished onboarding keep it finished (they aren't sent back to the new step).
    op.execute("UPDATE onboarding SET bank_connected_completed = onboarding_completed")


def downgrade() -> None:
    with op.batch_alter_table('onboarding', schema=None) as batch_op:
        batch_op.drop_column('bank_skipped')
        batch_op.drop_column('bank_connected_completed')
