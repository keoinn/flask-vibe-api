"""商品與評論的記憶體模擬資料，以及共用的 API 契約輔助函式。

商品資源為 `/api/items`，評論掛在 `/api/items/<item_id>/reviews`。
清單查詢的回應需透過 meta 帶出 total 與 filters_applied。
"""

from datetime import datetime
from typing import Any

from flask import Response, jsonify

ALLOWED_CATEGORIES: set[str] = {"electronics", "books", "accessories"}

ITEMS: list[dict[str, Any]] = [
    {
        "id": 101,
        "name": "無線降噪耳機",
        "category": "electronics",
        "price": 3990,
        "in_stock": True,
        "tags": ["audio", "wireless"],
        "created_at": "2026-01-12T09:30:00+08:00",
    },
    {
        "id": 102,
        "name": "機械式鍵盤",
        "category": "electronics",
        "price": 2490,
        "in_stock": False,
        "tags": ["keyboard", "mechanical"],
        "created_at": "2026-02-03T14:15:00+08:00",
    },
    {
        "id": 103,
        "name": "Python 架構設計",
        "category": "books",
        "price": 680,
        "in_stock": True,
        "tags": ["programming", "python"],
        "created_at": "2026-03-18T11:00:00+08:00",
    },
    {
        "id": 104,
        "name": "REST API 實戰手冊",
        "category": "books",
        "price": 520,
        "in_stock": False,
        "tags": ["api", "backend"],
        "created_at": "2026-04-07T16:45:00+08:00",
    },
    {
        "id": 105,
        "name": "筆電收納包",
        "category": "accessories",
        "price": 890,
        "in_stock": True,
        "tags": ["bag", "laptop"],
        "created_at": "2026-05-21T08:20:00+08:00",
    },
    {
        "id": 106,
        "name": "USB-C 擴充座",
        "category": "accessories",
        "price": 1590,
        "in_stock": False,
        "tags": ["usb-c", "hub"],
        "created_at": "2026-06-30T19:05:00+08:00",
    },
    {
        "id": 107,
        "name": "開放原始碼貼紙組",
        "category": "accessories",
        "price": 0,
        "in_stock": True,
        "tags": ["sticker"],
        "created_at": "2026-07-15T10:00:00+08:00",
    },
]

REVIEWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "item_id": 101,
        "author": "林小安",
        "rating": 5,
        "comment": "降噪效果穩定，長時間配戴也舒服。",
    },
    {
        "id": 2,
        "item_id": 101,
        "author": "陳以恩",
        "rating": 4,
        "comment": "音質清楚，低音稍微偏重。",
    },
    {
        "id": 3,
        "item_id": 103,
        "author": "黃子謙",
        "rating": 5,
        "comment": "範例貼近實務，適合拿來對照專案。",
    },
    {
        "id": 4,
        "item_id": 105,
        "author": "張若瑜",
        "rating": 3,
        "comment": "容量夠用，肩帶可以再厚一點。",
    },
    {
        "id": 5,
        "item_id": 102,
        "author": "吳承恩",
        "rating": 1,
        "comment": "鍵程偏硬，而且目前缺貨。",
    },
    {
        "id": 6,
        "item_id": 104,
        "author": "周品妍",
        "rating": 2,
        "comment": "觀念正確，但範例版本偏舊。",
    },
]

_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}


