"""create_income_categories_and_incomes

Revision ID: cd042dc67a1a
Revises: 4913d995bb53
Create Date: 2026-11-07 02:44:29.059711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd042dc67a1a'
down_revision: Union[str, Sequence[str], None] = '4913d995bb53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 建立 income_categories 與 incomes 表。"""
    op.create_table(
        'income_categories',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_income_categories'),
        sa.UniqueConstraint('name', name='uq_income_categories_name'),
    )

    op.create_table(
        'incomes',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('received_on', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('fx_rate_to_twd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('category_id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('invoice_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_incomes'),
        sa.ForeignKeyConstraint(['category_id'], ['income_categories.id'], name='fk_incomes_category_id_income_categories', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_incomes_account_id_accounts', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name='fk_incomes_invoice_id_invoices', ondelete='RESTRICT'),
        sa.UniqueConstraint('invoice_id', name='uq_incomes_invoice_id'),
        sa.CheckConstraint('amount > 0', name='ck_incomes_amount_positive'),
        sa.CheckConstraint('length(currency) = 3', name='ck_incomes_currency_length'),
        sa.CheckConstraint('fx_rate_to_twd > 0', name='ck_incomes_fx_rate_positive'),
        sa.CheckConstraint('source IS NOT NULL OR note IS NOT NULL', name='ck_incomes_source_or_note_not_null'),
    )


def downgrade() -> None:
    """Downgrade schema: 刪除 incomes 與 income_categories 表。"""
    op.drop_table('incomes')
    op.drop_table('income_categories')
