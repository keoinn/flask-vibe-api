"""個人記帳本 RESTful API。

支援帳戶 (accounts)、移轉 (transfers)、入帳分類 (income-categories)、入帳 (incomes)、花費分類 (expense-categories)、花費 (expenses)、統一發票 (invoices)、開獎期別與獎項 (draw-periods)、投資標的 (instruments)、投資交易 (trades)、月度現金流摘要 (summary) 與健康檢查端點。
回應格式統一封裝為 code、message、data。
"""

import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from extensions import db
from mock_data import ALLOWED_CATEGORIES, ITEMS, REVIEWS, parse_bool_query, parse_int_query
from models import (
    Account,
    DrawPeriod,
    DrawPrize,
    Expense,
    ExpenseCategory,
    Income,
    IncomeCategory,
    Instrument,
    Invoice,
    InvoiceItem,
    Trade,
    Transfer,
)


def make_response_payload(code, message, data=None, status_code=None, meta=None):
    """統一封裝 JSON 回應與 HTTP 狀態碼。

    回應外層為 code、message、data。code 為與 HTTP 狀態碼相同的整數。
    查詢清單時可傳入 meta。
    """
    if isinstance(code, int):
        http_code = code
    elif status_code is not None:
        http_code = status_code
    elif code == "success":
        http_code = 200
    elif code == "error":
        http_code = status_code if status_code else 400
    else:
        http_code = 200

    body = {"code": http_code, "message": message, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), http_code


