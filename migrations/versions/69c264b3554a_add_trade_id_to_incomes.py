"""add_trade_id_to_incomes

Revision ID: 69c264b3554a
Revises: 895aa98a3c6a
Create Date: 2026-11-13 01:07:26.844245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69c264b3554a'
down_revision: Union[str, Sequence[str], None] = '895aa98a3c6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 在 incomes 表新增 trade_id 欄位與唯一外鍵約束。"""
    with op.batch_alter_table('incomes') as batch_op:
        batch_op.add_column(sa.Column('trade_id', sa.BigInteger(), nullable=True))
        batch_op.create_foreign_key(
            'fk_incomes_trade_id_trades',
            'trades',
            ['trade_id'],
            ['id'],
            ondelete='RESTRICT',
        )
        batch_op.create_unique_constraint('uq_incomes_trade_id', ['trade_id'])


def downgrade() -> None:
    """Downgrade schema: 移除 incomes 表之 trade_id 欄位與相關約束。"""
    with op.batch_alter_table('incomes') as batch_op:
        batch_op.drop_constraint('uq_incomes_trade_id', type_='unique')
        batch_op.drop_constraint('fk_incomes_trade_id_trades', type_='foreignkey')
        batch_op.drop_column('trade_id')
