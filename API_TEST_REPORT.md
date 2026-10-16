# API 測試驗收報告

| 項目 | 內容 |
| --- | --- |
| 文件名稱 | API Verification Report |
| 目標服務 | Flask Vibe API，商品資源 `/api/items` |
| 測試基準位址 | `http://127.0.0.1:5000` |
| 測試時間 | 2026-10-17T01:42:59+08:00 |
| 案例總數 | 8 |
| 通過 / 失敗 | 8 / 0 |
| 通過率 | 100% |
| 測試結論 | 8 項案例全部 Pass，三大傳參途徑的狀態碼與 JSON 信封一致 |

---

## 1. 測試摘要

本次驗收讀取 `test_results.json`，確認本機 Flask API 在 Path、Query、Request Body 三種傳參途徑上的狀態碼與回應契約。腳本為 `run_tests.py`，以 Python 3 標準庫 `urllib` 依序呼叫，未使用第三方測試框架。

| 項目 | 說明 |
| --- | --- |
| 測試目標 | 健康檢查，以及商品資源的查詢、單筆讀取與建立 |
| 測試環境 | 本機 loopback，`127.0.0.1:5000` |
| 服務組成 | Flask 3.1.3、Werkzeug 3.1.9（專案依賴版本） |
| 資料存放 | 行程內記憶體清單；同一行程會保留先前建立的商品，重啟後回到初始資料 |
| 回應契約 | JSON 信封含 `status`、`message`、`data`；清單查詢另含 `meta` |
| 耗時合計 | 8 筆請求共 27.41 ms；首筆 22.37 ms，其餘 7 筆皆在 1.01 ms 以內 |

驗收同時覆蓋正常流程與邊界流程。存在的資源回 200，成功建立回 201，型別或數值不合法回 400，整數 ID 找不到資源回 404。錯誤回應維持 JSON 信封，`data` 為 `null`。

---

## 2. 測試矩陣執行總表

下表 URL 為路徑與查詢字串，主機皆為 `http://127.0.0.1:5000`。耗時取自各案 `elapsed_ms`。

| ID | 案例說明 | Method | URL | 預期碼 | 實際碼 | 耗時 | 結果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TC-01 | 健康檢查 | GET | `/api/health` | 200 | 200 | 22.37 ms | Pass |
| TC-02 | 取得存在的商品 | GET | `/api/items/101` | 200 | 200 | 0.85 ms | Pass |
| TC-03 | 取得不存在的商品 | GET | `/api/items/999` | 404 | 404 | 0.66 ms | Pass |
| TC-04 | 依分類、庫存與價格排序查詢商品 | GET | `/api/items?category=electronics&in_stock=true&sort=price_asc` | 200 | 200 | 0.59 ms | Pass |
| TC-05 | 最低價格轉型失敗 | GET | `/api/items?min_price=cheap` | 400 | 400 | 0.68 ms | Pass |
| TC-06 | 最低價格大於最高價格 | GET | `/api/items?min_price=5000&max_price=1000` | 400 | 400 | 0.55 ms | Pass |
| TC-07 | 新增合法商品 | POST | `/api/items` | 201 | 201 | 1.01 ms | Pass |
| TC-08 | 新增負數價格商品 | POST | `/api/items` | 400 | 400 | 0.7 ms | Pass |

通過率：8 / 8（100%）。

TC-07 的請求本文為：

```json
{"name": "降噪藍牙耳機", "category": "electronics", "price": 2990, "in_stock": true}
```

TC-08 的請求本文為：

```json
{"name": "異常商品", "category": "electronics", "price": -100}
```

其餘案例沒有請求本文。

---

## 3. 三大傳參機制合規性分析

### 3.1 Path Parameter：存在資源與 404 邊界

TC-02 以整數路徑 `/api/items/101` 取得既有商品，狀態碼 200。回應信封為 `status: "success"`、`message: "取得商品成功"`，`data` 為單筆物件：`id` 101、名稱「無線降噪耳機」、分類 `electronics`、價格 3990、`in_stock` 為 `true`。路徑上的整數已對應到正確資源，客戶端不必再從清單裡自行過濾。

TC-03 呼叫 `/api/items/999`，狀態碼 404，耗時 0.66 ms。回應為：

```json
{
  "status": "error",
  "message": "找不到指定商品",
  "data": null
}
```

這次 404 是資源不存在，路由本身已被整數 ID 匹配。訊息寫明「找不到指定商品」，`data` 為 `null`，沒有回傳空物件或其他商品。客戶端可以用 HTTP 404 停止重試，並用 `message` 顯示業務原因。不存在的 ID 沒有落到 500，也沒有被當成建立或查詢成功。

### 3.2 Query Parameters：過濾成功、型別防護與區間防護

TC-04 同時帶入 `category=electronics`、`in_stock=true`、`sort=price_asc`，狀態碼 200。`meta` 為：

```json
{
  "total": 3,
  "filters_applied": {"category": "electronics", "in_stock": true},
  "sort": "price_asc"
}
```

