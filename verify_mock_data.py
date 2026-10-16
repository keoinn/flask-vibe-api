"""驗證 mock_data 的資料契約與查詢參數轉型。"""

import mock_data as m


def verify_items():
    """驗證 ITEMS 筆數、必填欄位與分類合規性。"""
    assert len(m.ITEMS) >= 6, "ITEMS 數量不足 6 筆"
    required_keys = {"id", "name", "category", "price", "in_stock", "tags", "created_at"}
    for item in m.ITEMS:
        assert required_keys.issubset(item.keys()), f"缺少契約欄位: {item}"
        assert item["category"] in m.ALLOWED_CATEGORIES, f"非法分類: {item['category']}"
        assert isinstance(item["price"], int) and item["price"] >= 0, "價格型別或範圍錯誤"
        assert isinstance(item["in_stock"], bool), "in_stock 必須為 bool"
        assert isinstance(item["tags"], list), "tags 必須為 list"


def verify_reviews():
    """驗證 REVIEWS 關聯與評分範圍 (1~5)。"""
    item_ids = {item["id"] for item in m.ITEMS}
    for review in m.REVIEWS:
        assert review["item_id"] in item_ids, f"評論關聯到不存在的 item_id: {review['item_id']}"
        assert 1 <= review["rating"] <= 5, "rating 超出 1~5 範圍"


def verify_query_parsers():
    """驗證安全轉型防呆函式。"""
    value, error = m.parse_int_query("100", "min_price", min_val=0)
    assert value == 100 and error is None, "正常整數解析失敗"

    invalid_value, error_message = m.parse_int_query("cheap", "min_price", min_val=0)
    assert invalid_value is None and error_message is not None, "非法整數未正確攔截"

    bool_value, bool_error = m.parse_bool_query("true", "in_stock")
    assert bool_value is True and bool_error is None, "布林值解析失敗"


if __name__ == "__main__":
    verify_items()
    verify_reviews()
    verify_query_parsers()
    print("✅ 驗證通過！Mock Data 結構、分類白名單與 Query 轉型防呆 100% 符合 API Contract！")
