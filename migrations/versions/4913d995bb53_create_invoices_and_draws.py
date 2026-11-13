"""create_invoices_and_draws

Revision ID: 4913d995bb53
Revises: bbb3e5cf7466
Create Date: 2026-11-07 02:16:39.434104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4913d995bb53'
down_revision: Union[str, Sequence[str], None] = 'bbb3e5cf7466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 建立 invoices, invoice_items, draw_periods, draw_prizes 表。"""
    op.create_table(
        'invoices',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('number', sa.String(length=10), nullable=False),
        sa.Column('issued_on', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='TWD', nullable=False),
        sa.Column('fx_rate_to_twd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('random_code', sa.String(length=4), nullable=True),
        sa.Column('seller_name', sa.String(length=100), nullable=True),
        sa.Column('seller_ban', sa.String(length=8), nullable=True),
        sa.Column('prize_status', sa.String(length=20), server_default='unchecked', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_invoices'),
        sa.UniqueConstraint('number', name='uq_invoices_number'),
        sa.CheckConstraint("number ~ '^[A-Z]{2}[0-9]{8}$'", name='ck_invoices_number_format'),
        sa.CheckConstraint('amount > 0', name='ck_invoices_amount_positive'),
        sa.CheckConstraint("kind IN ('paper', 'electronic')", name='ck_invoices_kind'),
        sa.CheckConstraint('length(currency) = 3', name='ck_invoices_currency_length'),
        sa.CheckConstraint('fx_rate_to_twd > 0', name='ck_invoices_fx_rate_positive'),
        sa.CheckConstraint("random_code IS NULL OR random_code ~ '^[0-9]{4}$'", name='ck_invoices_random_code_format'),
        sa.CheckConstraint("seller_ban IS NULL OR seller_ban ~ '^[0-9]{8}$'", name='ck_invoices_seller_ban_format'),
        sa.CheckConstraint("prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')", name='ck_invoices_prize_status'),
    )

    op.create_table(
        'invoice_items',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('invoice_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('line_amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_invoice_items'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name='fk_invoice_items_invoice_id_invoices', ondelete='CASCADE'),
        sa.CheckConstraint('quantity > 0', name='ck_invoice_items_quantity_positive'),
        sa.CheckConstraint('unit_price > 0', name='ck_invoice_items_unit_price_positive'),
        sa.CheckConstraint('line_amount > 0', name='ck_invoice_items_line_amount_positive'),
    )

    op.create_table(
        'draw_periods',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('period_key', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_draw_periods'),
        sa.UniqueConstraint('period_key', name='uq_draw_periods_period_key'),
    )

    op.create_table(
        'draw_prizes',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('draw_period_id', sa.BigInteger(), nullable=False),
        sa.Column('tier', sa.String(length=20), nullable=False),
        sa.Column('matching_number', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_draw_prizes'),
        sa.ForeignKeyConstraint(['draw_period_id'], ['draw_periods.id'], name='fk_draw_prizes_draw_period_id_draw_periods', ondelete='CASCADE'),
        sa.UniqueConstraint('draw_period_id', 'tier', 'matching_number', name='uq_draw_prizes_period_tier_number'),
        sa.CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name='ck_draw_prizes_tier',
        ),
        sa.CheckConstraint('amount >= 0', name='ck_draw_prizes_amount_non_negative'),
    )


def downgrade() -> None:
    """Downgrade schema: 刪除 draw_prizes, draw_periods, invoice_items, invoices 表。"""
    op.drop_table('draw_prizes')
    op.drop_table('draw_periods')
    op.drop_table('invoice_items')
    op.drop_table('invoices')