`in_stock` 從查詢字串 `true` 轉成布林值 `true` 後寫入 `filters_applied`，`total` 與 `data` 陣列長度同為 3。回傳順序依價格由低到高：

| id | 名稱 | price |
| --- | --- | --- |
| 108 | 高解析藍牙耳機 | 2990 |
| 109 | 降噪藍牙耳機 | 2990 |
| 101 | 無線降噪耳機 | 3990 |

價格 2990 的兩筆再依 id 108、109 排列，隨後才是 3990。同一行程的記憶體清單已含先前建立的 108 與 109，因此這次篩選結果多於初始種子資料中「有庫存的 electronics」。狀態碼仍為 200，過濾、布林轉型與 `price_asc` 排序都反映在 `meta` 與 `data` 的順序上。

TC-05 傳入 `min_price=cheap`，狀態碼 400，耗時 0.68 ms。回應為：

```json
{
  "status": "error",
  "message": "參數 min_price 必須為整數",
  "data": null
}
```

`cheap` 無法轉成整數。服務回 400 與明確欄位訊息，`data` 為 `null`，沒有把非法字串帶入價格比較，也沒有產生 500。型別錯誤停在查詢參數這一層。

TC-06 的 `min_price=5000` 與 `max_price=1000` 各自都是合法整數，狀態碼仍為 400。回應為：

```json
{
  "status": "error",
  "message": "min_price 不可大於 max_price",
  "data": null
}
```

兩段數字都已完成轉型，接著才因下限大於上限被拒絕。這與 TC-05 的轉型失敗是兩道不同的檢查：先確認型別，再確認區間方向。客戶端收到的是可讀的業務訊息，而不是空清單或未定義的篩選結果。

### 3.3 Request Body：合法建立與負數價格防護

TC-07 以 `application/json` 提交名稱、分類、價格與庫存，狀態碼 201，耗時 1.01 ms。服務核發 `id` 110，並原樣保存客戶端提交的四個欄位：

```json
{
  "status": "success",
  "message": "新增商品成功",
  "data": {
    "id": 110,
    "name": "降噪藍牙耳機",
    "category": "electronics",
    "price": 2990,
    "in_stock": true,
    "tags": [],
    "created_at": "2026-10-17T01:42:59+08:00"
  }
}
```

主鍵由伺服器指定。`tags` 由服務補成空陣列，`created_at` 為伺服器時間。201 與「新增商品成功」一致，表示資源已建立，且與 TC-04 的 200 查詢成功區分開來。

TC-08 使用同一端點，價格改為 `-100`，狀態碼 400，耗時 0.7 ms。回應為：

```json
{
  "status": "error",
  "message": "price 不可為負數",
  "data": null
}
```

分類 `electronics` 與名稱都已送出，拒絕原因集中在價格。`data` 為 `null`，回應中沒有新的 `id`，這次 payload 沒有變成可再查詢的商品表示。負數防護在寫入前記住，狀態碼維持 400。

---

## 4. 結論與部署建議

8 項案例的實際狀態碼全部與預期相同，通過率 100%。Path 能區分存在資源（200）與不存在的整數 ID（404）。Query 在合法過濾時回 200 並以 `meta` 帶出已套用條件；`min_price=cheap` 與「下限大於上限」分別回 400，沒有因型別或區間錯誤變成 500。Body 在合法 JSON 時回 201 並由伺服器指定 `id`；價格為負數時回 400，且回應不含新資源。

部署前建議處理下列事項：

1. **持久化。** 商品清單放在行程記憶體。TC-04 已讀到同一行程稍早建立的 id 108、109，TC-07 接著核發 id 110。服務重啟後這些資料會消失。正式環境若有多個 worker 或無狀態執行個體，各行程的清單不會共用。上線前應改接到資料庫，並讓 id 由資料庫產生。
2. **執行方式。** 本次驗收對象是 `127.0.0.1:5000` 上的開發伺服器。部署時改由 WSGI 伺服器承接，並關閉 debug。專案內的 `vercel.json` 會把所有路徑轉到 `app.py`；若部署到該平台，更需要第 1 點的外部儲存，否則建立後的商品無法跨請求保留。
3. **存活探針。** TC-01 的 `/api/health` 回 200，`data.server` 為 `running`，`data.time` 為請求當下時間。可作為部署後的存活檢查。
4. **客戶端契約。** 成功、400 與 404 都使用同一 JSON 信封。客戶端應同時讀取 HTTP 狀態碼與 `message`。清單畫面應讀 `meta.total` 與 `meta.filters_applied`，避免只看 `data` 長度而忽略篩選條件。
5. **後續自動化。** 本次腳本以狀態碼判定 Pass/Fail，8 項因此全部通過。進入持續整合時，可再鎖定回應欄位：單筆須含整數 `id` 與非負 `price`，404 與 400 的 `data` 須為 `null`，清單的 `meta.total` 須等於 `data` 長度。
