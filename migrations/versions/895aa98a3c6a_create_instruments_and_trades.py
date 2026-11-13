"""create_instruments_and_trades

Revision ID: 895aa98a3c6a
Revises: edfc97c2022d
Create Date: 2026-11-13 01:07:23.138005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '895aa98a3c6a'
down_revision: Union[str, Sequence[str], None] = 'edfc97c2022d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 建立 instruments 與 trades 表。"""
    op.create_table(
        'instruments',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('market', sa.String(length=20), nullable=False),
        sa.Column('symbol', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_instruments'),
        sa.UniqueConstraint('market', 'symbol', name='uq_instruments_market_symbol'),
        sa.CheckConstraint("market IN ('tw_stock', 'us_stock', 'fund', 'other')", name='ck_instruments_market'),
        sa.CheckConstraint('length(currency) = 3', name='ck_instruments_currency_length'),
    )

    op.create_table(
        'trades',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('instrument_id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('trade_type', sa.String(length=30), nullable=False),
        sa.Column('traded_on', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('price', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('cash_amount', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('ratio', sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column('fee', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('tax', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('fx_rate_to_twd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_trades'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name='fk_trades_instrument_id_instruments', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_trades_account_id_accounts', ondelete='RESTRICT'),
        sa.CheckConstraint(
            "trade_type IN ('buy', 'sell', 'cash_dividend', 'stock_dividend', 'drip', 'split', 'merge', 'capital_reduction')",
            name='ck_trades_trade_type'
        ),
        sa.CheckConstraint('fee IS NULL OR fee >= 0', name='ck_trades_fee_non_negative'),
        sa.CheckConstraint('tax IS NULL OR tax >= 0', name='ck_trades_tax_non_negative'),
        sa.CheckConstraint('length(currency) = 3', name='ck_trades_currency_length'),
        sa.CheckConstraint('fx_rate_to_twd > 0', name='ck_trades_fx_rate_positive'),
    )


def downgrade() -> None:
    """Downgrade schema: 刪除 trades 與 instruments 表。"""
    op.drop_table('trades')
    op.drop_table('instruments')
