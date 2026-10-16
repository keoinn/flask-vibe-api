#!/usr/bin/env python3
"""驗收已部署到雲端的 Flask API。

用法：
    python verify_cloud.py --url https://xxx.vercel.app

只使用 Python 標準庫。JSON 解析用 json，計時用 time，HTTP 用 urllib。
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 30

VALID_ITEM = {
    "name": "雲端驗收耳機",
    "category": "electronics",
    "price": 1890,
    "in_stock": True,
}


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="對已部署的 Flask API 發送線上驗收請求",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="雲端服務基底 URL，例如 https://xxx.vercel.app",
    )
    return parser.parse_args(argv)


def use_color():
    return sys.stdout.isatty()


def paint(text, code):
    if not use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def decode_body(raw):
    """把回應轉成 JSON。不是 JSON 時保留文字，方便看出 HTML 錯誤頁。"""
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def request_json(method, url, payload=None):
    """送出請求。4xx/5xx 仍回傳狀態碼與本文，連線失敗則帶錯誤訊息。"""
    headers = {
        "Accept": "application/json",
        "User-Agent": "flask-vibe-cloud-verify/1.0",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = decode_body(response.read())
            error = None
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = decode_body(exc.read())
        error = None
    except urllib.error.URLError as exc:
        status = None
        body = None
        error = f"連線失敗：{exc.reason}"
    except TimeoutError:
        status = None
        body = None
        error = f"連線逾時（{TIMEOUT_SECONDS} 秒）"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return status, body, error, elapsed_ms


def message_of(body):
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    if isinstance(body, str):
        compact = " ".join(body.split())
        return compact[:160] if compact else "空回應"
    return "無 JSON 訊息"


def envelope_ok(body, expected_status_field):
    return isinstance(body, dict) and body.get("status") == expected_status_field


def check_health(base):
    url = base + "/api/health"
    status, body, error, elapsed_ms = request_json("GET", url)
    lines = [f"GET {url}", f"實際 {status}｜耗時 {elapsed_ms} ms"]
    if error:
        return False, lines + [error]
    data = body.get("data") if isinstance(body, dict) else None
    alive = (
        status == 200
        and envelope_ok(body, "success")
        and isinstance(data, dict)
        and data.get("server") == "running"
    )
    if alive:
        lines.append(message_of(body))
    else:
        lines.append(f"服務未回報運行中：{message_of(body)}")
    return alive, lines


def check_query(base):
    url = base + "/api/items?category=books&sort=price_asc"
    status, body, error, elapsed_ms = request_json("GET", url)
    lines = [f"GET {url}", f"實際 {status}｜耗時 {elapsed_ms} ms"]
    if error:
        return False, lines + [error]
    data = body.get("data") if isinstance(body, dict) else None
    meta = body.get("meta") if isinstance(body, dict) else None
    if status != 200 or not envelope_ok(body, "success") or not isinstance(data, list):
        return False, lines + [f"Query 未被正常解析：{message_of(body)}"]
    if len(data) == 0:
        return False, lines + ["篩選結果為空，category=books 沒有套用到商品清單"]

    prices = []
    for item in data:
        if not isinstance(item, dict) or item.get("category") != "books":
            return False, lines + ["結果含非 books 商品，category 篩選未生效"]
        price = item.get("price")
        if isinstance(price, bool) or not isinstance(price, int):
            return False, lines + ["商品價格不是整數，無法確認排序"]
        prices.append(price)
    if prices != sorted(prices):
        return False, lines + [f"價格不是由低到高：{prices}"]

    if not isinstance(meta, dict):
        return False, lines + ["清單回應缺少 meta，無法確認 filters 與 sort"]
    filters = meta.get("filters_applied")
    if not isinstance(filters, dict) or filters.get("category") != "books":
        return False, lines + ["meta.filters_applied.category 不是 books"]
    if meta.get("sort") != "price_asc":
        return False, lines + ["meta.sort 不是 price_asc"]

    lines.append(f"{len(data)} 筆 books，價格 {' → '.join(str(price) for price in prices)}")
    return True, lines


def check_paths(base):
    """單筆商品與階層式評論都必須命中對應的 Path。"""
    item_url = base + "/api/items/101"
    reviews_url = base + "/api/items/101/reviews"
    lines = []
    passed = True

    status, body, error, elapsed_ms = request_json("GET", item_url)
    lines.append(f"GET {item_url}")
    lines.append(f"實際 {status}｜耗時 {elapsed_ms} ms")
    if error:
        lines.append(error)
        passed = False
    else:
        data = body.get("data") if isinstance(body, dict) else None
        if status == 200 and envelope_ok(body, "success") and isinstance(data, dict) and data.get("id") == 101:
            lines.append(f"Path 解析為商品 {data.get('id')}（{data.get('name')}）")
        else:
            lines.append(f"Path 未取得 id 101：{message_of(body)}")
            passed = False

    status, body, error, elapsed_ms = request_json("GET", reviews_url)
    lines.append(f"GET {reviews_url}")
    lines.append(f"實際 {status}｜耗時 {elapsed_ms} ms")
    if error:
        lines.append(error)
        return False, lines
    data = body.get("data") if isinstance(body, dict) else None
    if status != 200 or not envelope_ok(body, "success") or not isinstance(data, list):
        lines.append(f"階層式路由未回傳評論清單：{message_of(body)}")
        return False, lines
    if len(data) == 0:
        lines.append("評論清單為空，/reviews 沒有帶回商品 101 的評論")
        return False, lines
    for review in data:
        if not isinstance(review, dict) or review.get("item_id") != 101:
            lines.append("評論清單含不屬於商品 101 的資料")
            return False, lines
    lines.append(f"階層式路由回傳 {len(data)} 筆評論，皆屬於商品 101")
    return passed, lines


def check_create(base):
    url = base + "/api/items"
    status, body, error, elapsed_ms = request_json("POST", url, VALID_ITEM)
    lines = [f"POST {url}", f"實際 {status}｜耗時 {elapsed_ms} ms"]
    if error:
        return False, lines + [error]
    data = body.get("data") if isinstance(body, dict) else None
    created = (
        status == 201
        and envelope_ok(body, "success")
        and isinstance(data, dict)
        and data.get("name") == VALID_ITEM["name"]
        and data.get("category") == VALID_ITEM["category"]
        and data.get("price") == VALID_ITEM["price"]
        and data.get("in_stock") is True
        and isinstance(data.get("id"), int)
        and not isinstance(data.get("id"), bool)
    )
    if created:
        lines.append(f"已建立 id {data['id']}，Body 欄位與回應一致")
    else:
        lines.append(f"Body 未被接受為 201 Created：{message_of(body)}")
    return created, lines


def check_bad_query(base):
    url = base + "/api/items?min_price=not_a_number"
    status, body, error, elapsed_ms = request_json("GET", url)
    lines = [f"GET {url}", f"實際 {status}｜耗時 {elapsed_ms} ms"]
    if error:
        return False, lines + [error]
    if status == 500:
        return False, lines + ["回傳 500，型別錯誤沒有被攔截"]
    blocked = status == 400 and envelope_ok(body, "error") and body.get("data") is None
    if blocked:
        lines.append(message_of(body))
    else:
        lines.append(f"未以 400 錯誤信封拒絕非法價格：{message_of(body)}")
    return blocked, lines


CHECKS = [
    ("服務存活", check_health),
    ("Query 篩選與排序", check_query),
    ("Path 參數與階層式路由", check_paths),
    ("Request Body 建立商品", check_create),
    ("Query 型別防護", check_bad_query),
]


def print_check(index, total, name, passed, lines):
    mark = paint("✅ Pass", "32") if passed else paint("❌ Fail", "31")
    print(f"[{index}/{total}] {mark}  {name}")
    for line in lines:
        print(f"         {line}")


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    base = args.url.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        print("URL 必須以 http:// 或 https:// 開頭", file=sys.stderr)
        return 2

    total = len(CHECKS)
    print(paint(f"雲端驗收  {base}", "1"))
    print(f"共 {total} 項請求，逾時 {TIMEOUT_SECONDS} 秒")

    passed_count = 0
    for index, (name, check) in enumerate(CHECKS, start=1):
        passed, lines = check(base)
        if passed:
            passed_count += 1
        print_check(index, total, name, passed, lines)

    failed_count = total - passed_count
    summary = f"共 {total} 項，Pass {passed_count}，Fail {failed_count}"
    print()
    print(paint(summary, "32" if failed_count == 0 else "31"))
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