def create_app():
    """建立並配置 Flask 應用程式。"""
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url or not database_url.strip():
        raise RuntimeError("未設定環境變數 DATABASE_URL，請在 .env 中指定 Supabase PostgreSQL 連線字串。")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # -------------------------------------------------------------
    # 跨來源資源共享 (CORS) 設定
    # -------------------------------------------------------------
    def is_origin_allowed(origin):
        if not origin:
            return True
        # 放行 http://127.0.0.1 與 http://localhost 的任意連接埠（亦相容 https）
        if re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origin):
            return True
        web_origin = os.environ.get("WEB_ORIGIN")
        if web_origin:
            allowed = [o.strip() for o in web_origin.split(",") if o.strip()]
            if "*" in allowed:
                return True
            clean_origin = origin.rstrip("/")
            for item in allowed:
                clean_item = item.rstrip("/")
                if clean_origin == clean_item:
                    return True
                # 支援如 *.github.io 或 https://*.github.io 萬用字元
                if "*" in clean_item:
                    pattern = "^" + re.escape(clean_item).replace(r"\*", ".*") + "$"
                    if re.match(pattern, clean_origin):
                        return True
        return False

    @app.before_request
    def handle_cors_preflight():
        if request.method == "OPTIONS":
            origin = request.headers.get("Origin") or ""
            if is_origin_allowed(origin):
                res = make_response("", 204)
                allow_origin = origin if origin else "*"
                res.headers["Access-Control-Allow-Origin"] = allow_origin
                res.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
                req_headers = request.headers.get("Access-Control-Request-Headers", "Content-Type, Authorization")
                res.headers["Access-Control-Allow-Headers"] = req_headers
                res.headers["Access-Control-Allow-Private-Network"] = "true"
                res.headers["Access-Control-Max-Age"] = "86400"
                res.headers["Vary"] = "Origin"
                return res

    @app.after_request
    def apply_cors_headers(response):
        origin = request.headers.get("Origin") or ""
        if is_origin_allowed(origin):
            allow_origin = origin if origin else "*"
            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, *"
            response.headers["Access-Control-Allow-Private-Network"] = "true"
            response.headers["Vary"] = "Origin"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    # -------------------------------------------------------------
    # 健康檢查端點
    # -------------------------------------------------------------
    @app.get("/api/health")
    def health_check():
        """回傳伺服器運行狀態與當前時間。"""
        payload = {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
        }
        return make_response_payload(200, "伺服器運作正常，測試正常可以進行其他任務。", payload)

    @app.get("/api/health/db")
    def health_check_db():
        """向 PostgreSQL 執行一次 SELECT 1，確認資料庫連線正常。"""
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return make_response_payload(200, "資料庫連線正常", {"status": "ok"})
        except Exception as exc:
            app.logger.error("資料庫連線失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 帳戶路由 (Accounts)
    # -------------------------------------------------------------
    @app.get("/api/accounts")
    def list_accounts():
        """取得帳戶清單。無資料時回傳空清單。"""
        try:
            accounts = db.session.execute(
                db.select(Account).order_by(Account.id.asc())
            ).scalars().all()
            return make_response_payload(200, "取得帳戶清單成功", [acc.to_dict() for acc in accounts])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/accounts")
    def create_account():
        """新增帳戶。必填 name 與 kind。客戶端提供之 id 與 created_at 一律忽略。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        # 驗證名稱 (必填、非空白字串)
        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return make_response_payload(400, "帳戶名稱為必填且不可為空白")
        name = raw_name.strip()

        # 驗證種類 (必填、在白名單內)
        raw_kind = payload.get("kind")
        if not isinstance(raw_kind, str) or raw_kind.strip() not in {"cash", "bank", "credit_card", "broker"}:
            return make_response_payload(400, "帳戶種類不合法，只允許 cash、bank、credit_card、broker")
        kind = raw_kind.strip()

        # 驗證幣別 (預設 TWD，三碼英文)
        raw_currency = payload.get("currency", "TWD")
        if raw_currency is None:
            raw_currency = "TWD"
        if not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
            return make_response_payload(400, "幣別代碼必須為三碼英文字母")
        currency = raw_currency.strip().upper()

        # 驗證期初餘額 (預設 0，必須為合法數值)
        raw_opening_balance = payload.get("opening_balance", 0)
        if raw_opening_balance is None:
            raw_opening_balance = 0
        try:
            opening_balance = Decimal(str(raw_opening_balance))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "期初餘額必須為數值")

        # 驗證結帳日 (可空，1~31)
        statement_day = payload.get("statement_day")
        if statement_day is not None:
            if isinstance(statement_day, bool) or not isinstance(statement_day, int) or not (1 <= statement_day <= 31):
                return make_response_payload(400, "結帳日必須介於 1 到 31 之間")

        # 驗證繳款日 (可空，1~31)
        payment_day = payload.get("payment_day")
        if payment_day is not None:
            if isinstance(payment_day, bool) or not isinstance(payment_day, int) or not (1 <= payment_day <= 31):
                return make_response_payload(400, "繳款日必須介於 1 到 31 之間")

        try:
            # 檢查名稱重複
            existing = db.session.execute(
                db.select(Account).where(Account.name == name)
            ).scalar_one_or_none()
            if existing:
                return make_response_payload(400, "帳戶名稱已存在，請使用其他名稱")

            account = Account(
                name=name,
                kind=kind,
                currency=currency,
                opening_balance=opening_balance,
                statement_day=statement_day,
                payment_day=payment_day,
            )
            db.session.add(account)
            db.session.commit()
            return make_response_payload(201, "新增帳戶成功", account.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/accounts/<int:account_id>")
    def get_account(account_id):
        """依 ID 取得單一帳戶。"""
        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得帳戶成功", account.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/accounts/<int:account_id>")
    def update_account(account_id):
        """更新帳戶名稱、結帳日或繳款日。主鍵不可變更，並自動更新 updated_at。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return make_response_payload(404, "找不到這一筆", None)

            if "name" in payload:
                raw_name = payload["name"]
                if not isinstance(raw_name, str) or not raw_name.strip():
                    return make_response_payload(400, "帳戶名稱不可為空白")
                new_name = raw_name.strip()
                conflict = db.session.execute(
                    db.select(Account).where(Account.name == new_name, Account.id != account_id)
                ).scalar_one_or_none()
                if conflict:
                    return make_response_payload(400, "帳戶名稱已存在，請使用其他名稱")
                account.name = new_name

            if "statement_day" in payload:
                s_day = payload["statement_day"]
                if s_day is not None:
                    if isinstance(s_day, bool) or not isinstance(s_day, int) or not (1 <= s_day <= 31):
                        return make_response_payload(400, "結帳日必須介於 1 到 31 之間")
                account.statement_day = s_day

            if "payment_day" in payload:
                p_day = payload["payment_day"]
                if p_day is not None:
                    if isinstance(p_day, bool) or not isinstance(p_day, int) or not (1 <= p_day <= 31):
                        return make_response_payload(400, "繳款日必須介於 1 到 31 之間")
                account.payment_day = p_day

            account.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新帳戶成功", account.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/accounts/<int:account_id>/balance")
    def get_account_balance(account_id):
        """計算帳戶餘額：opening_balance + 轉入 - 轉出 + 入帳 - 花費 + 投資交割淨額。純讀取不寫入。"""
        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return make_response_payload(404, "找不到這一筆", None)

            in_transfers = db.session.execute(
                db.select(Transfer).where(Transfer.to_account_id == account_id)
            ).scalars().all()
            out_transfers = db.session.execute(
                db.select(Transfer).where(Transfer.from_account_id == account_id)
            ).scalars().all()
            incomes = db.session.execute(
                db.select(Income).where(Income.account_id == account_id)
            ).scalars().all()
            expenses = db.session.execute(
                db.select(Expense).where(Expense.account_id == account_id)
            ).scalars().all()
            trades = db.session.execute(
                db.select(Trade).where(
                    Trade.account_id == account_id,
                    Trade.voided_at.is_(None),
                )
            ).scalars().all()

            # 投資交易金流計算
            trades_incomes_ids = {inc.trade_id for inc in incomes if inc.trade_id is not None}
            trades_net = Decimal("0")
            trades_net_twd = Decimal("0")

            for t in trades:
                fx = t.fx_rate_to_twd
                fee = t.fee or Decimal("0")
                tax = t.tax or Decimal("0")
                qty = t.quantity or Decimal("0")
                price = t.price or Decimal("0")
                cash = t.cash_amount or Decimal("0")

                if t.trade_type == "buy":
                    cost = (qty * price) + fee + tax
                    trades_net -= cost
                    trades_net_twd -= (cost * fx)
                elif t.trade_type == "sell":
                    revenue = (qty * price) - fee - tax
                    trades_net += revenue
                    trades_net_twd += (revenue * fx)
                elif t.trade_type in ("cash_dividend", "capital_reduction"):
                    if t.id not in trades_incomes_ids:
                        trades_net += cash
                        trades_net_twd += (cash * fx)

            # 原幣別餘額
            in_amount = sum((t.amount for t in in_transfers), Decimal("0"))
            out_amount = sum((t.amount for t in out_transfers), Decimal("0"))
            income_amount = sum((inc.amount for inc in incomes), Decimal("0"))
            expense_amount = sum((exp.amount for exp in expenses), Decimal("0"))
            original_balance = (
                account.opening_balance
                + in_amount
                - out_amount
                + income_amount
                - expense_amount
                + trades_net
            )

            # 台幣餘額：金額先乘上該列的 fx_rate_to_twd
            in_twd = sum((t.amount * t.fx_rate_to_twd for t in in_transfers), Decimal("0"))
            out_twd = sum((t.amount * t.fx_rate_to_twd for t in out_transfers), Decimal("0"))
            income_twd = sum((inc.amount * inc.fx_rate_to_twd for inc in incomes), Decimal("0"))
            expense_twd = sum((exp.amount * exp.fx_rate_to_twd for exp in expenses), Decimal("0"))

            if account.currency == "TWD":
                opening_twd = account.opening_balance
            else:
                all_records = in_transfers + out_transfers + incomes + expenses + trades
                rate = all_records[-1].fx_rate_to_twd if all_records else Decimal("1.0")
                opening_twd = account.opening_balance * rate

            twd_balance = opening_twd + in_twd - out_twd + income_twd - expense_twd + trades_net_twd

            data = {
                "account_id": account.id,
                "name": account.name,
                "currency": account.currency,
                "opening_balance": float(account.opening_balance),
                "balance": float(original_balance),
                "balance_twd": float(twd_balance),
                "original_balance": float(original_balance),
                "twd_balance": float(twd_balance),
            }
            return make_response_payload(200, "取得帳戶餘額成功", data)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 移轉路由 (Transfers)
    # -------------------------------------------------------------
    @app.get("/api/transfers")
    def list_transfers():
        """取得移轉紀錄清單。無資料時回傳空清單。"""
        try:
            transfers = db.session.execute(
                db.select(Transfer).order_by(Transfer.transferred_on.desc(), Transfer.id.desc())
            ).scalars().all()
            return make_response_payload(200, "取得移轉清單成功", [t.to_dict() for t in transfers])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/transfers")
    def create_transfer():
        """新增移轉紀錄。必填日期、金額、幣別、匯率、轉出帳戶與轉入帳戶。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        # 1. 驗證日期
        raw_date = payload.get("transferred_on")
        if not raw_date or not isinstance(raw_date, str):
            return make_response_payload(400, "移轉日期為必填且格式必須為 YYYY-MM-DD")
        try:
            transferred_on = date.fromisoformat(raw_date.strip())
        except Exception:
            return make_response_payload(400, "移轉日期格式無效，請使用 YYYY-MM-DD 格式")

        # 2. 驗證金額
        raw_amount = payload.get("amount")
        if raw_amount is None:
            return make_response_payload(400, "移轉金額為必填且必須大於 0")
        try:
            amount = Decimal(str(raw_amount))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "移轉金額必須為合法數值")
        if amount <= Decimal("0"):
            return make_response_payload(400, "移轉金額必須大於 0")

        # 3. 驗證幣別 (三碼英文)
        raw_currency = payload.get("currency")
        if not raw_currency or not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
            return make_response_payload(400, "幣別代碼為必填且必須為三碼英文字母")
        currency = raw_currency.strip().upper()

        # 4. 驗證匯率
        raw_fx = payload.get("fx_rate_to_twd")
        if raw_fx is None:
            return make_response_payload(400, "換算台幣匯率為必填且必須大於 0")
        try:
            fx_rate = Decimal(str(raw_fx))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "換算台幣匯率必須為合法數值")
        if fx_rate <= Decimal("0"):
            return make_response_payload(400, "換算台幣匯率必須大於 0")

        # 5. 驗證轉出與轉入帳戶
        from_account_id = payload.get("from_account_id")
        if from_account_id is None or isinstance(from_account_id, bool) or not isinstance(from_account_id, int):
            return make_response_payload(400, "轉出帳戶 ID 為必填整數")

        to_account_id = payload.get("to_account_id")
        if to_account_id is None or isinstance(to_account_id, bool) or not isinstance(to_account_id, int):
            return make_response_payload(400, "轉入帳戶 ID 為必填整數")

        if from_account_id == to_account_id:
            return make_response_payload(400, "轉出帳戶與轉入帳戶不可相同")

        try:
            from_account = db.session.get(Account, from_account_id)
            if from_account is None:
                return make_response_payload(400, "轉出帳戶不存在")

            to_account = db.session.get(Account, to_account_id)
            if to_account is None:
                return make_response_payload(400, "轉入帳戶不存在")

            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                return make_response_payload(400, "備註必須為字串")

            transfer = Transfer(
                transferred_on=transferred_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                note=note,
            )
            db.session.add(transfer)
            db.session.commit()
            return make_response_payload(201, "新增移轉成功", transfer.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/transfers/<int:transfer_id>")
    def get_transfer(transfer_id):
        """依 ID 取得單一移轉紀錄。"""
        try:
            transfer = db.session.get(Transfer, transfer_id)
            if transfer is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得移轉成功", transfer.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 入帳分類路由 (Income Categories)
    # -------------------------------------------------------------
    @app.get("/api/income-categories")
    def list_income_categories():
        """取得入帳分類清單。無資料時回傳空清單。"""
        try:
            categories = db.session.execute(
                db.select(IncomeCategory).order_by(IncomeCategory.id.asc())
            ).scalars().all()
            return make_response_payload(
                200, "取得入帳分類清單成功", [c.to_dict() for c in categories]
            )
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/income-categories")
    def create_income_category():
        """新增入帳分類。必填 name。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return make_response_payload(400, "分類名稱為必填且不可為空白")
        name = raw_name.strip()

        raw_desc = payload.get("description")
        description = raw_desc.strip() if isinstance(raw_desc, str) and raw_desc.strip() else None

        try:
            existing = db.session.execute(
                db.select(IncomeCategory).where(IncomeCategory.name == name)
            ).scalar_one_or_none()
            if existing:
                return make_response_payload(400, "分類名稱已存在，請使用其他名稱")

            category = IncomeCategory(name=name, description=description)
            db.session.add(category)
            db.session.commit()
            return make_response_payload(201, "新增入帳分類成功", category.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "分類名稱已存在，請使用其他名稱")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/income-categories/<int:category_id>")
    def get_income_category(category_id):
        """依 ID 取得單一入帳分類。"""
        try:
            category = db.session.get(IncomeCategory, category_id)
            if category is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得入帳分類成功", category.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/income-categories/<int:category_id>")
    def update_income_category(category_id):
        """更新入帳分類名稱或說明。主鍵不可變更，自動更新 updated_at。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            category = db.session.get(IncomeCategory, category_id)
            if category is None:
                return make_response_payload(404, "找不到這一筆", None)

            if "name" in payload:
                raw_name = payload["name"]
                if not isinstance(raw_name, str) or not raw_name.strip():
                    return make_response_payload(400, "分類名稱不可為空白")
                new_name = raw_name.strip()
                conflict = db.session.execute(
                    db.select(IncomeCategory).where(
                        IncomeCategory.name == new_name, IncomeCategory.id != category_id
                    )
                ).scalar_one_or_none()
                if conflict:
                    return make_response_payload(400, "分類名稱已存在，請使用其他名稱")
                category.name = new_name

            if "description" in payload:
                raw_desc = payload["description"]
                if raw_desc is None:
                    category.description = None
                elif isinstance(raw_desc, str):
                    category.description = raw_desc.strip() if raw_desc.strip() else None
                else:
                    return make_response_payload(400, "說明必須為字串或 null")

            category.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新入帳分類成功", category.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或分類名稱已存在")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 入帳明細路由 (Incomes)
    # -------------------------------------------------------------
    @app.get("/api/incomes")
    def list_incomes():
        """取得入帳紀錄清單。支援 account_id、category_id、date_from、date_to 查詢參數。"""
        try:
            query = db.select(Income)

            raw_account_id = request.args.get("account_id")
            if raw_account_id is not None and raw_account_id.strip():
                try:
                    account_id = int(raw_account_id.strip())
                except ValueError:
                    return make_response_payload(400, "帳戶 ID 必須為整數")
                query = query.where(Income.account_id == account_id)

            raw_category_id = request.args.get("category_id")
            if raw_category_id is not None and raw_category_id.strip():
                try:
                    category_id = int(raw_category_id.strip())
                except ValueError:
                    return make_response_payload(400, "分類 ID 必須為整數")
                query = query.where(Income.category_id == category_id)

            raw_date_from = request.args.get("date_from")
            if raw_date_from is not None and raw_date_from.strip():
                try:
                    date_from = date.fromisoformat(raw_date_from.strip())
                except ValueError:
                    return make_response_payload(400, "起始日期格式無效，請使用 YYYY-MM-DD 格式")
                query = query.where(Income.received_on >= date_from)

            raw_date_to = request.args.get("date_to")
            if raw_date_to is not None and raw_date_to.strip():
                try:
                    date_to = date.fromisoformat(raw_date_to.strip())
                except ValueError:
                    return make_response_payload(400, "結束日期格式無效，請使用 YYYY-MM-DD 格式")
                query = query.where(Income.received_on <= date_to)

            query = query.order_by(Income.received_on.desc(), Income.id.desc())
            incomes = db.session.execute(query).scalars().all()
            return make_response_payload(200, "取得入帳清單成功", [inc.to_dict() for inc in incomes])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/incomes")
    def create_income():
        """新增入帳紀錄。必填日期、金額、幣別、匯率、分類與帳戶。source 與 note 至少一個有內容。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        # 1. 驗證日期
        raw_date = payload.get("received_on")
        if not raw_date or not isinstance(raw_date, str):
            return make_response_payload(400, "入帳日期為必填且格式必須為 YYYY-MM-DD")
        try:
            received_on = date.fromisoformat(raw_date.strip())
        except ValueError:
            return make_response_payload(400, "入帳日期格式無效，請使用 YYYY-MM-DD 格式")

        # 2. 驗證金額
        raw_amount = payload.get("amount")
        if raw_amount is None:
            return make_response_payload(400, "入帳金額為必填且必須大於 0")
        try:
            amount = Decimal(str(raw_amount))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "入帳金額必須為合法數值")
        if amount <= Decimal("0"):
            return make_response_payload(400, "入帳金額必須大於 0")

        # 3. 驗證幣別 (三碼英文)
        raw_currency = payload.get("currency")
        if not raw_currency or not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
            return make_response_payload(400, "幣別代碼為必填且必須為三碼英文字母")
        currency = raw_currency.strip().upper()

        # 4. 驗證匯率
        raw_fx = payload.get("fx_rate_to_twd")
        if raw_fx is None:
            return make_response_payload(400, "換算台幣匯率為必填且必須大於 0")
        try:
            fx_rate = Decimal(str(raw_fx))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "換算台幣匯率必須為合法數值")
        if fx_rate <= Decimal("0"):
            return make_response_payload(400, "換算台幣匯率必須大於 0")

        # 5. 驗證分類
        category_id = payload.get("category_id")
        if category_id is None or isinstance(category_id, bool) or not isinstance(category_id, int):
            return make_response_payload(400, "入帳分類 ID 為必填整數")
        try:
            category = db.session.get(IncomeCategory, category_id)
            if category is None:
                return make_response_payload(400, "入帳分類不存在")

            # 6. 驗證帳戶
            account_id = payload.get("account_id")
            if account_id is None or isinstance(account_id, bool) or not isinstance(account_id, int):
                return make_response_payload(400, "帳戶 ID 為必填整數")
            account = db.session.get(Account, account_id)
            if account is None:
                return make_response_payload(400, "帳戶不存在")

            # 7. 驗證來源與備註 (至少一個有內容，JSON null 視同未提供)
            raw_source = payload.get("source")
            source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None

            raw_note = payload.get("note")
            note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

            if source is None and note is None:
                return make_response_payload(400, "來源與備註不可同時為空，至少需填寫一項")

            # 8. 驗證發票 (選填)
            invoice_id = payload.get("invoice_id")
            if invoice_id is not None:
                if isinstance(invoice_id, bool) or not isinstance(invoice_id, int):
                    return make_response_payload(400, "發票 ID 必須為整數")
                inv = db.session.get(Invoice, invoice_id)
                if inv is None:
                    return make_response_payload(400, "關聯發票不存在")
                existing_inv_income = db.session.execute(
                    db.select(Income).where(Income.invoice_id == invoice_id)
                ).scalar_one_or_none()
                if existing_inv_income:
                    return make_response_payload(400, "此發票已有對應的入帳紀錄")

            income = Income(
                received_on=received_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate,
                category_id=category_id,
                account_id=account_id,
                source=source,
                note=note,
                invoice_id=invoice_id,
            )
            db.session.add(income)
            db.session.commit()
            return make_response_payload(201, "新增入帳成功", income.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/incomes/<int:income_id>")
    def get_income(income_id):
        """依 ID 取得單一入帳紀錄。"""
        try:
            income = db.session.get(Income, income_id)
            if income is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得入帳成功", income.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/incomes/<int:income_id>")
    def update_income(income_id):
        """更新入帳紀錄。主鍵與 invoice_id 不可修改，自動更新 updated_at。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            income = db.session.get(Income, income_id)
            if income is None:
                return make_response_payload(404, "找不到這一筆", None)

            if "received_on" in payload:
                raw_date = payload["received_on"]
                if not raw_date or not isinstance(raw_date, str):
                    return make_response_payload(400, "入帳日期格式必須為 YYYY-MM-DD")
                try:
                    income.received_on = date.fromisoformat(raw_date.strip())
                except ValueError:
                    return make_response_payload(400, "入帳日期格式無效，請使用 YYYY-MM-DD 格式")

            if "amount" in payload:
                raw_amount = payload["amount"]
                if raw_amount is None:
                    return make_response_payload(400, "入帳金額必須大於 0")
                try:
                    new_amount = Decimal(str(raw_amount))
                except (ValueError, TypeError, InvalidOperation):
                    return make_response_payload(400, "入帳金額必須為合法數值")
                if new_amount <= Decimal("0"):
                    return make_response_payload(400, "入帳金額必須大於 0")
                income.amount = new_amount

            if "currency" in payload:
                raw_currency = payload["currency"]
                if not raw_currency or not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                    return make_response_payload(400, "幣別代碼必須為三碼英文字母")
                income.currency = raw_currency.strip().upper()

            if "fx_rate_to_twd" in payload:
                raw_fx = payload["fx_rate_to_twd"]
                if raw_fx is None:
                    return make_response_payload(400, "換算台幣匯率必須大於 0")
                try:
                    new_fx = Decimal(str(raw_fx))
                except (ValueError, TypeError, InvalidOperation):
                    return make_response_payload(400, "換算台幣匯率必須為合法數值")
                if new_fx <= Decimal("0"):
                    return make_response_payload(400, "換算台幣匯率必須大於 0")
                income.fx_rate_to_twd = new_fx

            if "category_id" in payload:
                cat_id = payload["category_id"]
                if cat_id is None or isinstance(cat_id, bool) or not isinstance(cat_id, int):
                    return make_response_payload(400, "入帳分類 ID 必須為整數")
                cat = db.session.get(IncomeCategory, cat_id)
                if cat is None:
                    return make_response_payload(400, "入帳分類不存在")
                income.category_id = cat_id

            if "account_id" in payload:
                acc_id = payload["account_id"]
                if acc_id is None or isinstance(acc_id, bool) or not isinstance(acc_id, int):
                    return make_response_payload(400, "帳戶 ID 必須為整數")
                acc = db.session.get(Account, acc_id)
                if acc is None:
                    return make_response_payload(400, "帳戶不存在")
                income.account_id = acc_id

            # 來源與備註更新檢查 (至少一個有內容)
            new_source = income.source
            if "source" in payload:
                raw_source = payload["source"]
                new_source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None

            new_note = income.note
            if "note" in payload:
                raw_note = payload["note"]
                new_note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

            if new_source is None and new_note is None:
                return make_response_payload(400, "來源與備註不可同時為空，至少需填寫一項")

            income.source = new_source
            income.note = new_note

            income.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新入帳成功", income.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 花費分類路由 (Expense Categories)
    # -------------------------------------------------------------
    @app.get("/api/expense-categories")
    def list_expense_categories():
        """取得花費分類清單。無資料時回傳空清單。"""
        try:
            categories = db.session.execute(
                db.select(ExpenseCategory).order_by(ExpenseCategory.id.asc())
            ).scalars().all()
            return make_response_payload(
                200, "取得花費分類清單成功", [c.to_dict() for c in categories]
            )
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/expense-categories")
    def create_expense_category():
        """新增花費分類。必填 name。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return make_response_payload(400, "分類名稱為必填且不可為空白")
        name = raw_name.strip()

        raw_desc = payload.get("description")
        description = raw_desc.strip() if isinstance(raw_desc, str) and raw_desc.strip() else None

        try:
            existing = db.session.execute(
                db.select(ExpenseCategory).where(ExpenseCategory.name == name)
            ).scalar_one_or_none()
            if existing:
                return make_response_payload(400, "分類名稱已存在，請使用其他名稱")

            category = ExpenseCategory(name=name, description=description)
            db.session.add(category)
            db.session.commit()
            return make_response_payload(201, "新增花費分類成功", category.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "分類名稱已存在，請使用其他名稱")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/expense-categories/<int:category_id>")
    def get_expense_category(category_id):
        """依 ID 取得單一花費分類。"""
        try:
            category = db.session.get(ExpenseCategory, category_id)
            if category is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得花費分類成功", category.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/expense-categories/<int:category_id>")
    def update_expense_category(category_id):
        """更新花費分類名稱或說明。主鍵不可變更，自動更新 updated_at。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            category = db.session.get(ExpenseCategory, category_id)
            if category is None:
                return make_response_payload(404, "找不到這一筆", None)

            if "name" in payload:
                raw_name = payload["name"]
                if not isinstance(raw_name, str) or not raw_name.strip():
                    return make_response_payload(400, "分類名稱不可為空白")
                new_name = raw_name.strip()
                conflict = db.session.execute(
                    db.select(ExpenseCategory).where(
                        ExpenseCategory.name == new_name, ExpenseCategory.id != category_id
                    )
                ).scalar_one_or_none()
                if conflict:
                    return make_response_payload(400, "分類名稱已存在，請使用其他名稱")
                category.name = new_name

            if "description" in payload:
                raw_desc = payload["description"]
                if raw_desc is None:
                    category.description = None
                elif isinstance(raw_desc, str):
                    category.description = raw_desc.strip() if raw_desc.strip() else None
                else:
                    return make_response_payload(400, "說明必須為字串或 null")

            category.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新花費分類成功", category.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或分類名稱已存在")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 花費明細路由 (Expenses)
    # -------------------------------------------------------------
    @app.get("/api/expenses")
    def list_expenses():
        """取得花費紀錄清單。支援 account_id、category_id、invoice_id、date_from、date_to 查詢參數。"""
        try:
            query = db.select(Expense)

            raw_account_id = request.args.get("account_id")
            if raw_account_id is not None and raw_account_id.strip():
                try:
                    account_id = int(raw_account_id.strip())
                except ValueError:
                    return make_response_payload(400, "帳戶 ID 必須為整數")
                query = query.where(Expense.account_id == account_id)

            raw_category_id = request.args.get("category_id")
            if raw_category_id is not None and raw_category_id.strip():
                try:
                    category_id = int(raw_category_id.strip())
                except ValueError:
                    return make_response_payload(400, "分類 ID 必須為整數")
                query = query.where(Expense.category_id == category_id)

            raw_invoice_id = request.args.get("invoice_id")
            if raw_invoice_id is not None and raw_invoice_id.strip():
                try:
                    invoice_id = int(raw_invoice_id.strip())
                except ValueError:
                    return make_response_payload(400, "發票 ID 必須為整數")
                query = query.where(Expense.invoice_id == invoice_id)

            raw_date_from = request.args.get("date_from")
            if raw_date_from is not None and raw_date_from.strip():
                try:
                    date_from = date.fromisoformat(raw_date_from.strip())
                except ValueError:
                    return make_response_payload(400, "起始日期格式無效，請使用 YYYY-MM-DD 格式")
                query = query.where(Expense.spent_on >= date_from)

            raw_date_to = request.args.get("date_to")
            if raw_date_to is not None and raw_date_to.strip():
                try:
                    date_to = date.fromisoformat(raw_date_to.strip())
                except ValueError:
                    return make_response_payload(400, "結束日期格式無效，請使用 YYYY-MM-DD 格式")
                query = query.where(Expense.spent_on <= date_to)

            query = query.order_by(Expense.spent_on.desc(), Expense.id.desc())
            expenses = db.session.execute(query).scalars().all()
            return make_response_payload(200, "取得花費清單成功", [exp.to_dict() for exp in expenses])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/expenses")
    def create_expense():
        """新增花費紀錄。必填消費日、金額、幣別、匯率、分類與帳戶。商家與備註至少一個。invoice_id 與 settled_on 選填。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        # 1. 驗證消費日 (spent_on)
        raw_spent = payload.get("spent_on")
        if not raw_spent or not isinstance(raw_spent, str):
            return make_response_payload(400, "消費日期為必填且格式必須為 YYYY-MM-DD")
        try:
            spent_on = date.fromisoformat(raw_spent.strip())
        except ValueError:
            return make_response_payload(400, "消費日期格式無效，請使用 YYYY-MM-DD 格式")

        # 2. 驗證扣款日 (settled_on，選填)
        settled_on = None
        if "settled_on" in payload and payload["settled_on"] is not None:
            raw_settled = payload["settled_on"]
            if not isinstance(raw_settled, str) or not raw_settled.strip():
                return make_response_payload(400, "扣款日期格式無效，請使用 YYYY-MM-DD 格式")
            try:
                settled_on = date.fromisoformat(raw_settled.strip())
            except ValueError:
                return make_response_payload(400, "扣款日期格式無效，請使用 YYYY-MM-DD 格式")

        # 3. 驗證金額
        raw_amount = payload.get("amount")
        if raw_amount is None:
            return make_response_payload(400, "花費金額為必填且必須大於 0")
        try:
            amount = Decimal(str(raw_amount))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "花費金額必須為合法數值")
        if amount <= Decimal("0"):
            return make_response_payload(400, "花費金額必須大於 0")

        # 4. 驗證幣別 (三碼英文)
        raw_currency = payload.get("currency")
        if not raw_currency or not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
            return make_response_payload(400, "幣別代碼為必填且必須為三碼英文字母")
        currency = raw_currency.strip().upper()

        # 5. 驗證匯率
        raw_fx = payload.get("fx_rate_to_twd")
        if raw_fx is None:
            return make_response_payload(400, "換算台幣匯率為必填且必須大於 0")
        try:
            fx_rate = Decimal(str(raw_fx))
        except (ValueError, TypeError, InvalidOperation):
            return make_response_payload(400, "換算台幣匯率必須為合法數值")
        if fx_rate <= Decimal("0"):
            return make_response_payload(400, "換算台幣匯率必須大於 0")

        # 6. 驗證分類
        category_id = payload.get("category_id")
        if category_id is None or isinstance(category_id, bool) or not isinstance(category_id, int):
            return make_response_payload(400, "花費分類 ID 為必填整數")
        try:
            category = db.session.get(ExpenseCategory, category_id)
            if category is None:
                return make_response_payload(400, "花費分類不存在")

            # 7. 驗證帳戶
            account_id = payload.get("account_id")
            if account_id is None or isinstance(account_id, bool) or not isinstance(account_id, int):
                return make_response_payload(400, "帳戶 ID 為必填整數")
            account = db.session.get(Account, account_id)
            if account is None:
                return make_response_payload(400, "帳戶不存在")

            # 8. 驗證商家與備註 (至少一個有內容，JSON null 視同未提供)
            raw_merchant = payload.get("merchant")
            merchant = raw_merchant.strip() if isinstance(raw_merchant, str) and raw_merchant.strip() else None

            raw_note = payload.get("note")
            note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

            if merchant is None and note is None:
                return make_response_payload(400, "商家與備註不可同時為空，至少需填寫一項")

            # 9. 驗證發票 (選填，JSON null 視同未提供)
            invoice_id = None
            if "invoice_id" in payload and payload["invoice_id"] is not None:
                raw_inv = payload["invoice_id"]
                if isinstance(raw_inv, bool) or not isinstance(raw_inv, int):
                    return make_response_payload(400, "發票 ID 必須為整數")
                invoice_id = raw_inv
                inv = db.session.get(Invoice, invoice_id)
                if inv is None:
                    return make_response_payload(400, "關聯發票不存在")

            expense = Expense(
                spent_on=spent_on,
                settled_on=settled_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate,
                category_id=category_id,
                account_id=account_id,
                merchant=merchant,
                note=note,
                invoice_id=invoice_id,
            )
            db.session.add(expense)
            db.session.commit()
            return make_response_payload(201, "新增花費成功", expense.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/expenses/<int:expense_id>")
    def get_expense(expense_id):
        """依 ID 取得單一花費紀錄。"""
        try:
            expense = db.session.get(Expense, expense_id)
            if expense is None:
                return make_response_payload(404, "找不到這一筆", None)
            return make_response_payload(200, "取得花費成功", expense.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/expenses/<int:expense_id>")
    def update_expense(expense_id):
        """更新花費紀錄。主鍵不可修改，自動更新 updated_at。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            expense = db.session.get(Expense, expense_id)
            if expense is None:
                return make_response_payload(404, "找不到這一筆", None)

            if "spent_on" in payload:
                raw_spent = payload["spent_on"]
                if not raw_spent or not isinstance(raw_spent, str):
                    return make_response_payload(400, "消費日期格式必須為 YYYY-MM-DD")
                try:
                    expense.spent_on = date.fromisoformat(raw_spent.strip())
                except ValueError:
                    return make_response_payload(400, "消費日期格式無效，請使用 YYYY-MM-DD 格式")

            if "settled_on" in payload:
                raw_settled = payload["settled_on"]
                if raw_settled is None:
                    expense.settled_on = None
                elif isinstance(raw_settled, str) and raw_settled.strip():
                    try:
                        expense.settled_on = date.fromisoformat(raw_settled.strip())
                    except ValueError:
                        return make_response_payload(400, "扣款日期格式無效，請使用 YYYY-MM-DD 格式")
                else:
                    return make_response_payload(400, "扣款日期格式無效，請使用 YYYY-MM-DD 格式")

            if "amount" in payload:
                raw_amount = payload["amount"]
                if raw_amount is None:
                    return make_response_payload(400, "花費金額必須大於 0")
                try:
                    new_amount = Decimal(str(raw_amount))
                except (ValueError, TypeError, InvalidOperation):
                    return make_response_payload(400, "花費金額必須為合法數值")
                if new_amount <= Decimal("0"):
                    return make_response_payload(400, "花費金額必須大於 0")
                expense.amount = new_amount

            if "currency" in payload:
                raw_currency = payload["currency"]
                if not raw_currency or not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                    return make_response_payload(400, "幣別代碼必須為三碼英文字母")
                expense.currency = raw_currency.strip().upper()

            if "fx_rate_to_twd" in payload:
                raw_fx = payload["fx_rate_to_twd"]
                if raw_fx is None:
                    return make_response_payload(400, "換算台幣匯率必須大於 0")
                try:
                    new_fx = Decimal(str(raw_fx))
                except (ValueError, TypeError, InvalidOperation):
                    return make_response_payload(400, "換算台幣匯率必須為合法數值")
                if new_fx <= Decimal("0"):
                    return make_response_payload(400, "換算台幣匯率必須大於 0")
                expense.fx_rate_to_twd = new_fx

            if "category_id" in payload:
                cat_id = payload["category_id"]
                if cat_id is None or isinstance(cat_id, bool) or not isinstance(cat_id, int):
                    return make_response_payload(400, "花費分類 ID 必須為整數")
                cat = db.session.get(ExpenseCategory, cat_id)
                if cat is None:
                    return make_response_payload(400, "花費分類不存在")
                expense.category_id = cat_id

            if "account_id" in payload:
                acc_id = payload["account_id"]
                if acc_id is None or isinstance(acc_id, bool) or not isinstance(acc_id, int):
                    return make_response_payload(400, "帳戶 ID 必須為整數")
                acc = db.session.get(Account, acc_id)
                if acc is None:
                    return make_response_payload(400, "帳戶不存在")
                expense.account_id = acc_id

            if "invoice_id" in payload:
                inv_id = payload["invoice_id"]
                if inv_id is None:
                    expense.invoice_id = None
                elif isinstance(inv_id, bool) or not isinstance(inv_id, int):
                    return make_response_payload(400, "發票 ID 必須為整數")
                else:
                    inv = db.session.get(Invoice, inv_id)
                    if inv is None:
                        return make_response_payload(400, "關聯發票不存在")
                    expense.invoice_id = inv_id

            # 商家與備註更新檢查 (至少一個有內容)
            new_merchant = expense.merchant
            if "merchant" in payload:
                raw_merchant = payload["merchant"]
                new_merchant = raw_merchant.strip() if isinstance(raw_merchant, str) and raw_merchant.strip() else None

            new_note = expense.note
            if "note" in payload:
                raw_note = payload["note"]
                new_note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

            if new_merchant is None and new_note is None:
                return make_response_payload(400, "商家與備註不可同時為空，至少需填寫一項")

            expense.merchant = new_merchant
            expense.note = new_note

            expense.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新花費成功", expense.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 輔助函式：發票期別與對獎比對
    # -------------------------------------------------------------
    def compute_period_key(issued_on: date) -> str:
        """由開立日計算統一發票期別 (YYYY-01, YYYY-03, ..., YYYY-11)。"""
        odd_month = ((issued_on.month - 1) // 2) * 2 + 1
        return f"{issued_on.year:04d}-{odd_month:02d}"

    def get_period_date_range(period_key: str):
        """解析期別字串取得日期範圍 [start_date, end_date) 左閉右開。"""
        match = re.match(r"^(\d{4})-(01|03|05|07|09|11)$", period_key)
        if not match:
            raise ValueError(f"無效的期別格式: {period_key}")
        year = int(match.group(1))
        start_month = int(match.group(2))
        start_date = date(year, start_month, 1)
        if start_month == 11:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, start_month + 2, 1)
        return start_date, end_date

    def check_single_prize(inv_digits: str, prize: DrawPrize, first_prize_numbers: list) -> bool:
        """檢查單張發票末 8 碼是否符合該獎項條件。"""
        tier = prize.tier
        matching = (prize.matching_number or "").strip()

        if tier in ("special", "grand", "first"):
            return inv_digits == matching

        if tier == "extra_sixth":
            return len(matching) >= 3 and inv_digits.endswith(matching)

        if tier in ("second", "third", "fourth", "fifth", "sixth"):
            tier_len_map = {
                "second": 7,
                "third": 6,
                "fourth": 5,
                "fifth": 4,
                "sixth": 3,
            }
            n = tier_len_map[tier]
            if len(matching) == n and inv_digits.endswith(matching):
                return True
            if len(matching) == 8 and inv_digits.endswith(matching[-n:]):
                return True
            for fn in first_prize_numbers:
                if len(fn) == 8 and inv_digits.endswith(fn[-n:]):
                    return True
            return False

        if matching and inv_digits == matching:
            return True
        if len(matching) >= 3 and inv_digits.endswith(matching):
            return True
        return False

    def find_winning_prize(invoice: Invoice, prizes: list) -> DrawPrize | None:
        """比對發票與獎項清單，回傳中獎金額最高的獎項；若未中獎回傳 None。"""
        inv_digits = invoice.number[2:] if len(invoice.number) >= 10 else invoice.number
        first_prize_numbers = [
            p.matching_number.strip()
            for p in prizes
            if p.tier == "first" and len(p.matching_number.strip()) == 8
        ]
        matched = []
        for p in prizes:
            if check_single_prize(inv_digits, p, first_prize_numbers):
                matched.append(p)
        if not matched:
            return None
        return max(matched, key=lambda p: p.amount)

    # -------------------------------------------------------------
    # 發票路由 (Invoices)
    # -------------------------------------------------------------
    @app.post("/api/invoices")
    def create_invoice():
        """新增統一發票。必填號碼、開立日、金額、種類。幣別未送時用 TWD，匯率未送且幣別為 TWD 時用 1。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        for field in ("number", "issued_on", "amount", "kind"):
            if field not in payload or payload[field] is None:
                return make_response_payload(400, f"必填欄位缺失: {field}")

        raw_number = str(payload["number"]).strip()
        if not re.match(r"^[A-Z]{2}[0-9]{8}$", raw_number):
            return make_response_payload(400, "發票號碼格式錯誤，必須為 2 碼大寫英文加 8 碼數字")

        raw_issued = str(payload["issued_on"]).strip()
        try:
            issued_date = date.fromisoformat(raw_issued)
        except ValueError:
            return make_response_payload(400, "開立日期格式錯誤，應為 YYYY-MM-DD")

        try:
            amount = Decimal(str(payload["amount"]))
            if amount <= Decimal("0"):
                return make_response_payload(400, "發票金額必須大於 0")
        except (InvalidOperation, TypeError, ValueError):
            return make_response_payload(400, "發票金額必須為數值且大於 0")

        kind = str(payload["kind"]).strip()
        if kind not in ("paper", "electronic"):
            return make_response_payload(400, "發票種類必須為 paper 或 electronic")

        currency = payload.get("currency")
        if currency is None or (isinstance(currency, str) and not currency.strip()):
            currency = "TWD"
        else:
            currency = str(currency).strip().upper()
            if len(currency) != 3:
                return make_response_payload(400, "幣別代碼必須為 3 碼英文字母")

        raw_fx = payload.get("fx_rate_to_twd")
        if raw_fx is None or (isinstance(raw_fx, str) and not raw_fx.strip()):
            if currency == "TWD":
                fx_rate_to_twd = Decimal("1.000000")
            else:
                return make_response_payload(400, "非 TWD 幣別必須提供換算台幣匯率")
        else:
            try:
                fx_rate_to_twd = Decimal(str(raw_fx))
                if fx_rate_to_twd <= Decimal("0"):
                    return make_response_payload(400, "匯率必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "匯率必須為數值且大於 0")

        random_code = payload.get("random_code")
        if random_code is not None:
            random_code = str(random_code).strip()
            if random_code:
                if not re.match(r"^[0-9]{4}$", random_code):
                    return make_response_payload(400, "發票隨機碼必須為 4 碼數字")
            else:
                random_code = None

        seller_name = payload.get("seller_name")
        if seller_name is not None:
            seller_name = str(seller_name).strip()
            if len(seller_name) > 100:
                return make_response_payload(400, "賣方名稱長度不可超過 100 字元")
            if not seller_name:
                seller_name = None

        seller_ban = payload.get("seller_ban")
        if seller_ban is not None:
            seller_ban = str(seller_ban).strip()
            if seller_ban:
                if not re.match(r"^[0-9]{8}$", seller_ban):
                    return make_response_payload(400, "賣方統一編號必須為 8 碼數字")
            else:
                seller_ban = None

        try:
            existing = db.session.execute(
                db.select(Invoice).where(Invoice.number == raw_number)
            ).scalar_one_or_none()
            if existing:
                return make_response_payload(400, "發票號碼已存在，不可重複新增")

            invoice = Invoice(
                number=raw_number,
                issued_on=issued_date,
                amount=amount,
                kind=kind,
                currency=currency,
                fx_rate_to_twd=fx_rate_to_twd,
                random_code=random_code,
                seller_name=seller_name,
                seller_ban=seller_ban,
                prize_status="unchecked",
            )
            db.session.add(invoice)
            db.session.commit()
            return make_response_payload(201, "新增發票成功", invoice.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/invoices")
    def list_invoices():
        """查詢發票清單。可依 period_key 與 prize_status 篩選。"""
        try:
            stmt = db.select(Invoice)

            period_key = request.args.get("period_key")
            if period_key:
                period_key = period_key.strip()
                try:
                    start_date, end_date = get_period_date_range(period_key)
                    stmt = stmt.where(Invoice.issued_on >= start_date, Invoice.issued_on < end_date)
                except ValueError:
                    return make_response_payload(400, "期別格式錯誤，應為 YYYY-01、YYYY-03 等")

            prize_status = request.args.get("prize_status")
            if prize_status:
                prize_status = prize_status.strip()
                if prize_status not in ("unchecked", "lost", "won", "claimed", "void"):
                    return make_response_payload(400, "無效的對獎狀態參數")
                stmt = stmt.where(Invoice.prize_status == prize_status)

            stmt = stmt.order_by(Invoice.issued_on.desc(), Invoice.id.desc())
            invoices = db.session.execute(stmt).scalars().all()
            return make_response_payload(200, "取得發票清單成功", [inv.to_dict() for inv in invoices])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/invoices/<int:invoice_id>")
    def get_invoice(invoice_id):
        """取得單筆發票。在 data 帶上品項清單與已掛上的花費 id 清單。"""
        try:
            invoice = db.session.get(Invoice, invoice_id)
            if invoice is None:
                return make_response_payload(404, "找不到該發票", None)

            data = invoice.to_dict()
            data["items"] = [item.to_dict() for item in invoice.items]
            data["expense_ids"] = [exp.id for exp in invoice.expenses]
            return make_response_payload(200, "取得發票成功", data)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.patch("/api/invoices/<int:invoice_id>")
    def update_invoice(invoice_id):
        """更新發票。可改賣方、隨機碼；可把 prize_status 改成 void。不可改號碼與主鍵。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            invoice = db.session.get(Invoice, invoice_id)
            if invoice is None:
                return make_response_payload(404, "找不到該發票", None)

            # 不可修改號碼與主鍵
            if "number" in payload and payload["number"] != invoice.number:
                return make_response_payload(400, "不可修改發票號碼與主鍵")
            if "id" in payload and payload["id"] != invoice.id:
                return make_response_payload(400, "不可修改發票號碼與主鍵")

            if "seller_name" in payload:
                sn = payload["seller_name"]
                if sn is not None:
                    sn = str(sn).strip()
                    if len(sn) > 100:
                        return make_response_payload(400, "賣方名稱長度不可超過 100 字元")
                    invoice.seller_name = sn if sn else None
                else:
                    invoice.seller_name = None

            if "seller_ban" in payload:
                sb = payload["seller_ban"]
                if sb is not None:
                    sb = str(sb).strip()
                    if sb:
                        if not re.match(r"^[0-9]{8}$", sb):
                            return make_response_payload(400, "賣方統一編號必須為 8 碼數字")
                        invoice.seller_ban = sb
                    else:
                        invoice.seller_ban = None
                else:
                    invoice.seller_ban = None

            if "random_code" in payload:
                rc = payload["random_code"]
                if rc is not None:
                    rc = str(rc).strip()
                    if rc:
                        if not re.match(r"^[0-9]{4}$", rc):
                            return make_response_payload(400, "發票隨機碼必須為 4 碼數字")
                        invoice.random_code = rc
                    else:
                        invoice.random_code = None
                else:
                    invoice.random_code = None

            if "prize_status" in payload:
                ps = payload["prize_status"]
                if ps == "void":
                    invoice.prize_status = "void"
                elif ps == invoice.prize_status:
                    pass
                else:
                    return make_response_payload(400, "發票狀態僅允許修改為作廢 (void)")

            invoice.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "更新發票成功", invoice.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/invoices/<int:invoice_id>/items")
    def create_invoice_item(invoice_id):
        """新增發票品項。必填名稱、數量、單價、小計。指向不存在發票時回 400。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            invoice = db.session.get(Invoice, invoice_id)
            if invoice is None:
                return make_response_payload(400, "指向不存在的發票")

            for field in ("name", "quantity", "unit_price", "line_amount"):
                if field not in payload or payload[field] is None:
                    return make_response_payload(400, f"必填欄位缺失: {field}")

            raw_name = str(payload["name"]).strip()
            if not raw_name:
                return make_response_payload(400, "品項名稱不可為空白")
            if len(raw_name) > 150:
                return make_response_payload(400, "品項名稱不可超過 150 字元")

            try:
                quantity = Decimal(str(payload["quantity"]))
                if quantity <= Decimal("0"):
                    return make_response_payload(400, "數量必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "數量必須為數值且大於 0")

            try:
                unit_price = Decimal(str(payload["unit_price"]))
                if unit_price <= Decimal("0"):
                    return make_response_payload(400, "單價必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "單價必須為數值且大於 0")

            try:
                line_amount = Decimal(str(payload["line_amount"]))
                if line_amount <= Decimal("0"):
                    return make_response_payload(400, "小計金額必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "小計金額必須為數值且大於 0")

            item = InvoiceItem(
                invoice_id=invoice.id,
                name=raw_name,
                quantity=quantity,
                unit_price=unit_price,
                line_amount=line_amount,
            )
            db.session.add(item)
            db.session.commit()
            return make_response_payload(201, "新增發票品項成功", item.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/invoices/<int:invoice_id>/items")
    def list_invoice_items(invoice_id):
        """取得指定發票之品項清單。空的回 200 與空清單。"""
        try:
            invoice = db.session.get(Invoice, invoice_id)
            if invoice is None:
                return make_response_payload(404, "找不到該發票", None)

            items = [item.to_dict() for item in invoice.items]
            return make_response_payload(200, "取得發票品項成功", items)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 開獎期別與開獎獎項路由 (Draw Periods & Prizes)
    # -------------------------------------------------------------
    @app.post("/api/draw-periods")
    def create_draw_period():
        """建立開獎期別。必填 period_key。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        raw_key = payload.get("period_key")
        if not raw_key:
            return make_response_payload(400, "必填欄位缺失: period_key")

        period_key = str(raw_key).strip()
        if not re.match(r"^\d{4}-(01|03|05|07|09|11)$", period_key):
            return make_response_payload(
                400, "期別格式錯誤，應為 YYYY-01、YYYY-03、YYYY-05、YYYY-07、YYYY-09 或 YYYY-11"
            )

        try:
            existing = db.session.execute(
                db.select(DrawPeriod).where(DrawPeriod.period_key == period_key)
            ).scalar_one_or_none()
            if existing:
                return make_response_payload(400, "該開獎期別已存在")

            period = DrawPeriod(period_key=period_key)
            db.session.add(period)
            db.session.commit()
            return make_response_payload(201, "建立開獎期別成功", period.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/draw-periods")
    def list_draw_periods():
        """取得開獎期別清單。"""
        try:
            periods = db.session.execute(
                db.select(DrawPeriod).order_by(DrawPeriod.period_key.desc())
            ).scalars().all()
            return make_response_payload(200, "取得開獎期別清單成功", [p.to_dict() for p in periods])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/draw-periods/<int:period_id>")
    def get_draw_period(period_id):
        """取得單一開獎期別與其獎項清單。"""
        try:
            period = db.session.get(DrawPeriod, period_id)
            if period is None:
                return make_response_payload(404, "找不到該開獎期別", None)
            data = period.to_dict()
            data["prizes"] = [prize.to_dict() for prize in period.prizes]
            return make_response_payload(200, "取得開獎期別成功", data)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/draw-periods/<int:period_id>/prizes")
    def create_draw_prize(period_id):
        """新增一筆獎號與獎金。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            period = db.session.get(DrawPeriod, period_id)
            if period is None:
                return make_response_payload(400, "指向不存在的開獎期")

            for field in ("tier", "matching_number", "amount"):
                if field not in payload or payload[field] is None:
                    return make_response_payload(400, f"必填欄位缺失: {field}")

            tier = str(payload["tier"]).strip()
            allowed_tiers = (
                "special", "grand", "first", "second", "third", "fourth", "fifth", "sixth", "extra_sixth"
            )
            if tier not in allowed_tiers:
                return make_response_payload(400, f"獎項類別不合法，僅支援: {', '.join(allowed_tiers)}")

            matching_number = str(payload["matching_number"]).strip()
            if not matching_number:
                return make_response_payload(400, "中獎號碼不可為空白")

            if tier in ("special", "grand", "first"):
                if not re.match(r"^[0-9]{8}$", matching_number):
                    return make_response_payload(400, f"{tier} 獎項之中獎號碼必須為 8 碼數字")

            try:
                amount = Decimal(str(payload["amount"]))
                if amount < Decimal("0"):
                    return make_response_payload(400, "獎金金額不可小於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "獎金金額必須為數值")

            conflict = db.session.execute(
                db.select(DrawPrize).where(
                    DrawPrize.draw_period_id == period_id,
                    DrawPrize.tier == tier,
                    DrawPrize.matching_number == matching_number,
                )
            ).scalar_one_or_none()
            if conflict:
                return make_response_payload(400, "該期別已存在相同獎項與獎號")

            prize = DrawPrize(
                draw_period_id=period_id,
                tier=tier,
                matching_number=matching_number,
                amount=amount,
            )
            db.session.add(prize)
            db.session.commit()
            return make_response_payload(201, "新增開獎獎項成功", prize.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/draw-periods/<int:period_id>/check")
    def check_draw_period_invoices(period_id):
        """對該期所有未作廢且開立日落在該期的發票對獎，回寫 prize_status。回傳 checked_count 與 won_count。"""
        try:
            period = db.session.get(DrawPeriod, period_id)
            if period is None:
                return make_response_payload(400, "指向不存在的開獎期")

            start_date, end_date = get_period_date_range(period.period_key)

            invoices = db.session.execute(
                db.select(Invoice).where(
                    Invoice.issued_on >= start_date,
                    Invoice.issued_on < end_date,
                    Invoice.prize_status != "void",
                )
            ).scalars().all()

            prizes = db.session.execute(
                db.select(DrawPrize).where(DrawPrize.draw_period_id == period_id)
            ).scalars().all()

            checked_count = 0
            won_count = 0

            for inv in invoices:
                checked_count += 1
                winning = find_winning_prize(inv, prizes)
                if winning:
                    won_count += 1
                    if inv.prize_status != "claimed":
                        inv.prize_status = "won"
                        inv.updated_at = datetime.now(timezone.utc)
                else:
                    if inv.prize_status != "claimed":
                        inv.prize_status = "lost"
                        inv.updated_at = datetime.now(timezone.utc)

            db.session.commit()
            return make_response_payload(
                200, "發票對獎完成", {"checked_count": checked_count, "won_count": won_count}
            )
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫對獎失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/invoices/<int:invoice_id>/prize-income")
    def claim_invoice_prize_income(invoice_id):
        """為已中獎之發票建立中獎入帳，並將發票改為 claimed。同一交易中完成。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        try:
            invoice = db.session.get(Invoice, invoice_id)
            if invoice is None:
                return make_response_payload(404, "找不到該發票", None)

            if invoice.prize_status == "claimed":
                return make_response_payload(400, "該發票中獎獎金已領取")
            if invoice.prize_status != "won":
                return make_response_payload(400, "發票狀態非中獎 (won)，無法建立中獎入帳")

            existing_income = db.session.execute(
                db.select(Income).where(Income.invoice_id == invoice.id)
            ).scalar_one_or_none()
            if existing_income:
                return make_response_payload(400, "該發票已有入帳紀錄，不可重複領獎")

            for req_field in ("category_id", "account_id"):
                if req_field not in payload or payload[req_field] is None:
                    return make_response_payload(400, f"必填欄位缺失: {req_field}")

            category = db.session.get(IncomeCategory, payload["category_id"])
            if category is None:
                return make_response_payload(400, "指定的入帳分類不存在")

            account = db.session.get(Account, payload["account_id"])
            if account is None:
                return make_response_payload(400, "指定的帳戶不存在")

            period_key = compute_period_key(invoice.issued_on)
            period = db.session.execute(
                db.select(DrawPeriod).where(DrawPeriod.period_key == period_key)
            ).scalar_one_or_none()
            if not period:
                return make_response_payload(400, f"找不到開立日對應之開獎期別 ({period_key})")

            prizes = db.session.execute(
                db.select(DrawPrize).where(DrawPrize.draw_period_id == period.id)
            ).scalars().all()
            winning_prize = find_winning_prize(invoice, prizes)
            if not winning_prize or winning_prize.amount <= Decimal("0"):
                return make_response_payload(400, "查無此發票之中獎獎項或獎金金額")

            prize_amount = winning_prize.amount

            raw_received = payload.get("received_on")
            if raw_received is not None:
                try:
                    received_date = date.fromisoformat(str(raw_received).strip())
                except ValueError:
                    return make_response_payload(400, "入帳日期格式錯誤，應為 YYYY-MM-DD")
            else:
                received_date = date.today()

            source = payload.get("source")
            if source is not None:
                source = str(source).strip() or None
            if not source:
                source = f"統一發票中獎 ({invoice.number})"

            note = payload.get("note")
            if note is not None:
                note = str(note).strip() or None
            if not note:
                note = f"發票號碼 {invoice.number} 中獎獎金"

            income = Income(
                received_on=received_date,
                amount=prize_amount,
                currency=invoice.currency,
                fx_rate_to_twd=invoice.fx_rate_to_twd,
                category_id=category.id,
                account_id=account.id,
                invoice_id=invoice.id,
                source=source,
                note=note,
            )
            invoice.prize_status = "claimed"
            invoice.updated_at = datetime.now(timezone.utc)

            db.session.add(income)
            db.session.commit()
            return make_response_payload(201, "建立中獎入帳成功", income.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 輔助函式：投資標的持有股數與平均成本計算
    # -------------------------------------------------------------
    def replay_instrument_holding(instrument_id: int):
        """重播指定標的的所有未作廢交易，回傳 (當前持有股數, 每股平均成本, 總成本)。"""
        trades = db.session.execute(
            db.select(Trade).where(
                Trade.instrument_id == instrument_id,
                Trade.voided_at.is_(None),
            ).order_by(Trade.traded_on.asc(), Trade.id.asc())
        ).scalars().all()

        current_qty = Decimal("0")
        total_cost = Decimal("0")

        for t in trades:
            t_type = t.trade_type
            if t_type in ("buy", "drip"):
                qty = t.quantity or Decimal("0")
                price = t.price or Decimal("0")
                current_qty += qty
                total_cost += (qty * price)
            elif t_type == "sell":
                qty = t.quantity or Decimal("0")
                if current_qty > Decimal("0"):
                    unit_cost = total_cost / current_qty
                    total_cost -= (qty * unit_cost)
                current_qty -= qty
                if current_qty <= Decimal("0"):
                    current_qty = Decimal("0")
                    total_cost = Decimal("0")
            elif t_type == "stock_dividend":
                qty = t.quantity or Decimal("0")
                current_qty += qty
            elif t_type in ("split", "merge"):
                ratio = t.ratio or Decimal("1")
                current_qty = current_qty * ratio
            elif t_type == "capital_reduction":
                if t.quantity is not None and t.quantity > Decimal("0"):
                    qty = t.quantity
                    if current_qty > Decimal("0"):
                        unit_cost = total_cost / current_qty
                        total_cost -= (qty * unit_cost)
                    current_qty -= qty
                elif t.ratio is not None and t.ratio > Decimal("0"):
                    current_qty = current_qty * t.ratio
                    total_cost = total_cost * t.ratio
                if current_qty <= Decimal("0"):
                    current_qty = Decimal("0")
                    total_cost = Decimal("0")
            elif t_type == "cash_dividend":
                pass

        avg_cost = (total_cost / current_qty) if current_qty > Decimal("0") else Decimal("0")
        return current_qty, avg_cost, total_cost

    # -------------------------------------------------------------
    # 投資標的路由 (Instruments)
    # -------------------------------------------------------------
    @app.post("/api/instruments")
    def create_instrument():
        """新增投資標的。必填 market、symbol、name、currency。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        for field in ("market", "symbol", "name", "currency"):
            if field not in payload or payload[field] is None:
                return make_response_payload(400, f"必填欄位缺失: {field}")

        market = str(payload["market"]).strip()
        allowed_markets = ("tw_stock", "us_stock", "fund", "other")
        if market not in allowed_markets:
            return make_response_payload(400, f"market 僅允許: {', '.join(allowed_markets)}")

        symbol = str(payload["symbol"]).strip().upper()
        if not symbol:
            return make_response_payload(400, "代號不可為空白")
        if len(symbol) > 30:
            return make_response_payload(400, "代號長度不可超過 30 字元")

        name = str(payload["name"]).strip()
        if not name:
            return make_response_payload(400, "標的名稱不可為空白")
        if len(name) > 100:
            return make_response_payload(400, "標的名稱不可超過 100 字元")

        currency = str(payload["currency"]).strip().upper()
        if len(currency) != 3:
            return make_response_payload(400, "幣別代碼必須為 3 碼英文字母")

        try:
            conflict = db.session.execute(
                db.select(Instrument).where(
                    Instrument.market == market,
                    Instrument.symbol == symbol,
                )
            ).scalar_one_or_none()
            if conflict:
                return make_response_payload(400, "同一市場中已存在相同代號之標的")

            inst = Instrument(
                market=market,
                symbol=symbol,
                name=name,
                currency=currency,
            )
            db.session.add(inst)
            db.session.commit()
            return make_response_payload(201, "新增投資標的成功", inst.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/instruments")
    def list_instruments():
        """查詢投資標的清單。"""
        try:
            instruments = db.session.execute(
                db.select(Instrument).order_by(Instrument.id.asc())
            ).scalars().all()
            return make_response_payload(200, "取得投資標的清單成功", [inst.to_dict() for inst in instruments])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/instruments/<int:instrument_id>")
    def get_instrument(instrument_id):
        """查詢單一投資標的。"""
        try:
            inst = db.session.get(Instrument, instrument_id)
            if inst is None:
                return make_response_payload(404, "找不到該投資標的", None)
            return make_response_payload(200, "取得投資標的成功", inst.to_dict())
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/instruments/<int:instrument_id>/holding")
    def get_instrument_holding(instrument_id):
        """取得標的目前持有數量與平均成本。忽略 voided_at 有值之交易，依 traded_on, id 重播。"""
        try:
            inst = db.session.get(Instrument, instrument_id)
            if inst is None:
                return make_response_payload(404, "找不到該投資標的", None)

            current_qty, avg_cost, total_cost = replay_instrument_holding(instrument_id)

            data = {
                "instrument_id": inst.id,
                "symbol": inst.symbol,
                "name": inst.name,
                "currency": inst.currency,
                "quantity": float(current_qty),
                "average_cost": float(round(avg_cost, 4)) if avg_cost else 0.0,
                "total_cost": float(round(total_cost, 4)) if total_cost else 0.0,
            }
            return make_response_payload(200, "取得標的持有資訊成功", data)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 投資交易路由 (Trades)
    # -------------------------------------------------------------
    @app.post("/api/trades")
    def create_trade():
        """新增投資交易。依交易種類驗證參數，並於 sell 或 capital_reduction 檢驗持股不得為負。"""
        if not request.is_json:
            return make_response_payload(400, "請傳送合法的 JSON 資料")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法的 JSON 物件")

        for field in ("instrument_id", "account_id", "trade_type", "traded_on", "currency", "fx_rate_to_twd"):
            if field not in payload or payload[field] is None:
                return make_response_payload(400, f"必填欄位缺失: {field}")

        try:
            instrument_id = int(payload["instrument_id"])
        except (ValueError, TypeError):
            return make_response_payload(400, "instrument_id 必須為整數")

        try:
            account_id = int(payload["account_id"])
        except (ValueError, TypeError):
            return make_response_payload(400, "account_id 必須為整數")

        inst = db.session.get(Instrument, instrument_id)
        if not inst:
            return make_response_payload(400, "指定的投資標的不存在")

        acc = db.session.get(Account, account_id)
        if not acc:
            return make_response_payload(400, "指定的帳戶不存在")

        trade_type = str(payload["trade_type"]).strip()
        allowed_trade_types = (
            "buy", "sell", "cash_dividend", "stock_dividend", "drip", "split", "merge", "capital_reduction"
        )
        if trade_type not in allowed_trade_types:
            return make_response_payload(400, f"不合法的交易種類，僅允許: {', '.join(allowed_trade_types)}")

        try:
            traded_on = date.fromisoformat(str(payload["traded_on"]).strip())
        except ValueError:
            return make_response_payload(400, "交易日期格式錯誤，應為 YYYY-MM-DD")

        currency = str(payload["currency"]).strip().upper()
        if len(currency) != 3:
            return make_response_payload(400, "幣別代碼必須為 3 碼英文字母")

        try:
            fx_rate_to_twd = Decimal(str(payload["fx_rate_to_twd"]))
            if fx_rate_to_twd <= Decimal("0"):
                return make_response_payload(400, "匯率必須大於 0")
        except (InvalidOperation, TypeError, ValueError):
            return make_response_payload(400, "匯率必須為數值且大於 0")

        # 數值欄位解析（null 與省略相同）
        quantity = None
        if payload.get("quantity") is not None:
            try:
                quantity = Decimal(str(payload["quantity"]))
                if quantity <= Decimal("0"):
                    return make_response_payload(400, "數量必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "數量必須為數值且大於 0")

        price = None
        if payload.get("price") is not None:
            try:
                price = Decimal(str(payload["price"]))
                if price <= Decimal("0"):
                    return make_response_payload(400, "價格必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "價格必須為數值且大於 0")

        ratio = None
        if payload.get("ratio") is not None:
            try:
                ratio = Decimal(str(payload["ratio"]))
                if ratio <= Decimal("0"):
                    return make_response_payload(400, "比例必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "比例必須為數值且大於 0")

        cash_amount = None
        if payload.get("cash_amount") is not None:
            try:
                cash_amount = Decimal(str(payload["cash_amount"]))
                if cash_amount <= Decimal("0"):
                    return make_response_payload(400, "現金金額必須大於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "現金金額必須為數值且大於 0")

        fee = None
        if payload.get("fee") is not None:
            try:
                fee = Decimal(str(payload["fee"]))
                if fee < Decimal("0"):
                    return make_response_payload(400, "手續費不可小於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "手續費必須為數值且不可小於 0")

        tax = None
        if payload.get("tax") is not None:
            try:
                tax = Decimal(str(payload["tax"]))
                if tax < Decimal("0"):
                    return make_response_payload(400, "稅額不可小於 0")
            except (InvalidOperation, TypeError, ValueError):
                return make_response_payload(400, "稅額必須為數值且不可小於 0")

        # 依交易種類檢查必要欄位
        if trade_type in ("buy", "sell", "drip"):
            if quantity is None:
                return make_response_payload(400, f"{trade_type} 交易必須提供大於 0 的數量 (quantity)")
            if price is None:
                return make_response_payload(400, f"{trade_type} 交易必須提供大於 0 的價格 (price)")
        elif trade_type == "stock_dividend":
            if quantity is None:
                return make_response_payload(400, "stock_dividend 配股交易必須提供大於 0 的數量 (quantity)")
        elif trade_type in ("split", "merge"):
            if ratio is None:
                return make_response_payload(400, f"{trade_type} 交易必須提供大於 0 的比例 (ratio)")
        elif trade_type == "cash_dividend":
            if cash_amount is None:
                return make_response_payload(400, "cash_dividend 現金股利交易必須提供大於 0 的現金金額 (cash_amount)")
        elif trade_type == "capital_reduction":
            if quantity is None and ratio is None and cash_amount is None:
                return make_response_payload(400, "減資交易必須提供數量 (quantity)、比例 (ratio) 或現金金額 (cash_amount)")

        # 賣出與減資若會使持有小於 0，回 400
        current_holding_qty, _, _ = replay_instrument_holding(instrument_id)
        if trade_type == "sell":
            if current_holding_qty < quantity:
                return make_response_payload(
                    400, f"賣出數量 ({quantity}) 超過目前持有數量 ({current_holding_qty})，無法賣出"
                )
        elif trade_type == "capital_reduction":
            if quantity is not None and current_holding_qty < quantity:
                return make_response_payload(
                    400, f"減資數量 ({quantity}) 超過目前持有數量 ({current_holding_qty})"
                )
            elif current_holding_qty <= Decimal("0"):
                return make_response_payload(400, "目前未持有該標的，無法進行減資")

        # 判斷是否連動建立入帳 (post_income)
        post_income = payload.get("post_income")
        should_post_income = (
            post_income in (True, "true", "True", 1)
            and trade_type in ("cash_dividend", "capital_reduction")
            and (cash_amount is not None and cash_amount > Decimal("0"))
        )

        income_category = None
        if should_post_income:
            income_category_id = payload.get("income_category_id")
            if not income_category_id:
                return make_response_payload(400, "post_income 為真時，必填 income_category_id")
            try:
                income_category = db.session.get(IncomeCategory, int(income_category_id))
            except (ValueError, TypeError):
                return make_response_payload(400, "income_category_id 必須為整數")
            if not income_category:
                return make_response_payload(400, "指定的入帳分類不存在")

        try:
            trade = Trade(
                instrument_id=instrument_id,
                account_id=account_id,
                trade_type=trade_type,
                traded_on=traded_on,
                quantity=quantity,
                price=price,
                cash_amount=cash_amount,
                ratio=ratio,
                fee=fee,
                tax=tax,
                currency=currency,
                fx_rate_to_twd=fx_rate_to_twd,
            )
            db.session.add(trade)

            if should_post_income:
                db.session.flush()
                income_source = payload.get("source") or f"{inst.name} ({inst.symbol})"
                income_note = (
                    payload.get("note")
                    or f"{'現金股利' if trade_type == 'cash_dividend' else '減資退還現金'}"
                )
                income = Income(
                    received_on=traded_on,
                    amount=cash_amount,
                    currency=currency,
                    fx_rate_to_twd=fx_rate_to_twd,
                    category_id=income_category.id,
                    account_id=account_id,
                    trade_id=trade.id,
                    source=income_source,
                    note=income_note,
                )
                db.session.add(income)

            db.session.commit()
            return make_response_payload(201, "新增交易成功", trade.to_dict())
        except IntegrityError:
            db.session.rollback()
            return make_response_payload(400, "資料格式不合法或違反約束條件")
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫寫入失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.get("/api/trades")
    def list_trades():
        """查詢交易清單。可依 instrument_id 與 account_id 篩選。"""
        try:
            stmt = db.select(Trade)

            instrument_id = request.args.get("instrument_id")
            if instrument_id:
                try:
                    stmt = stmt.where(Trade.instrument_id == int(instrument_id))
                except ValueError:
                    return make_response_payload(400, "instrument_id 必須為整數")

            account_id = request.args.get("account_id")
            if account_id:
                try:
                    stmt = stmt.where(Trade.account_id == int(account_id))
                except ValueError:
                    return make_response_payload(400, "account_id 必須為整數")

            stmt = stmt.order_by(Trade.traded_on.desc(), Trade.id.desc())
            trades = db.session.execute(stmt).scalars().all()
            return make_response_payload(200, "取得交易清單成功", [t.to_dict() for t in trades])
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    @app.post("/api/trades/<int:trade_id>/void")
    def void_trade(trade_id):
        """將指定交易作廢。若已有入帳紀錄則回傳 400，不可作廢。"""
        try:
            trade = db.session.get(Trade, trade_id)
            if trade is None:
                return make_response_payload(404, "找不到該筆交易", None)

            if trade.voided_at is not None:
                return make_response_payload(400, "該筆交易已作廢")

            linked_income = db.session.execute(
                db.select(Income).where(Income.trade_id == trade.id)
            ).scalar_one_or_none()
            if linked_income:
                return make_response_payload(400, "此筆交易已有對應入帳紀錄，無法作廢")

            trade.voided_at = datetime.now(timezone.utc)
            trade.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response_payload(200, "交易作廢成功", trade.to_dict())
        except OperationalError as exc:
            db.session.rollback()
            app.logger.error("資料庫更新失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 月度生活現金流摘要路由 (Monthly Summary)
    # -------------------------------------------------------------
    @app.get("/api/summary")
    def get_monthly_summary():
        """查詢指定月份之生活現金流摘要（入帳合計與花費合計）。查詢參數 month 必填 (YYYY-MM)。"""
        raw_month = request.args.get("month")
        if not raw_month or not raw_month.strip():
            return make_response_payload(400, "缺少必填查詢參數: month")

        month_str = raw_month.strip()
        match = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", month_str)
        if not match:
            return make_response_payload(400, "月份格式錯誤，應為 YYYY-MM (例如 2026-03)")

        year = int(match.group(1))
        m = int(match.group(2))
        start_date = date(year, m, 1)
        if m == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, m + 1, 1)

        try:
            incomes = db.session.execute(
                db.select(Income).where(
                    Income.received_on >= start_date,
                    Income.received_on < end_date,
                )
            ).scalars().all()

            expenses = db.session.execute(
                db.select(Expense).where(
                    Expense.spent_on >= start_date,
                    Expense.spent_on < end_date,
                )
            ).scalars().all()

            income_twd = sum((inc.amount * inc.fx_rate_to_twd for inc in incomes), Decimal("0"))
            expense_twd = sum((exp.amount * exp.fx_rate_to_twd for exp in expenses), Decimal("0"))

            data = {
                "month": month_str,
                "income_twd": float(income_twd),
                "expense_twd": float(expense_twd),
            }
            return make_response_payload(200, "取得月度生活現金流摘要成功", data)
        except OperationalError as exc:
            app.logger.error("資料庫查詢失敗: %s", exc, exc_info=True)
            return make_response_payload(500, "資料庫暫時連不上", None)

    # -------------------------------------------------------------
    # 商品資源路由 (保留既有 mock 項目以維持向後相容)
    # -------------------------------------------------------------
    items = [dict(item) for item in ITEMS]
    _next_item_id = max((item["id"] for item in items), default=100) + 1

    _SORT_SPECS = {
        "id": ("id", False),
        "-id": ("id", True),
        "price": ("price", False),
        "price_asc": ("price", False),
        "+price": ("price", False),
        "-price": ("price", True),
        "price_desc": ("price", True),
        "name": ("name", False),
        "name_asc": ("name", False),
        "-name": ("name", True),
        "name_desc": ("name", True),
        "created_at": ("created_at", False),
        "-created_at": ("created_at", True),
    }
    _SORT_HINT = "price、price_asc、-price、price_desc、name、-name、created_at、-created_at、id 或 -id"

    def find_item(item_id):
        for item in items:
            if item["id"] == item_id:
                return item
        return None

    def _parse_item_query():
        filters = {}
        raw_category = request.args.get("category")
        if raw_category is not None and raw_category.strip() != "":
            category = raw_category.strip()
            if category not in ALLOWED_CATEGORIES:
                return None, None, "category 不在允許的分類白名單內"
            filters["category"] = category

        min_price, error = parse_int_query(request.args.get("min_price"), "min_price")
        if error:
            return None, None, error

        max_price, error = parse_int_query(request.args.get("max_price"), "max_price")
        if error:
            return None, None, error

        if min_price is not None and max_price is not None and min_price > max_price:
            return None, None, "min_price 不可大於 max_price"

        if min_price is not None:
            filters["min_price"] = min_price
        if max_price is not None:
            filters["max_price"] = max_price

        in_stock, error = parse_bool_query(request.args.get("in_stock"), "in_stock")
        if error:
            return None, None, error
        if in_stock is not None:
            filters["in_stock"] = in_stock

        raw_sort = request.args.get("sort")
        sort_key = None
        if raw_sort is not None and raw_sort.strip() != "":
            sort_key = raw_sort.strip()
            if sort_key not in _SORT_SPECS:
                return None, None, f"sort 必須為 {_SORT_HINT}"

        return filters, sort_key, None

    def _select_items(filters, sort_key):
        matched = []
        for item in items:
            if "category" in filters and item["category"] != filters["category"]:
                continue
            if "min_price" in filters and item["price"] < filters["min_price"]:
                continue
            if "max_price" in filters and item["price"] > filters["max_price"]:
                continue
            if "in_stock" in filters and item["in_stock"] is not filters["in_stock"]:
                continue
            matched.append(item)

        if sort_key is None:
            return matched

        field, reverse = _SORT_SPECS[sort_key]
        return sorted(matched, key=lambda item: (item[field], item["id"]), reverse=reverse)

    @app.get("/api/items")
    def list_items():
        filters, sort_key, error = _parse_item_query()
        if error:
            return make_response_payload(400, error)

        matched = _select_items(filters, sort_key)
        meta = {"total": len(matched), "filters_applied": filters}
        if sort_key is not None:
            meta["sort"] = sort_key
        return make_response_payload(200, "取得商品清單成功", matched, meta=meta)

    @app.get("/api/items/<int:item_id>")
    def get_item(item_id):
        item = find_item(item_id)
        if item is None:
            return make_response_payload(404, "找不到這一筆")
        return make_response_payload(200, "取得商品成功", item)

    @app.get("/api/items/<int:item_id>/reviews")
    def list_item_reviews(item_id):
        if find_item(item_id) is None:
            return make_response_payload(404, "找不到這一筆")
        matched = [review for review in REVIEWS if review["item_id"] == item_id]
        meta = {"total": len(matched), "item_id": item_id}
        return make_response_payload(200, "取得商品評論成功", matched, meta=meta)

    @app.post("/api/items")
    def create_item():
        nonlocal _next_item_id

        if not request.is_json:
            return make_response_payload(400, "Content-Type 必須為 application/json")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return make_response_payload(400, "未傳送合法 JSON")

        raw_name = payload.get("name")
        if not isinstance(raw_name, str):
            return make_response_payload(400, "缺少必填欄位 name")
        name = raw_name.strip()
        if name == "":
            return make_response_payload(400, "name 不可為空白")

        if "category" not in payload or payload.get("category") is None:
            return make_response_payload(400, "缺少必填欄位 category")
        raw_category = payload["category"]
        if not isinstance(raw_category, str):
            return make_response_payload(400, "category 必須為字串")
        category = raw_category.strip()
        if category not in ALLOWED_CATEGORIES:
            return make_response_payload(400, "category 不在允許的分類白名單內")

        if "price" not in payload or payload.get("price") is None:
            return make_response_payload(400, "缺少必填欄位 price")
        raw_price = payload["price"]
        if isinstance(raw_price, bool) or not isinstance(raw_price, int):
            return make_response_payload(400, "price 必須為整數")
        if raw_price < 0:
            return make_response_payload(400, "price 不可為負數")

        if "in_stock" in payload and payload["in_stock"] is not None:
            in_stock = payload["in_stock"]
            if not isinstance(in_stock, bool):
                return make_response_payload(400, "in_stock 必須為布林值")
        else:
            in_stock = True

        if "tags" in payload and payload["tags"] is not None:
            tags = payload["tags"]
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                return make_response_payload(400, "tags 必須為字串清單")
            tags = list(tags)
        else:
            tags = []

        item = {
            "id": _next_item_id,
            "name": name,
            "category": category,
            "price": raw_price,
            "in_stock": in_stock,
            "tags": tags,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _next_item_id += 1
        items.append(item)
        return make_response_payload(201, "新增商品成功", item)

    # -------------------------------------------------------------
    # 錯誤處理常式
    # -------------------------------------------------------------
    @app.errorhandler(404)
    def handle_not_found(_error):
        """不存在的路徑一律回傳 JSON，避免 Flask 預設 HTML。"""
        return make_response_payload(404, "找不到這一筆", None)

    @app.errorhandler(500)
    def handle_internal_error(_error):
        """未處理例外一律回傳 JSON，避免堆疊或 HTML 外洩。"""
        return make_response_payload(500, "伺服器內部錯誤", None)

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        return make_response_payload(405, "不支援的請求方法", None)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
