"""create_expense_categories_and_expenses

Revision ID: edfc97c2022d
Revises: cd042dc67a1a
Create Date: 2026-11-07 03:14:43.055237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'edfc97c2022d'
down_revision: Union[str, Sequence[str], None] = 'cd042dc67a1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 建立 expense_categories 與 expenses 表。"""
    op.create_table(
        'expense_categories',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_expense_categories'),
        sa.UniqueConstraint('name', name='uq_expense_categories_name'),
    )

    op.create_table(
        'expenses',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('spent_on', sa.Date(), nullable=False),
        sa.Column('settled_on', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('fx_rate_to_twd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('category_id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('merchant', sa.String(length=100), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('invoice_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_expenses'),
        sa.ForeignKeyConstraint(['category_id'], ['expense_categories.id'], name='fk_expenses_category_id_expense_categories', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_expenses_account_id_accounts', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name='fk_expenses_invoice_id_invoices', ondelete='RESTRICT'),
        sa.CheckConstraint('amount > 0', name='ck_expenses_amount_positive'),
        sa.CheckConstraint('length(currency) = 3', name='ck_expenses_currency_length'),
        sa.CheckConstraint('fx_rate_to_twd > 0', name='ck_expenses_fx_rate_positive'),
        sa.CheckConstraint('merchant IS NOT NULL OR note IS NOT NULL', name='ck_expenses_merchant_or_note_not_null'),
    )


def downgrade() -> None:
    """Downgrade schema: 刪除 expenses 與 expense_categories 表。"""
    op.drop_table('expenses')
    op.drop_table('expense_categories')
