"""create_accounts_and_transfers

Revision ID: bbb3e5cf7466
Revises: 
Create Date: 2026-11-06 23:44:30.982485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbb3e5cf7466'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 建立 accounts 與 transfers 表。"""
    op.create_table(
        'accounts',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='TWD', nullable=False),
        sa.Column('opening_balance', sa.Numeric(precision=14, scale=4), server_default='0', nullable=False),
        sa.Column('statement_day', sa.Integer(), nullable=True),
        sa.Column('payment_day', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_accounts'),
        sa.UniqueConstraint('name', name='uq_accounts_name'),
        sa.CheckConstraint("kind IN ('cash', 'bank', 'credit_card', 'broker')", name='ck_accounts_kind'),
        sa.CheckConstraint("length(currency) = 3", name='ck_accounts_currency_length'),
        sa.CheckConstraint("statement_day IS NULL OR (statement_day >= 1 AND statement_day <= 31)", name='ck_accounts_statement_day'),
        sa.CheckConstraint("payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)", name='ck_accounts_payment_day'),
    )

    op.create_table(
        'transfers',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('transferred_on', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('fx_rate_to_twd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('from_account_id', sa.BigInteger(), nullable=False),
        sa.Column('to_account_id', sa.BigInteger(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_transfers'),
        sa.ForeignKeyConstraint(['from_account_id'], ['accounts.id'], name='fk_transfers_from_account_id_accounts', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['to_account_id'], ['accounts.id'], name='fk_transfers_to_account_id_accounts', ondelete='RESTRICT'),
        sa.CheckConstraint('amount > 0', name='ck_transfers_amount_positive'),
        sa.CheckConstraint('fx_rate_to_twd > 0', name='ck_transfers_fx_rate_positive'),
        sa.CheckConstraint('length(currency) = 3', name='ck_transfers_currency_length'),
        sa.CheckConstraint('from_account_id != to_account_id', name='ck_transfers_different_accounts'),
    )


def downgrade() -> None:
    """Downgrade schema: 刪除 transfers 與 accounts 表。"""
    op.drop_table('transfers')
    op.drop_table('accounts')
