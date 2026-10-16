"""任務管理系統的最小可行 RESTful API。

使用記憶體清單保存任務，端點本身不依賴 session，符合無狀態原則。
"""

from datetime import datetime

from flask import Flask, jsonify, request

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


def make_response_payload(status, message, data=None, status_code=200):
    """統一封裝 JSON 回應與 HTTP 狀態碼。"""
    body = {"status": status, "message": message, "data": data}
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
