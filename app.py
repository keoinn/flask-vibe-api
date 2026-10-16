"""任務與商品資源的最小可行 RESTful API。

使用記憶體清單保存資料，端點本身不依賴 session，符合無狀態原則。
"""

from datetime import datetime

from flask import Flask, jsonify, request

from mock_data import ALLOWED_CATEGORIES, ITEMS, REVIEWS, parse_bool_query, parse_int_query

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False

tasks = [
    {
        "id": 1,
        "title": "熟悉 Flask 路由",
        "description": "建立健康檢查與任務查詢端點",
    },
    {
        "id": 2,
        "title": "整理 API 回應格式",
        "description": "統一封裝 status、message 與 data",
    },
]
_next_id = 3

items = [dict(item) for item in ITEMS]
_next_item_id = max((item["id"] for item in items), default=100) + 1

# sort 查詢值 -> (欄位, 是否由大到小)。別名與主名稱指向同一規則。
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


def make_response_payload(status, message, data=None, status_code=200, meta=None):
    """統一封裝 JSON 回應與 HTTP 狀態碼。

    單筆資源只帶 status、message、data。查詢清單時可傳入 meta，例如：

        {"total": 2, "filters_applied": {"category": "books", "in_stock": True}}
    """
    body = {"status": status, "message": message, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status_code


def find_task(task_id):
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


@app.get("/api/health")
def health_check():
    """回傳伺服器運行狀態與當前時間。"""
    payload = {
        "server": "running",
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return make_response_payload("success", "伺服器運行正常", payload)


@app.get("/api/tasks")
def list_tasks():
    """取得所有任務。"""
    return make_response_payload("success", "取得任務清單成功", tasks)


@app.post("/api/tasks")
def create_task():
    """新增一筆任務。title 為必填，description 為選填。"""
    global _next_id

    if not request.is_json:
        return make_response_payload(
            "error",
            "Content-Type 必須為 application/json",
            status_code=400,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return make_response_payload("error", "未傳送合法 JSON", status_code=400)

    raw_title = payload.get("title")
    if not isinstance(raw_title, str):
        return make_response_payload("error", "缺少必填欄位 title", status_code=400)

    title = raw_title.strip()
    if title == "":
        return make_response_payload("error", "title 不可為空白", status_code=400)

    description = payload.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        return make_response_payload("error", "description 必須為字串", status_code=400)

    task = {
        "id": _next_id,
        "title": title,
        "description": description,
    }
    _next_id += 1
    tasks.append(task)
    return make_response_payload("success", "新增任務成功", task, 201)


@app.get("/api/tasks/<int:task_id>")
def get_task(task_id):
    """依 ID 查詢單一任務。"""
    task = find_task(task_id)
    if task is None:
        return make_response_payload("error", "找不到指定任務", status_code=404)
    return make_response_payload("success", "取得任務成功", task)


def find_item(item_id):
    for item in items:
        if item["id"] == item_id:
            return item
    return None


def _parse_item_query():
    """解析商品清單的查詢參數。

    成功時回傳 (filters, sort_key, None)。轉型或範圍不合法時回傳
    (None, None, 繁體中文錯誤訊息)，且不會因型別錯誤拋出例外。
    """
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
    """依已驗證的條件篩選，再依 sort 產生新清單，不改動原始順序。"""
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
    """依 category、價格區間、in_stock 過濾，並以 sort 排序。"""
    filters, sort_key, error = _parse_item_query()
    if error:
        return make_response_payload("error", error, status_code=400)

    matched = _select_items(filters, sort_key)
    meta = {"total": len(matched), "filters_applied": filters}
    if sort_key is not None:
        meta["sort"] = sort_key
    return make_response_payload("success", "取得商品清單成功", matched, meta=meta)


@app.get("/api/items/<int:item_id>")
def get_item(item_id):
    """依整數 ID 取得單一商品。"""
    item = find_item(item_id)
    if item is None:
        return make_response_payload("error", "找不到指定商品", status_code=404)
    return make_response_payload("success", "取得商品成功", item)


@app.get("/api/items/<int:item_id>/reviews")
def list_item_reviews(item_id):
    """取得指定商品的評論。路徑必須先對到存在的商品。"""
    if find_item(item_id) is None:
        return make_response_payload("error", "找不到指定商品", status_code=404)
    matched = [review for review in REVIEWS if review["item_id"] == item_id]
    meta = {"total": len(matched), "item_id": item_id}
    return make_response_payload("success", "取得商品評論成功", matched, meta=meta)


@app.post("/api/items")
def create_item():
    """新增商品。name、category、price 為必填。"""
    global _next_item_id

    if not request.is_json:
        return make_response_payload(
            "error",
            "Content-Type 必須為 application/json",
            status_code=400,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return make_response_payload("error", "未傳送合法 JSON", status_code=400)

    raw_name = payload.get("name")
    if not isinstance(raw_name, str):
        return make_response_payload("error", "缺少必填欄位 name", status_code=400)
    name = raw_name.strip()
    if name == "":
        return make_response_payload("error", "name 不可為空白", status_code=400)

    if "category" not in payload or payload.get("category") is None:
        return make_response_payload("error", "缺少必填欄位 category", status_code=400)
    raw_category = payload["category"]
    if not isinstance(raw_category, str):
        return make_response_payload("error", "category 必須為字串", status_code=400)
    category = raw_category.strip()
    if category not in ALLOWED_CATEGORIES:
        return make_response_payload(
            "error",
            "category 不在允許的分類白名單內",
            status_code=400,
        )

    if "price" not in payload or payload.get("price") is None:
        return make_response_payload("error", "缺少必填欄位 price", status_code=400)
    raw_price = payload["price"]
    if isinstance(raw_price, bool) or not isinstance(raw_price, int):
        return make_response_payload("error", "price 必須為整數", status_code=400)
    if raw_price < 0:
        return make_response_payload("error", "price 不可為負數", status_code=400)

    if "in_stock" in payload and payload["in_stock"] is not None:
        in_stock = payload["in_stock"]
        if not isinstance(in_stock, bool):
            return make_response_payload("error", "in_stock 必須為布林值", status_code=400)
    else:
        in_stock = True

    if "tags" in payload and payload["tags"] is not None:
        tags = payload["tags"]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            return make_response_payload("error", "tags 必須為字串清單", status_code=400)
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
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _next_item_id += 1
    items.append(item)
    return make_response_payload("success", "新增商品成功", item, 201)


@app.errorhandler(404)
def handle_not_found(_error):
    """不存在的路徑一律回傳 JSON，避免 Flask 預設 HTML。"""
    return make_response_payload("error", "找不到指定的路徑", status_code=404)


@app.errorhandler(500)
def handle_internal_error(_error):
    """未處理例外一律回傳 JSON，避免堆疊或 HTML 外洩。"""
    return make_response_payload("error", "伺服器內部錯誤", status_code=500)


@app.errorhandler(405)
def handle_method_not_allowed(_error):
    return make_response_payload("error", "不支援的請求方法", status_code=405)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
