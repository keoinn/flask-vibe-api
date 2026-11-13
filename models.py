"""資料庫模型定義。

包含 accounts、transfers、invoices、invoice_items、draw_periods、draw_prizes、income_categories、incomes、expense_categories、expenses、instruments 與 trades 之 SQLAlchemy 模型。
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from extensions import db


class Account(db.Model):
    """帳戶模型。

    記錄現金、銀行、信用卡、券商交割戶等資產載體。
    """

    __tablename__ = "accounts"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = db.Column(String(100), nullable=False)
    kind = db.Column(String(30), nullable=False)
    currency = db.Column(String(3), nullable=False, default="TWD", server_default="TWD")
    opening_balance = db.Column(
        Numeric(14, 4), nullable=False, default=Decimal("0.0000"), server_default="0"
    )
    statement_day = db.Column(Integer, nullable=True)
    payment_day = db.Column(Integer, nullable=True)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：轉出與轉入移轉紀錄、入帳紀錄、花費紀錄（父列被參照時禁止刪除）
    outgoing_transfers = relationship(
        "Transfer",
        foreign_keys="Transfer.from_account_id",
        back_populates="from_account",
        passive_deletes="all",
    )
    incoming_transfers = relationship(
        "Transfer",
        foreign_keys="Transfer.to_account_id",
        back_populates="to_account",
        passive_deletes="all",
    )
    incomes = relationship(
        "Income",
        foreign_keys="Income.account_id",
        back_populates="account",
        passive_deletes="all",
    )
    expenses = relationship(
        "Expense",
        foreign_keys="Expense.account_id",
        back_populates="account",
        passive_deletes="all",
    )
    trades = relationship(
        "Trade",
        foreign_keys="Trade.account_id",
        back_populates="account",
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_accounts_name"),
        CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="ck_accounts_kind",
        ),
        CheckConstraint("length(currency) = 3", name="ck_accounts_currency_length"),
        CheckConstraint(
            "statement_day IS NULL OR (statement_day >= 1 AND statement_day <= 31)",
            name="ck_accounts_statement_day",
        ),
        CheckConstraint(
            "payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)",
            name="ck_accounts_payment_day",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "currency": self.currency,
            "opening_balance": float(self.opening_balance) if self.opening_balance is not None else 0.0,
            "statement_day": self.statement_day,
            "payment_day": self.payment_day,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Account id={self.id} name='{self.name}' kind='{self.kind}'>"


class Transfer(db.Model):
    """帳戶移轉模型。

    記錄資金於兩個內部帳戶之間的移動。
    """

    __tablename__ = "transfers"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    transferred_on = db.Column(Date, nullable=False)
    amount = db.Column(Numeric(14, 4), nullable=False)
    currency = db.Column(String(3), nullable=False)
    fx_rate_to_twd = db.Column(Numeric(12, 6), nullable=False)
    from_account_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    to_account_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    note = db.Column(Text, nullable=True)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    from_account = relationship(
        "Account", foreign_keys=[from_account_id], back_populates="outgoing_transfers"
    )
    to_account = relationship(
        "Account", foreign_keys=[to_account_id], back_populates="incoming_transfers"
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        CheckConstraint("fx_rate_to_twd > 0", name="ck_transfers_fx_rate_positive"),
        CheckConstraint("length(currency) = 3", name="ck_transfers_currency_length"),
        CheckConstraint(
            "from_account_id != to_account_id",
            name="ck_transfers_different_accounts",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "transferred_on": self.transferred_on.isoformat() if self.transferred_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Transfer id={self.id} date='{self.transferred_on}' "
            f"amount={self.amount} from={self.from_account_id} to={self.to_account_id}>"
        )


class Invoice(db.Model):
    """統一發票模型。

    記錄發票號碼、開立日期、金額、種類、幣別、對獎狀態與賣方資訊。
    """

    __tablename__ = "invoices"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    number = db.Column(String(10), nullable=False)
    issued_on = db.Column(Date, nullable=False)
    amount = db.Column(Numeric(14, 4), nullable=False)
    kind = db.Column(String(20), nullable=False)
    currency = db.Column(String(3), nullable=False, default="TWD", server_default="TWD")
    fx_rate_to_twd = db.Column(Numeric(12, 6), nullable=False)
    random_code = db.Column(String(4), nullable=True)
    seller_name = db.Column(String(100), nullable=True)
    seller_ban = db.Column(String(8), nullable=True)
    prize_status = db.Column(
        String(20),
        nullable=False,
        default="unchecked",
        server_default="unchecked",
    )
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：發票品項明細（發票刪除時品項級聯刪除）
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # 關聯：發票中獎入帳（一張發票最多一筆入帳，父列被參照時禁止刪除）
    income = relationship(
        "Income",
        back_populates="invoice",
        uselist=False,
        passive_deletes="all",
    )
    # 關聯：花費紀錄（一張發票可對應多筆花費，父列被參照時禁止刪除）
    expenses = relationship(
        "Expense",
        back_populates="invoice",
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("number", name="uq_invoices_number"),
        CheckConstraint("number ~ '^[A-Z]{2}[0-9]{8}$'", name="ck_invoices_number_format"),
        CheckConstraint("amount > 0", name="ck_invoices_amount_positive"),
        CheckConstraint("kind IN ('paper', 'electronic')", name="ck_invoices_kind"),
        CheckConstraint("length(currency) = 3", name="ck_invoices_currency_length"),
        CheckConstraint("fx_rate_to_twd > 0", name="ck_invoices_fx_rate_positive"),
        CheckConstraint(
            "random_code IS NULL OR random_code ~ '^[0-9]{4}$'",
            name="ck_invoices_random_code_format",
        ),
        CheckConstraint(
            "seller_ban IS NULL OR seller_ban ~ '^[0-9]{8}$'",
            name="ck_invoices_seller_ban_format",
        ),
        CheckConstraint(
            "prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')",
            name="ck_invoices_prize_status",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "number": self.number,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "kind": self.kind,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "random_code": self.random_code,
            "seller_name": self.seller_name,
            "seller_ban": self.seller_ban,
            "prize_status": self.prize_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number='{self.number}' amount={self.amount} prize_status='{self.prize_status}'>"


class InvoiceItem(db.Model):
    """發票品項明細模型。

    記錄單張發票內的品項名稱、數量、單價與小計金額。
    """

    __tablename__ = "invoice_items"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    invoice_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(String(150), nullable=False)
    quantity = db.Column(Numeric(12, 4), nullable=False)
    unit_price = db.Column(Numeric(14, 4), nullable=False)
    line_amount = db.Column(Numeric(14, 4), nullable=False)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    invoice = relationship("Invoice", back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_items_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_invoice_items_unit_price_positive"),
        CheckConstraint("line_amount > 0", name="ck_invoice_items_line_amount_positive"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "name": self.name,
            "quantity": float(self.quantity) if self.quantity is not None else 0.0,
            "unit_price": float(self.unit_price) if self.unit_price is not None else 0.0,
            "line_amount": float(self.line_amount) if self.line_amount is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<InvoiceItem id={self.id} invoice_id={self.invoice_id} "
            f"name='{self.name}' line_amount={self.line_amount}>"
        )


class DrawPeriod(db.Model):
    """統一發票開獎期別模型。

    記錄發票開獎期別代碼（如 2026-02）。
    """

    __tablename__ = "draw_periods"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    period_key = db.Column(String(20), nullable=False)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：開獎獎項清單（開獎期刪除時獎項級聯刪除）
    prizes = relationship(
        "DrawPrize",
        back_populates="draw_period",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("period_key", name="uq_draw_periods_period_key"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "period_key": self.period_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<DrawPeriod id={self.id} period_key='{self.period_key}'>"


class DrawPrize(db.Model):
    """統一發票開獎獎項模型。

    記錄各期開出的獎項類別、中獎號碼與獎金金額。
    """

    __tablename__ = "draw_prizes"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    draw_period_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("draw_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier = db.Column(String(20), nullable=False)
    matching_number = db.Column(String(20), nullable=False)
    amount = db.Column(Numeric(14, 4), nullable=False)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    draw_period = relationship("DrawPeriod", back_populates="prizes")

    __table_args__ = (
        UniqueConstraint(
            "draw_period_id", "tier", "matching_number", name="uq_draw_prizes_period_tier_number"
        ),
        CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name="ck_draw_prizes_tier",
        ),
        CheckConstraint("amount >= 0", name="ck_draw_prizes_amount_non_negative"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "draw_period_id": self.draw_period_id,
            "tier": self.tier,
            "matching_number": self.matching_number,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<DrawPrize id={self.id} draw_period_id={self.draw_period_id} "
            f"tier='{self.tier}' number='{self.matching_number}' amount={self.amount}>"
        )


class IncomeCategory(db.Model):
    """入帳分類模型。

    記錄薪水、獎金、利息、中獎、退款等入帳分類。
    """

    __tablename__ = "income_categories"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = db.Column(String(50), nullable=False)
    description = db.Column(Text, nullable=True)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：入帳明細紀錄（父列被參照時禁止刪除）
    incomes = relationship(
        "Income",
        back_populates="category",
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_income_categories_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<IncomeCategory id={self.id} name='{self.name}'>"


class Income(db.Model):
    """入帳冊明細模型。

    記錄外部資金流入具體帳戶的明細事件。
    """

    __tablename__ = "incomes"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    received_on = db.Column(Date, nullable=False)
    amount = db.Column(Numeric(14, 4), nullable=False)
    currency = db.Column(String(3), nullable=False, default="TWD", server_default="TWD")
    fx_rate_to_twd = db.Column(Numeric(12, 6), nullable=False, default=Decimal("1.000000"), server_default="1")
    category_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("income_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source = db.Column(String(100), nullable=True)
    note = db.Column(Text, nullable=True)
    invoice_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trade_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("trades.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    category = relationship("IncomeCategory", back_populates="incomes")
    account = relationship("Account", back_populates="incomes")
    invoice = relationship("Invoice", back_populates="income")
    trade = relationship("Trade", back_populates="income")

    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_incomes_invoice_id"),
        UniqueConstraint("trade_id", name="uq_incomes_trade_id"),
        CheckConstraint("amount > 0", name="ck_incomes_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_incomes_currency_length"),
        CheckConstraint("fx_rate_to_twd > 0", name="ck_incomes_fx_rate_positive"),
        CheckConstraint(
            "source IS NOT NULL OR note IS NOT NULL",
            name="ck_incomes_source_or_note_not_null",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "received_on": self.received_on.isoformat() if self.received_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "category_id": self.category_id,
            "account_id": self.account_id,
            "source": self.source,
            "note": self.note,
            "invoice_id": self.invoice_id,
            "trade_id": self.trade_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Income id={self.id} received_on='{self.received_on}' "
            f"amount={self.amount} account_id={self.account_id}>"
        )


class ExpenseCategory(db.Model):
    """花費分類模型。

    記錄餐飲外食、日常用品、交通運輸、娛樂等花費分類標籤。
    """

    __tablename__ = "expense_categories"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name = db.Column(String(50), nullable=False)
    description = db.Column(Text, nullable=True)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：花費明細紀錄（父列被參照時禁止刪除）
    expenses = relationship(
        "Expense",
        back_populates="category",
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_expense_categories_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<ExpenseCategory id={self.id} name='{self.name}'>"


class Expense(db.Model):
    """花費冊明細模型。

    記錄個人資金流出的具體消費支出事件。
    """

    __tablename__ = "expenses"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    spent_on = db.Column(Date, nullable=False)
    settled_on = db.Column(Date, nullable=True)
    amount = db.Column(Numeric(14, 4), nullable=False)
    currency = db.Column(String(3), nullable=False, default="TWD", server_default="TWD")
    fx_rate_to_twd = db.Column(Numeric(12, 6), nullable=False, default=Decimal("1.000000"), server_default="1")
    category_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merchant = db.Column(String(100), nullable=True)
    note = db.Column(Text, nullable=True)
    invoice_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    category = relationship("ExpenseCategory", back_populates="expenses")
    account = relationship("Account", back_populates="expenses")
    invoice = relationship("Invoice", back_populates="expenses")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_expenses_currency_length"),
        CheckConstraint("fx_rate_to_twd > 0", name="ck_expenses_fx_rate_positive"),
        CheckConstraint(
            "merchant IS NOT NULL OR note IS NOT NULL",
            name="ck_expenses_merchant_or_note_not_null",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spent_on": self.spent_on.isoformat() if self.spent_on else None,
            "settled_on": self.settled_on.isoformat() if self.settled_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "category_id": self.category_id,
            "account_id": self.account_id,
            "merchant": self.merchant,
            "note": self.note,
            "invoice_id": self.invoice_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Expense id={self.id} spent_on='{self.spent_on}' "
            f"amount={self.amount} account_id={self.account_id}>"
        )


class Instrument(db.Model):
    """投資標的模型。

    記錄股票、ETF、基金等金融商品之市場類別、代號、名稱與計價幣別。
    """

    __tablename__ = "instruments"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    market = db.Column(String(20), nullable=False)
    symbol = db.Column(String(30), nullable=False)
    name = db.Column(String(100), nullable=False)
    currency = db.Column(String(3), nullable=False)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯：交易明細紀錄（父列被參照時禁止刪除）
    trades = relationship(
        "Trade",
        back_populates="instrument",
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("market", "symbol", name="uq_instruments_market_symbol"),
        CheckConstraint(
            "market IN ('tw_stock', 'us_stock', 'fund', 'other')",
            name="ck_instruments_market",
        ),
        CheckConstraint("length(currency) = 3", name="ck_instruments_currency_length"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "symbol": self.symbol,
            "name": self.name,
            "currency": self.currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Instrument id={self.id} market='{self.market}' symbol='{self.symbol}' name='{self.name}'>"


class Trade(db.Model):
    """投資交易明細模型。

    記錄買進、賣出、現金股利、股票股利、股息再投入、分割、合併、減資等投資交易。
    """

    __tablename__ = "trades"

    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    instrument_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_type = db.Column(String(30), nullable=False)
    traded_on = db.Column(Date, nullable=False)
    quantity = db.Column(Numeric(14, 4), nullable=True)
    price = db.Column(Numeric(14, 4), nullable=True)
    cash_amount = db.Column(Numeric(14, 4), nullable=True)
    ratio = db.Column(Numeric(14, 6), nullable=True)
    fee = db.Column(Numeric(14, 4), nullable=True)
    tax = db.Column(Numeric(14, 4), nullable=True)
    currency = db.Column(String(3), nullable=False)
    fx_rate_to_twd = db.Column(Numeric(12, 6), nullable=False, default=Decimal("1.000000"), server_default="1")
    voided_at = db.Column(DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("timezone('utc', now())"),
    )

    # 關聯
    instrument = relationship("Instrument", back_populates="trades")
    account = relationship("Account", back_populates="trades")
    # 關聯：現金股利或減資退款可對應一筆入帳（一筆交易最多一筆入帳，父列被參照時禁止刪除）
    income = relationship(
        "Income",
        back_populates="trade",
        uselist=False,
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "trade_type IN ('buy', 'sell', 'cash_dividend', 'stock_dividend', 'drip', 'split', 'merge', 'capital_reduction')",
            name="ck_trades_trade_type",
        ),
        CheckConstraint("fee IS NULL OR fee >= 0", name="ck_trades_fee_non_negative"),
        CheckConstraint("tax IS NULL OR tax >= 0", name="ck_trades_tax_non_negative"),
        CheckConstraint("length(currency) = 3", name="ck_trades_currency_length"),
        CheckConstraint("fx_rate_to_twd > 0", name="ck_trades_fx_rate_positive"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "instrument_id": self.instrument_id,
            "account_id": self.account_id,
            "trade_type": self.trade_type,
            "traded_on": self.traded_on.isoformat() if self.traded_on else None,
            "quantity": float(self.quantity) if self.quantity is not None else None,
            "price": float(self.price) if self.price is not None else None,
            "cash_amount": float(self.cash_amount) if self.cash_amount is not None else None,
            "ratio": float(self.ratio) if self.ratio is not None else None,
            "fee": float(self.fee) if self.fee is not None else None,
            "tax": float(self.tax) if self.tax is not None else None,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "voided_at": self.voided_at.isoformat() if self.voided_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Trade id={self.id} instrument_id={self.instrument_id} "
            f"type='{self.trade_type}' traded_on='{self.traded_on}'>"
        )


