# API 測試驗收報告

| 項目 | 內容 |
| --- | --- |
| 文件名稱 | API Test Verification Report |
| 目標服務 | Flask Vibe API（任務管理 RESTful API） |
| 測試基準位址 | `http://127.0.0.1:5000` |
| 報告日期 | 2026-10-17 |
| 測試結論 | 5 項案例全部 Pass |

---

## 1. 測試概述

本次驗收針對本機已完成的 Flask RESTful API，確認健康檢查、任務清單、任務新增，以及錯誤路徑皆回傳統一的 JSON 封裝，且 HTTP 狀態碼與業務規則一致。

| 項目 | 說明 |
| --- | --- |
| 測試環境 | 本機 loopback，`127.0.0.1:5000` |
| 執行環境 | Python 3.13.7、Werkzeug 3.1.9（取自回應標頭 `Server`） |
| 目標服務 | Flask 開發伺服器所提供的任務 API |
| 資料存放 | 行程內記憶體清單；服務重啟後回到初始資料 |
| 測試工具 | curl（本次日誌之驗收依據）。Postman 以相同 URL、Header 與 JSON body 可重現同一結果 |
| 回應契約 | `Content-Type: application/json`；本體固定含 `status`、`message`、`data` |
| 日誌時間 | 成功新增與空白標題兩筆回應標頭為 `Fri, 16 Oct 2026 16:45:16 GMT` 與 `16:45:43 GMT`（台灣時間 2026-10-17 00:45） |

驗收範圍涵蓋正常流程與防禦性流程：資源建立應為 201，欄位清洗失敗應為 400，未註冊路徑應為 404，且錯誤回應維持 JSON，不回傳 HTML。

---

## 2. 測試案例涵蓋矩陣

| 案例編號 | 測試端點 | HTTP Method | 輸入描述 | 預期狀態碼 | 實際狀態碼 | 測試結果 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-01 | `/api/health` | GET | 無請求本文，檢查服務存活 | 200 | 200 | Pass |
| TC-02 | `/api/tasks` | GET | 無請求本文，查詢任務清單 | 200 | 200 | Pass |
| TC-03 | `/api/tasks` | POST | 合法 JSON：含 `title` 與 `description` | 201 | 201 | Pass |
| TC-04 | `/api/tasks` | POST | 合法 JSON：`title` 僅含空白字元 | 400 | 400 | Pass |
| TC-05 | `/api/not-exist-route` | GET | 呼叫未註冊路徑 | 404 | 404 | Pass |

通過率：5 / 5（100%）。

---

## 3. 各案例詳細呼叫與回應紀錄

### TC-01 健康檢查

**呼叫**

```http
GET /api/health HTTP/1.1
Host: 127.0.0.1:5000
```

**回應**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "success",
  "message": "伺服器運行正常",
  "data": {
    "server": "running",
    "time": "<請求當下的 ISO 8601 時間>"
  }
}
```

**技術點評**

狀態碼 200 表示服務可接受請求。回應沿用統一封裝，`status` 為 `success`，訊息為「伺服器運行正常」。`data.time` 隨請求當下變化，本次摘要日誌未附具體時間字串。此端點可作為部署後與監控用的存活探針。

### TC-02 任務清單查詢

**呼叫**

```http
GET /api/tasks HTTP/1.1
Host: 127.0.0.1:5000
```

**回應**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "success",
  "message": "取得任務清單成功",
  "data": [
    {
      "id": 1,
      "title": "熟悉 Flask 路由",
      "description": "建立健康檢查與任務查詢端點"
    },
    {
      "id": 2,
      "title": "整理 API 回應格式",
      "description": "統一封裝 status、message 與 data"
    }
  ]
}
```

**技術點評**

狀態碼 200，`data` 為陣列且含 2 筆初始任務。清單讀取未改寫資源，符合安全的查詢語意。中文標題以 UTF-8 原樣輸出，未變成 `\uXXXX` 跳脫序列。

### TC-03 正常新增任務

**呼叫**

```bash
curl -i -X POST http://127.0.0.1:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "完成 Postman 整合測試", "description": "由 AI 產出驗收報告"}'
```

**回應**

