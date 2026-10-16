"""依序呼叫本機 Flask API，並把每個案例的結果寫入 test_results.json。

只使用 Python 3 標準庫，不依賴第三方測試框架。
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"
OUTPUT_PATH = Path(__file__).resolve().parent / "test_results.json"
TIMEOUT_SECONDS = 5

CASES = [
    {
        "case_name": "健康檢查",
        "method": "GET",
        "path": "/api/health",
        "payload": None,
        "expected_status": 200,
    },
    {
        "case_name": "取得存在的商品",
        "method": "GET",
        "path": "/api/items/101",
        "payload": None,
        "expected_status": 200,
    },
    {
        "case_name": "取得不存在的商品",
        "method": "GET",
        "path": "/api/items/999",
        "payload": None,
        "expected_status": 404,
    },
    {
        "case_name": "依分類、庫存與價格排序查詢商品",
        "method": "GET",
        "path": "/api/items?category=electronics&in_stock=true&sort=price_asc",
        "payload": None,
        "expected_status": 200,
    },
    {
        "case_name": "最低價格轉型失敗",
        "method": "GET",
        "path": "/api/items?min_price=cheap",
        "payload": None,
        "expected_status": 400,
    },
    {
        "case_name": "最低價格大於最高價格",
        "method": "GET",
        "path": "/api/items?min_price=5000&max_price=1000",
        "payload": None,
        "expected_status": 400,
    },
    {
        "case_name": "新增合法商品",
        "method": "POST",
        "path": "/api/items",
        "payload": {
            "name": "降噪藍牙耳機",
            "category": "electronics",
            "price": 2990,
            "in_stock": True,
        },
        "expected_status": 201,
    },
    {
        "case_name": "新增負數價格商品",
        "method": "POST",
        "path": "/api/items",
        "payload": {
            "name": "異常商品",
            "category": "electronics",
            "price": -100,
        },
        "expected_status": 400,
    },
]


def decode_body(raw):
    """把回應位元組轉成 JSON 物件；無法解析時保留原始文字。"""
    if not raw:
        return None
    text = raw.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def run_case(case):
    """執行單一案例。4xx/5xx 仍讀取回應，連線失敗則記為 Fail。"""
    url = BASE_URL + case["path"]
    payload = case["payload"]
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=case["method"],
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            actual_status = response.status
            response_body = decode_body(response.read())
    except urllib.error.HTTPError as exc:
        actual_status = exc.code
        response_body = decode_body(exc.read())
    except urllib.error.URLError as exc:
        actual_status = None
        response_body = {"error": str(exc.reason)}
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    result = "Pass" if actual_status == case["expected_status"] else "Fail"
    return {
        "case_name": case["case_name"],
        "method": case["method"],
        "url": url,
        "payload": payload,
        "expected_status": case["expected_status"],
        "actual_status": actual_status,
        "elapsed_ms": elapsed_ms,
        "response_body": response_body,
        "result": result,
    }


def print_progress(index, total, record):
    """在終端機印出單一案例的 Pass/Fail 與狀態碼。"""
    print(
        f"[{index}/{total}] {record['result']}  {record['case_name']}\n"
        f"         {record['method']} {record['url']}\n"
        f"         預期 {record['expected_status']}｜實際 {record['actual_status']}"
        f"｜耗時 {record['elapsed_ms']} ms"
    )


def main():
    total = len(CASES)
    results = []
    print(f"開始測試 {BASE_URL}，共 {total} 項案例")

    for index, case in enumerate(CASES, start=1):
        record = run_case(case)
        results.append(record)
        print_progress(index, total, record)

    passed = sum(record["result"] == "Pass" for record in results)
    failed = total - passed
    report = {
        "base_url": BASE_URL,
        "executed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary": {"total": total, "passed": passed, "failed": failed},
        "results": results,
    }
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n共 {total} 項，Pass {passed}，Fail {failed}")
    print(f"結果已寫入 {OUTPUT_PATH.name}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