def _is_strict_int(value: object) -> bool:
    """布林值是 int 的子類別，這裡把兩者分開。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_mock_data() -> None:
    """載入時確認模擬資料符合 Data Schema，避免篩選測試吃到壞資料。"""
    expected_categories = {"electronics", "books", "accessories"}
    if set(ALLOWED_CATEGORIES) != expected_categories:
        raise ValueError("ALLOWED_CATEGORIES 必須正好包含 electronics、books、accessories")

    if len(ITEMS) < 6:
        raise ValueError("ITEMS 至少需要 6 筆商品")
    if len(REVIEWS) < 4:
        raise ValueError("REVIEWS 至少需要 4 筆評論")

    seen_item_ids: set[int] = set()
    categories: set[str] = set()
    stock_states: set[bool] = set()

    for item in ITEMS:
        item_id = item["id"]
        if not _is_strict_int(item_id) or item_id < 101:
            raise ValueError("商品 id 必須為從 101 起跳的整數")
        if item_id in seen_item_ids:
            raise ValueError(f"商品 id {item_id} 重複")
        seen_item_ids.add(item_id)

        name = item["name"]
        if not isinstance(name, str) or name.strip() == "":
            raise ValueError(f"商品 {item_id} 的 name 必須為非空白字串")

        category = item["category"]
        if not isinstance(category, str) or category not in ALLOWED_CATEGORIES:
            raise ValueError(f"商品 {item_id} 的 category 不在允許清單內")
        categories.add(category)

        price = item["price"]
        if not _is_strict_int(price) or price < 0:
            raise ValueError(f"商品 {item_id} 的 price 必須為大於等於 0 的整數")

        in_stock = item["in_stock"]
        if not isinstance(in_stock, bool):
            raise ValueError(f"商品 {item_id} 的 in_stock 必須為布林值")
        stock_states.add(in_stock)

        tags = item["tags"]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"商品 {item_id} 的 tags 必須為字串清單")

        created_at = item["created_at"]
        if not isinstance(created_at, str):
            raise ValueError(f"商品 {item_id} 的 created_at 必須為 ISO 8601 字串")
        try:
            datetime.fromisoformat(created_at)
        except ValueError as exc:
            raise ValueError(f"商品 {item_id} 的 created_at 不是合法的 ISO 8601") from exc

    if categories != expected_categories:
        raise ValueError("ITEMS 必須涵蓋 electronics、books、accessories")
    if stock_states != {True, False}:
        raise ValueError("ITEMS 必須同時包含有庫存與無庫存商品")

    seen_review_ids: set[int] = set()
    for review in REVIEWS:
        review_id = review["id"]
        if not _is_strict_int(review_id):
            raise ValueError("評論 id 必須為整數")
        if review_id in seen_review_ids:
            raise ValueError(f"評論 id {review_id} 重複")
        seen_review_ids.add(review_id)

        item_id = review["item_id"]
        if not _is_strict_int(item_id) or item_id not in seen_item_ids:
            raise ValueError(f"評論 {review_id} 的 item_id 找不到對應商品")

        author = review["author"]
        if not isinstance(author, str) or author.strip() == "":
            raise ValueError(f"評論 {review_id} 的 author 必須為非空白字串")

        rating = review["rating"]
        if not _is_strict_int(rating) or not 1 <= rating <= 5:
            raise ValueError(f"評論 {review_id} 的 rating 必須為 1 到 5 的整數")

        comment = review["comment"]
        if not isinstance(comment, str):
            raise ValueError(f"評論 {review_id} 的 comment 必須為字串")


def make_response_payload(status, message, data=None, meta=None, status_code=200):
    """統一封裝 JSON 回應與 HTTP 狀態碼。

    單筆資源只帶 status、message、data。查詢清單時請傳入 meta，例如：

        {"total": 2, "filters_applied": {"category": "books", "in_stock": True}}
    """
    body: dict[str, Any] = {"status": status, "message": message, "data": data}
    if meta is not None:
        body["meta"] = meta
    response: Response = jsonify(body)
    return response, status_code


def parse_int_query(raw_val, param_name, default=None, min_val=None):
    """把查詢參數轉成整數。

    缺值或空白回傳 default。轉型失敗或小於 min_val 時不拋出例外，
    回傳 (None, 繁體中文錯誤訊息)。成功時錯誤訊息為 None。
    """
    if raw_val is None:
        return default, None

    if isinstance(raw_val, str):
        stripped = raw_val.strip()
        if stripped == "":
            return default, None
        try:
            parsed = int(stripped)
        except ValueError:
            return None, f"參數 {param_name} 必須為整數"
    elif _is_strict_int(raw_val):
        parsed = raw_val
    else:
        return None, f"參數 {param_name} 必須為整數"

    if min_val is not None and parsed < min_val:
        return None, f"參數 {param_name} 不可小於 {min_val}"
    return parsed, None


def parse_bool_query(raw_val, param_name, default=None):
    """把查詢參數轉成布林值。

    接受 true、false、1、0、yes、no（不分大小寫）。缺值或空白回傳 default。
    轉型失敗時不拋出例外，回傳 (None, 繁體中文錯誤訊息)。
    """
    if raw_val is None:
        return default, None

    if isinstance(raw_val, bool):
        return raw_val, None

    if isinstance(raw_val, str):
        stripped = raw_val.strip()
        if stripped == "":
            return default, None
        token = stripped.casefold()
        if token in _TRUE_TOKENS:
            return True, None
        if token in _FALSE_TOKENS:
            return False, None

    return None, f"參數 {param_name} 必須為布林值（true、false、1、0、yes、no）"


_validate_mock_data()