```http
HTTP/1.1 201 CREATED
Server: Werkzeug/3.1.9 Python/3.13.7
Date: Fri, 16 Oct 2026 16:45:16 GMT
Content-Type: application/json
Content-Length: 182
Connection: close

{
  "status": "success",
  "message": "新增任務成功",
  "data": {
    "id": 8,
    "title": "完成 Postman 整合測試",
    "description": "由 AI 產出驗收報告"
  }
}
```

**技術點評**

用戶端只提交 `title` 與 `description`，伺服器核發 `id: 8` 並原樣保存兩個欄位。`201 CREATED` 與「新增任務成功」一致，表示資源已建立。此 `id` 不是 3，代表該行程的記憶體序號在本次呼叫前已經前進；序號由伺服器管理，客戶端無法在這次 payload 中指定主鍵。

### TC-04 空白標題防呆

**呼叫**

```bash
curl -i -X POST http://127.0.0.1:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "   "}'
```

**回應**

```http
HTTP/1.1 400 BAD REQUEST
Server: Werkzeug/3.1.9 Python/3.13.7
Date: Fri, 16 Oct 2026 16:45:43 GMT
Content-Type: application/json
Content-Length: 78
Connection: close

{
  "status": "error",
  "message": "title 不可為空白",
  "data": null
}
```

**技術點評**

請求的 `Content-Type` 已是 `application/json`，本文也可被解析，因此這次 400 來自欄位規則，而非媒體類型錯誤。`title` 經 `.strip()` 後成為空字串，服務拒絕建立並回傳明確訊息。`data` 為 `null`，回應中沒有新的任務 `id`，表示無效輸入未寫入清單。

### TC-05 不存在路由

**呼叫**

```http
GET /api/not-exist-route HTTP/1.1
Host: 127.0.0.1:5000
```

**回應**

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "status": "error",
  "message": "API 路徑不存在"
}
```

**技術點評**

未註冊路徑由全域 404 攔截器處理，狀態碼 404，本體為 JSON，訊息為「API 路徑不存在」。客戶端不會收到 Flask 預設 HTML 錯誤頁，路徑探測時的回應格式與其他端點一致。

---

## 4. 架構安全性與防禦性總結

### 4.1 `201 Created` 合規性

TC-03 的結果符合資源建立的 HTTP 語意。

- 狀態碼為 201，對應「請求已完成，並產生新資源」。Werkzeug 狀態列文字為 `201 CREATED`，與 `201 Created` 為同一狀態碼。
- 回應本文帶回已建立的表示：伺服器指定的 `id`，以及客戶端提交的 `title`、`description`。
- 成功訊息「新增任務成功」與 `status: "success"` 同屬建立成功，沒有以 200 混淆「查詢成功」與「建立成功」。
- 主鍵由伺服器遞增產生。本次請求未帶 `id`，回應中的 `8` 不可由客戶端任意指定。
- 媒體類型為 `application/json`，中文內容可直接閱讀。

後續若要再對齊較完整的建立回應，可在 201 加上 `Location` 標頭（例如 `/api/tasks/8`），讓客戶端不必只從本文取出新資源位址。本次驗收以狀態碼與 JSON 本文為準，TC-03 判定 Pass。

### 4.2 `400 Bad Request` 合規性

TC-04 的結果符合客戶端輸入錯誤的 HTTP 語意。

- `"   "` 在去除前後空白後沒有有效標題。服務回 400，而不是建立一筆空白任務，也沒有落到 500。
- 錯誤本文維持同一契約：`status` 為 `error`，`message` 為「title 不可為空白」，`data` 為 `null`。
- 回應沒有堆疊追蹤、框架 HTML 或內部路徑，錯誤資訊停在呼叫端可處理的業務訊息。
- 此案例已帶正確的 `application/json`。400 證明第二層防禦（欄位清洗）獨立於第一層媒體類型檢查。
- 拒絕回應未含新 `id`。無效 payload 沒有變成可再查詢的資源。

### 4.3 整體判斷

五項案例的實際狀態碼皆與預期相同，統一 JSON 封裝在成功、驗證失敗與未知路徑三種情況都成立。201 正確表達資源建立，400 正確擋下清洗後為空的 `title`。以本次日誌為準，本機 API 測試驗收通過。
