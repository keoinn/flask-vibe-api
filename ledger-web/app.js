/**
 * 個人記帳本前端主程式 (Mobile-First Vanilla JavaScript)
 * 遵循 docs/前端串接.md 規格書
 * 驗收方式：在 ledger-api/ledger-web 用本機靜態伺服器開啟 (例如: python3 -m http.server 3000)
 */

(function () {
  "use strict";

  // ==========================================
  // 常數與狀態管理
  // ==========================================
  const STORAGE_KEY = "ledger.connection";

  const state = {
    apiBaseUrl: "",
    currentTab: "tab-home",
    accounts: [],
    expenseCategories: [],
    incomeCategories: [],
    currentMonthRecords: [], // 本月記帳即時明細清單 (入帳與花費)
  };

  // DOM 元素快取
  const dom = {
    viewConnection: document.getElementById("view-connection"),
    viewMain: document.getElementById("view-main"),
    formConnection: document.getElementById("form-connection"),
    inputApiUrl: document.getElementById("input-api-url"),
    connectionError: document.getElementById("connection-error"),
    btnConnect: document.getElementById("btn-connect"),
    btnDisconnect: document.getElementById("btn-disconnect"),
    pageTitle: document.getElementById("page-title"),
    toastMessage: document.getElementById("toast-message"),

    // 底部導覽
    navButtons: document.querySelectorAll(".nav-item"),
    tabPanes: document.querySelectorAll(".tab-pane"),

    // 首頁
    summaryMonthLabel: document.getElementById("summary-month-label"),
    summaryIncome: document.getElementById("summary-income"),
    summaryExpense: document.getElementById("summary-expense"),
    summaryNet: document.getElementById("summary-net"),
    accountsContainer: document.getElementById("accounts-container"),
    noAccountsCard: document.getElementById("no-accounts-card"),
    formInitAccount: document.getElementById("form-init-account"),
    inputInitAccountName: document.getElementById("input-init-account-name"),
    btnRefreshAccounts: document.getElementById("btn-refresh-accounts"),

    // 記帳
    btnToggleExpense: document.getElementById("btn-toggle-expense"),
    btnToggleIncome: document.getElementById("btn-toggle-income"),
    panelExpense: document.getElementById("panel-expense"),
    panelIncome: document.getElementById("panel-income"),
    formExpense: document.getElementById("form-expense"),
    formIncome: document.getElementById("form-income"),
    expenseSpentOn: document.getElementById("expense-spent-on"),
    expenseAmount: document.getElementById("expense-amount"),
    expenseAccountId: document.getElementById("expense-account-id"),
    expenseCategoryId: document.getElementById("expense-category-id"),
    expenseMerchant: document.getElementById("expense-merchant"),
    expenseNote: document.getElementById("expense-note"),
    expenseSettledOn: document.getElementById("expense-settled-on"),
    btnOpenCreateExpenseCat: document.getElementById("btn-open-create-expense-cat"),
    inlineCreateExpenseCat: document.getElementById("inline-create-expense-cat"),
    inputNewExpenseCatName: document.getElementById("input-new-expense-cat-name"),
    btnSaveExpenseCat: document.getElementById("btn-save-expense-cat"),

    incomeReceivedOn: document.getElementById("income-received-on"),
    incomeAmount: document.getElementById("income-amount"),
    incomeAccountId: document.getElementById("income-account-id"),
    incomeCategoryId: document.getElementById("income-category-id"),
    incomeSource: document.getElementById("income-source"),
    incomeNote: document.getElementById("income-note"),
    btnOpenCreateIncomeCat: document.getElementById("btn-open-create-income-cat"),
    inlineCreateIncomeCat: document.getElementById("inline-create-income-cat"),
    inputNewIncomeCatName: document.getElementById("input-new-income-cat-name"),
    btnSaveIncomeCat: document.getElementById("btn-save-income-cat"),

    recordsList: document.getElementById("records-list"),
    recordsCount: document.getElementById("records-count"),

    // 投資
    btnFetchQuotes: document.getElementById("btn-fetch-quotes"),
    quoteFetchFeedback: document.getElementById("quote-fetch-feedback"),
    instrumentsContainer: document.getElementById("instruments-container"),

    // 發票
    invoicesContainer: document.getElementById("invoices-container"),
    btnRefreshInvoices: document.getElementById("btn-refresh-invoices"),
  };

  // ==========================================
  // 工具函式
  // ==========================================
  let toastTimer = null;

  function showToast(message, isError = false) {
    if (!dom.toastMessage) return;
    clearTimeout(toastTimer);

    dom.toastMessage.textContent = message;
    dom.toastMessage.className = `toast ${isError ? "toast-error" : "toast-success"}`;

    toastTimer = setTimeout(() => {
      dom.toastMessage.className = "toast hidden";
    }, 3500);
  }

  function formatTWD(num) {
    const val = Number(num) || 0;
    return "NT$ " + val.toLocaleString("zh-TW", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function getTodayDateString() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function getCurrentMonthKey() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    return `${y}-${m}`;
  }

  function escapeHTML(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ==========================================
  // 核心 API 請求包裝
  // ==========================================
  async function apiRequest(endpoint, options = {}) {
    if (!state.apiBaseUrl) {
      throw new Error("目前連不上記帳服務");
    }

    const url = `${state.apiBaseUrl}${endpoint}`;
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    let response;
    try {
      response = await fetch(url, { ...options, headers });
    } catch (netErr) {
      // 網路斷線、CORS 阻擋或伺服器未啟動
      throw new Error("目前連不上記帳服務");
    }

    let json;
    try {
      json = await response.json();
    } catch (parseErr) {
      throw new Error("目前連不上記帳服務");
    }

    // 後端格式封裝：code, message, data
    if (!response.ok || json.code >= 400) {
      const errMsg = json && json.message ? json.message : "目前連不上記帳服務";
      const err = new Error(errMsg);
      err.code = json ? json.code : response.status;
      err.data = json ? json.data : null;
      throw err;
    }

    return json;
  }

  // ==========================================
  // 1. 連線管理 (Connection Logic)
  // ==========================================
  function checkForbiddenWords(urlStr) {
    const lower = urlStr.toLowerCase();
    if (
      lower.includes("postgresql://") ||
      lower.includes("sb_secret_") ||
      lower.includes("service_role")
    ) {
      return true;
    }
    return false;
  }

  async function testHealthCheck(baseUrl) {
    const cleanUrl = baseUrl.replace(/\/+$/, "");
    const healthUrl = `${cleanUrl}/api/health`;

    let res;
    try {
      res = await fetch(healthUrl, { method: "GET" });
    } catch (err) {
      throw new Error("目前連不上記帳服務");
    }

    let json;
    try {
      json = await res.json();
    } catch (err) {
      throw new Error("目前連不上記帳服務");
    }

    if (json.code === 200 && json.data && json.data.status === "ok") {
      return cleanUrl;
    }

    throw new Error(json.message || "健康檢查未通過");
  }

  async function handleConnectionSubmit() {
    const inputVal = (dom.inputApiUrl.value || "").trim();

    dom.connectionError.classList.add("hidden");
    dom.connectionError.textContent = "";

    if (!inputVal) {
      dom.connectionError.textContent = "請輸入後端 API 伺服器網址";
      dom.connectionError.classList.remove("hidden");
      return;
    }

    // 檢查非法關鍵字
    if (checkForbiddenWords(inputVal)) {
      dom.connectionError.textContent = "禁止輸入資料庫連線字串或金鑰，僅能填寫後端 API 網址";
      dom.connectionError.classList.remove("hidden");
      return;
    }

    dom.btnConnect.disabled = true;
    dom.btnConnect.textContent = "連線驗證中...";

    try {
      const verifiedBaseUrl = await testHealthCheck(inputVal);

      // 檢查通過，寫入 localStorage (裡面只有 apiBaseUrl)
      const connObj = { apiBaseUrl: verifiedBaseUrl };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(connObj));

      state.apiBaseUrl = verifiedBaseUrl;
      showToast("伺服器連線成功！");
      enterMainApp();
    } catch (err) {
      dom.connectionError.textContent = err.message || "目前連不上記帳服務";
      dom.connectionError.classList.remove("hidden");
    } finally {
      dom.btnConnect.disabled = false;
      dom.btnConnect.textContent = "連線並進入記帳本";
    }
  }

  function handleDisconnect() {
    localStorage.removeItem(STORAGE_KEY);
    state.apiBaseUrl = "";
    state.accounts = [];
    state.expenseCategories = [];
    state.incomeCategories = [];
    state.currentMonthRecords = [];

    dom.inputApiUrl.value = "";
    dom.connectionError.classList.add("hidden");
    dom.viewMain.classList.add("hidden");
    dom.viewConnection.classList.remove("hidden");
    showToast("已清除連線設定");
  }

  async function initConnection() {
    const rawStored = localStorage.getItem(STORAGE_KEY);
    if (!rawStored) {
      dom.viewConnection.classList.remove("hidden");
      dom.viewMain.classList.add("hidden");
      return;
    }

    let parsed;
    try {
      parsed = JSON.parse(rawStored);
    } catch (e) {
      localStorage.removeItem(STORAGE_KEY);
      dom.viewConnection.classList.remove("hidden");
      dom.viewMain.classList.add("hidden");
      return;
    }

    const storedUrl = (parsed && parsed.apiBaseUrl) ? parsed.apiBaseUrl : "";
    if (!storedUrl || checkForbiddenWords(storedUrl)) {
      localStorage.removeItem(STORAGE_KEY);
      dom.viewConnection.classList.remove("hidden");
      dom.viewMain.classList.add("hidden");
      return;
    }

    // 已存過連線，打開先向後端重查 /api/health
    dom.inputApiUrl.value = storedUrl;
    try {
      const verifiedUrl = await testHealthCheck(storedUrl);
      state.apiBaseUrl = verifiedUrl;
      enterMainApp();
    } catch (err) {
      // 驗證失敗回到連線頁並顯示錯誤句子
      dom.connectionError.textContent = err.message || "目前連不上記帳服務";
      dom.connectionError.classList.remove("hidden");
      dom.viewConnection.classList.remove("hidden");
      dom.viewMain.classList.add("hidden");
    }
  }

  function enterMainApp() {
    dom.viewConnection.classList.add("hidden");
    dom.viewMain.classList.remove("hidden");

    // 預設日期填入今天
    const today = getTodayDateString();
    if (dom.expenseSpentOn) dom.expenseSpentOn.value = today;
    if (dom.incomeReceivedOn) dom.incomeReceivedOn.value = today;

    // 切換至首頁並載入資料
    switchTab("tab-home");
  }

  // ==========================================
  // 2. 導覽分頁切換
  // ==========================================
  const tabTitles = {
    "tab-home": "個人記帳本",
    "tab-bookkeeping": "記一筆收支",
    "tab-investment": "投資持倉行情",
    "tab-invoices": "統一發票清單",
  };

  function switchTab(targetTabId) {
    state.currentTab = targetTabId;

    dom.tabPanes.forEach((pane) => {
      if (pane.id === targetTabId) {
        pane.classList.add("active");
        pane.classList.remove("hidden");
      } else {
        pane.classList.remove("active");
        pane.classList.add("hidden");
      }
    });

    dom.navButtons.forEach((btn) => {
      if (btn.getAttribute("data-tab") === targetTabId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    if (dom.pageTitle && tabTitles[targetTabId]) {
      dom.pageTitle.textContent = tabTitles[targetTabId];
    }

    // 載入該分頁所需資料
    if (targetTabId === "tab-home") {
      loadHomeData();
    } else if (targetTabId === "tab-bookkeeping") {
      loadBookkeepingData();
    } else if (targetTabId === "tab-investment") {
      loadInvestmentData();
    } else if (targetTabId === "tab-invoices") {
      loadInvoicesData();
    }
  }

  // ==========================================
  // 3. 首頁 (Home Tab) 業務邏輯
  // ==========================================
  async function loadHomeData() {
    const curMonth = getCurrentMonthKey();
    if (dom.summaryMonthLabel) {
      dom.summaryMonthLabel.textContent = `${curMonth} 月`;
    }

    // 同步讀取月生活現金流與帳戶清單
    await Promise.all([loadMonthlySummary(curMonth), loadAccountsAndBalances()]);
  }

  async function loadMonthlySummary(monthKey) {
    try {
      const res = await apiRequest(`/api/summary?month=${encodeURIComponent(monthKey)}`);
      const data = res.data || {};
      const income = Number(data.income_twd) || 0;
      const expense = Number(data.expense_twd) || 0;
      const net = income - expense;

      dom.summaryIncome.textContent = formatTWD(income);
      dom.summaryExpense.textContent = formatTWD(expense);
      dom.summaryNet.textContent = formatTWD(net);

      if (net >= 0) {
        dom.summaryNet.style.color = "var(--color-primary)";
      } else {
        dom.summaryNet.style.color = "var(--color-expense)";
      }
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function loadAccountsAndBalances() {
    dom.accountsContainer.innerHTML = '<div class="loading-placeholder">帳戶餘額更新中...</div>';

    try {
      const res = await apiRequest("/api/accounts");
      const accounts = res.data || [];
      state.accounts = accounts;

      if (accounts.length === 0) {
        dom.accountsContainer.innerHTML = "";
        dom.noAccountsCard.classList.remove("hidden");
        return;
      }

      dom.noAccountsCard.classList.add("hidden");

      // 平行呼叫每一帳戶的即時餘額
      const accountCards = await Promise.all(
        accounts.map(async (acc) => {
          let twdBalance = 0;
          let currBalance = null;
          try {
            const balRes = await apiRequest(`/api/accounts/${acc.id}/balance`);
            const balData = balRes.data || {};
            twdBalance = Number(balData.twd_balance) || 0;
            currBalance = balData.currency_balance;
          } catch (e) {
            // 單一帳戶餘額失敗不中斷全部
          }

          const kindNames = {
            cash: "現金",
            bank: "銀行",
            credit_card: "信用卡",
            broker: "證券交割",
          };

          const kindBadge = kindNames[acc.kind] || acc.kind;
          const isForeign = acc.currency && acc.currency !== "TWD";

          return `
            <div class="account-card" data-account-id="${acc.id}">
              <div class="account-info">
                <div class="account-name-row">
                  <span class="account-name">${escapeHTML(acc.name)}</span>
                  <span class="badge badge-account">${escapeHTML(kindBadge)}</span>
                </div>
                <span class="record-sub">${escapeHTML(acc.currency)} 帳戶</span>
              </div>
              <div class="account-balance-group">
                <span class="account-twd-balance num-mono">${formatTWD(twdBalance)}</span>
                ${
                  isForeign && currBalance != null
                    ? `<span class="account-original-balance num-mono">原幣: ${Number(currBalance).toFixed(2)} ${acc.currency}</span>`
                    : ""
                }
              </div>
            </div>
          `;
        })
      );

      dom.accountsContainer.innerHTML = accountCards.join("");
    } catch (err) {
      dom.accountsContainer.innerHTML = `<div class="empty-placeholder">${escapeHTML(err.message)}</div>`;
      showToast(err.message, true);
    }
  }

  async function handleInitAccountSubmit() {
    const name = (dom.inputInitAccountName.value || "").trim();
    if (!name) {
      showToast("請輸入帳戶名稱", true);
      return;
    }

    try {
      // 客戶端不送 id、created_at、updated_at
      const payload = {
        name: name,
        kind: "cash",
        currency: "TWD",
        opening_balance: 0.0,
      };

      await apiRequest("/api/accounts", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      showToast("現金帳戶建立成功！");
      dom.noAccountsCard.classList.add("hidden");
      await loadAccountsAndBalances();
      await loadMonthlySummary(getCurrentMonthKey());
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // ==========================================
  // 4. 記帳 (Bookkeeping Tab) 業務邏輯
  // ==========================================
  async function loadBookkeepingData() {
    await Promise.all([
      loadAccountsForSelect(),
      loadExpenseCategories(),
      loadIncomeCategories(),
      loadCurrentMonthRecords(),
    ]);
  }

  async function loadAccountsForSelect() {
    try {
      const res = await apiRequest("/api/accounts");
      state.accounts = res.data || [];
      populateAccountSelects();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  function populateAccountSelects() {
    const expSelect = dom.expenseAccountId;
    const incSelect = dom.incomeAccountId;

    const buildOptions = (list) => {
      if (!list || list.length === 0) {
        return '<option value="">(尚未建立帳戶)</option>';
      }
      return [
        '<option value="">請選擇帳戶</option>',
        ...list.map(
          (acc) => `<option value="${acc.id}">${escapeHTML(acc.name)} (${acc.currency})</option>`
        ),
      ].join("");
    };

    expSelect.innerHTML = buildOptions(state.accounts);
    incSelect.innerHTML = buildOptions(state.accounts);
  }

  async function loadExpenseCategories() {
    try {
      const res = await apiRequest("/api/expense-categories");
      state.expenseCategories = res.data || [];
      populateExpenseCategorySelect();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  function populateExpenseCategorySelect() {
    const select = dom.expenseCategoryId;
    const cats = state.expenseCategories;

    if (!cats || cats.length === 0) {
      select.innerHTML = '<option value="">(尚無花費分類，請先新增)</option>';
      // 自動展開快速新增分類區塊
      dom.inlineCreateExpenseCat.classList.remove("hidden");
      return;
    }

    select.innerHTML = [
      '<option value="">請選擇花費分類</option>',
      ...cats.map((c) => `<option value="${c.id}">${escapeHTML(c.name)}</option>`),
    ].join("");
  }

  async function loadIncomeCategories() {
    try {
      const res = await apiRequest("/api/income-categories");
      state.incomeCategories = res.data || [];
      populateIncomeCategorySelect();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  function populateIncomeCategorySelect() {
    const select = dom.incomeCategoryId;
    const cats = state.incomeCategories;

    if (!cats || cats.length === 0) {
      select.innerHTML = '<option value="">(尚無入帳分類，請先新增)</option>';
      dom.inlineCreateIncomeCat.classList.remove("hidden");
      return;
    }

    select.innerHTML = [
      '<option value="">請選擇入帳分類</option>',
      ...cats.map((c) => `<option value="${c.id}">${escapeHTML(c.name)}</option>`),
    ].join("");
  }

  // 建立分類 (Expense / Income)
  async function handleCreateExpenseCategory() {
    const name = (dom.inputNewExpenseCatName.value || "").trim();
    if (!name) {
      showToast("分類名稱不可為空", true);
      return;
    }

    try {
      const res = await apiRequest("/api/expense-categories", {
        method: "POST",
        body: JSON.stringify({ name: name, description: null }),
      });

      showToast(`花費分類「${name}」建立成功！`);
      dom.inputNewExpenseCatName.value = "";
      dom.inlineCreateExpenseCat.classList.add("hidden");

      await loadExpenseCategories();
      if (res.data && res.data.id) {
        dom.expenseCategoryId.value = res.data.id;
      }
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function handleCreateIncomeCategory() {
    const name = (dom.inputNewIncomeCatName.value || "").trim();
    if (!name) {
      showToast("分類名稱不可為空", true);
      return;
    }

    try {
      const res = await apiRequest("/api/income-categories", {
        method: "POST",
        body: JSON.stringify({ name: name, description: null }),
      });

      showToast(`入帳分類「${name}」建立成功！`);
      dom.inputNewIncomeCatName.value = "";
      dom.inlineCreateIncomeCat.classList.add("hidden");

      await loadIncomeCategories();
      if (res.data && res.data.id) {
        dom.incomeCategoryId.value = res.data.id;
      }
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // 新增花費提交
  async function handleExpenseSubmit() {
    const spentOn = dom.expenseSpentOn.value;
    const rawAmount = dom.expenseAmount.value;
    const accountId = dom.expenseAccountId.value;
    const categoryId = dom.expenseCategoryId.value;
    const merchant = (dom.expenseMerchant.value || "").trim();
    const note = (dom.expenseNote.value || "").trim();
    const settledOn = dom.expenseSettledOn.value || null;

    if (!spentOn) return showToast("請選擇消費日期", true);
    if (!rawAmount || Number(rawAmount) <= 0) return showToast("請輸入大於 0 之金額", true);
    if (!accountId) return showToast("請選擇扣款帳戶", true);
    if (!categoryId) return showToast("請選擇花費分類", true);

    // 商業約束 rule.empty_text: 商家與備註至少填一個
    if (!merchant && !note) {
      return showToast("商家與備註至少填一個", true);
    }

    try {
      // 客戶端不送 id、created_at、updated_at
      const payload = {
        spent_on: spentOn,
        amount: Number(rawAmount),
        account_id: parseInt(accountId, 10),
        category_id: parseInt(categoryId, 10),
        merchant: merchant || null,
        note: note || null,
        settled_on: settledOn,
      };

      const res = await apiRequest("/api/expenses", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const newExpense = res.data;
      showToast("新增花費成功！");

      // 清空表單欄位（保留日期與帳戶方便連續記帳）
      dom.expenseAmount.value = "";
      dom.expenseMerchant.value = "";
      dom.expenseNote.value = "";
      dom.expenseSettledOn.value = "";

      // 核心需求：成功後把新列放在本月清單最上方
      prependRecordToList({
        type: "expense",
        date: newExpense.spent_on,
        amount: newExpense.amount,
        title: newExpense.merchant || newExpense.note || "日常消費",
        sub: getCategoryNameById("expense", newExpense.category_id),
      });

      // 同步刷新首頁現金流
      loadMonthlySummary(getCurrentMonthKey());
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // 新增入帳提交
  async function handleIncomeSubmit() {
    const receivedOn = dom.incomeReceivedOn.value;
    const rawAmount = dom.incomeAmount.value;
    const accountId = dom.incomeAccountId.value;
    const categoryId = dom.incomeCategoryId.value;
    const source = (dom.incomeSource.value || "").trim();
    const note = (dom.incomeNote.value || "").trim();

    if (!receivedOn) return showToast("請選擇入帳日期", true);
    if (!rawAmount || Number(rawAmount) <= 0) return showToast("請輸入大於 0 之金額", true);
    if (!accountId) return showToast("請選擇存入帳戶", true);
    if (!categoryId) return showToast("請選擇入帳分類", true);

    // 商業約束 rule.empty_text: 來源與備註至少填一個
    if (!source && !note) {
      return showToast("來源與備註至少填一個", true);
    }

    try {
      // 客戶端不送 id、created_at、updated_at
      const payload = {
        received_on: receivedOn,
        amount: Number(rawAmount),
        account_id: parseInt(accountId, 10),
        category_id: parseInt(categoryId, 10),
        source: source || null,
        note: note || null,
      };

      const res = await apiRequest("/api/incomes", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const newIncome = res.data;
      showToast("新增入帳成功！");

      dom.incomeAmount.value = "";
      dom.incomeSource.value = "";
      dom.incomeNote.value = "";

      // 核心需求：成功後把新列放在本月清單最上方
      prependRecordToList({
        type: "income",
        date: newIncome.received_on,
        amount: newIncome.amount,
        title: newIncome.source || newIncome.note || "入帳收入",
        sub: getCategoryNameById("income", newIncome.category_id),
      });

      // 同步刷新首頁現金流
      loadMonthlySummary(getCurrentMonthKey());
    } catch (err) {
      showToast(err.message, true);
    }
  }

  function getCategoryNameById(type, catId) {
    const list = type === "income" ? state.incomeCategories : state.expenseCategories;
    const found = list.find((c) => c.id === catId);
    return found ? found.name : "一般分類";
  }

  // 載入當前月份已發生之明細 (合併入帳與花費)
  async function loadCurrentMonthRecords() {
    dom.recordsList.innerHTML = '<div class="loading-placeholder">載入本月明細中...</div>';

    const curMonth = getCurrentMonthKey();
    const dateFrom = `${curMonth}-01`;
    const dateTo = `${curMonth}-31`;

    try {
      const [incRes, expRes] = await Promise.all([
        apiRequest(`/api/incomes?date_from=${dateFrom}&date_to=${dateTo}`),
        apiRequest(`/api/expenses?date_from=${dateFrom}&date_to=${dateTo}`),
      ]);

      const incomes = (incRes.data || []).map((i) => ({
        type: "income",
        date: i.received_on,
        amount: i.amount,
        title: i.source || i.note || "入帳所得",
        sub: getCategoryNameById("income", i.category_id),
        rawTime: i.created_at || i.received_on,
      }));

      const expenses = (expRes.data || []).map((e) => ({
        type: "expense",
        date: e.spent_on,
        amount: e.amount,
        title: e.merchant || e.note || "生活花費",
        sub: getCategoryNameById("expense", e.category_id),
        rawTime: e.created_at || e.spent_on,
      }));

      // 依日期與建立時間倒序排序
      const allRecords = [...incomes, ...expenses].sort((a, b) => {
        if (a.date !== b.date) return b.date.localeCompare(a.date);
        return String(b.rawTime).localeCompare(String(a.rawTime));
      });

      state.currentMonthRecords = allRecords;
      renderRecordsList();
    } catch (err) {
      dom.recordsList.innerHTML = `<div class="empty-placeholder">${escapeHTML(err.message)}</div>`;
    }
  }

  function prependRecordToList(item) {
    state.currentMonthRecords.unshift(item);
    renderRecordsList();
  }

  function renderRecordsList() {
    const list = state.currentMonthRecords;
    if (dom.recordsCount) {
      dom.recordsCount.textContent = `${list.length} 筆`;
    }

    if (!list || list.length === 0) {
      dom.recordsList.innerHTML = '<div class="empty-placeholder">本月尚無任何收支明細</div>';
      return;
    }

    dom.recordsList.innerHTML = list
      .map((item) => {
        const isIncome = item.type === "income";
        const sign = isIncome ? "+" : "-";
        const amountClass = isIncome ? "income" : "expense";
        const formattedAmount = `${sign}${formatTWD(item.amount)}`;

        return `
          <div class="record-item">
            <div class="record-meta">
              <div class="record-title-row">
                <span class="badge ${isIncome ? "badge-won" : "badge-neutral"}">${isIncome ? "入帳" : "花費"}</span>
                <span class="record-title">${escapeHTML(item.title)}</span>
              </div>
              <span class="record-sub">${escapeHTML(item.date)} · ${escapeHTML(item.sub)}</span>
            </div>
            <span class="record-amount num-mono ${amountClass}">${formattedAmount}</span>
          </div>
        `;
      })
      .join("");
  }

  // ==========================================
  // 5. 投資 (Investment Tab) 業務邏輯
  // ==========================================
  async function loadInvestmentData() {
    dom.instrumentsContainer.innerHTML = '<div class="loading-placeholder">讀取台股標的中...</div>';
    dom.quoteFetchFeedback.classList.add("hidden");

    try {
      const res = await apiRequest("/api/instruments");
      const instruments = res.data || [];

      // 只篩選 market === 'tw_stock' 之投資標的
      const twStocks = instruments.filter((inst) => inst.market === "tw_stock");

      if (twStocks.length === 0) {
        dom.instrumentsContainer.innerHTML = '<div class="empty-placeholder">目前沒有台股標的 (tw_stock)</div>';
        return;
      }

      // 平行拉取持有資訊 (holding) 與最新報價 (quote)
      const cardsHtml = await Promise.all(
        twStocks.map(async (stock) => {
          let holdingQty = 0;
          let quoteDisplay = "還沒有報價";
          let hasQuote = false;

          // 1. 取得持有數量
          try {
            const hRes = await apiRequest(`/api/instruments/${stock.id}/holding`);
            if (hRes.data && hRes.data.quantity != null) {
              holdingQty = Number(hRes.data.quantity) || 0;
            }
          } catch (e) {
            // 無持有或查詢失敗保持 0
          }

          // 2. 取得最新報價 (沒有就顯示「還沒有報價」)
          try {
            const qRes = await apiRequest(`/api/instruments/${stock.id}/quote`);
            if (qRes.data && (qRes.data.price != null || qRes.data.close != null)) {
              const p = qRes.data.price != null ? qRes.data.price : qRes.data.close;
              quoteDisplay = formatTWD(p);
              hasQuote = true;
            }
          } catch (e) {
            // 端點不存在 (404) 或查無資料，依指示顯示「還沒有報價」
            quoteDisplay = "還沒有報價";
          }

          return `
            <div class="instrument-card" data-instrument-id="${stock.id}">
              <div class="instrument-main">
                <div class="instrument-name-row">
                  <span class="instrument-name">${escapeHTML(stock.name)}</span>
                  <span class="instrument-symbol">${escapeHTML(stock.symbol)}</span>
                </div>
                <span class="instrument-holding">持有股數：<strong class="num-mono">${holdingQty.toLocaleString()}</strong> 股</span>
              </div>
              <div class="instrument-quote-group">
                <span class="instrument-quote-label">最新報價</span>
                <span class="instrument-quote-price num-mono ${hasQuote ? "" : "no-quote"}">${escapeHTML(quoteDisplay)}</span>
              </div>
            </div>
          `;
        })
      );

      dom.instrumentsContainer.innerHTML = cardsHtml.join("");
    } catch (err) {
      dom.instrumentsContainer.innerHTML = `<div class="empty-placeholder">${escapeHTML(err.message)}</div>`;
      showToast(err.message, true);
    }
  }

  // 抓取台股報價按鈕
  async function handleFetchQuotes() {
    dom.btnFetchQuotes.disabled = true;
    dom.btnFetchQuotes.textContent = "抓取報價中...";
    dom.quoteFetchFeedback.classList.add("hidden");

    try {
      // 依規格呼叫 POST /api/tw-stock-quotes/fetch
      const res = await apiRequest("/api/tw-stock-quotes/fetch", {
        method: "POST",
      });

      const data = res.data || {};

      // 核心要求：missing 與 skipped 用一句人話帶過
      const missingCount = Array.isArray(data.missing)
        ? data.missing.length
        : Number(data.missing) || 0;
      const skippedCount = Array.isArray(data.skipped)
        ? data.skipped.length
        : Number(data.skipped) || 0;

      let humanSentence = "台股報價已成功更新完成";
      if (missingCount > 0 || skippedCount > 0) {
        humanSentence = `台股報價更新完成（其中 ${missingCount} 檔查無報價，${skippedCount} 檔略過未處理）`;
      }

      dom.quoteFetchFeedback.textContent = humanSentence;
      dom.quoteFetchFeedback.classList.remove("hidden");
      showToast("台股報價更新完成！");

      // 完成後重讀標的、持倉與最新報價
      await loadInvestmentData();
    } catch (err) {
      // 失敗時畫面只顯示 message。若連不上顯示「目前連不上記帳服務」
      const errorMsg = err.message || "目前連不上記帳服務";
      dom.quoteFetchFeedback.textContent = errorMsg;
      dom.quoteFetchFeedback.classList.remove("hidden");
      showToast(errorMsg, true);
    } finally {
      dom.btnFetchQuotes.disabled = false;
      dom.btnFetchQuotes.textContent = "抓取台股報價";
    }
  }

  // ==========================================
  // 6. 發票 (Invoices Tab) 業務邏輯 (只讀)
  // ==========================================
  async function loadInvoicesData() {
    dom.invoicesContainer.innerHTML = '<div class="loading-placeholder">載入統一發票清單中...</div>';

    try {
      const res = await apiRequest("/api/invoices");
      const invoices = res.data || [];

      if (invoices.length === 0) {
        dom.invoicesContainer.innerHTML = '<div class="empty-placeholder">目前尚無統一發票紀錄</div>';
        return;
      }

      const statusMap = {
        unchecked: { label: "未對獎", cls: "badge-unchecked" },
        won: { label: "已中獎", cls: "badge-won" },
        claimed: { label: "已領獎", cls: "badge-claimed" },
        lost: { label: "未中獎", cls: "badge-lost" },
        void: { label: "作廢", cls: "badge-void" },
      };

      const html = invoices
        .map((inv) => {
          const statusInfo = statusMap[inv.prize_status] || {
            label: inv.prize_status || "未知",
            cls: "badge-neutral",
          };

          return `
            <div class="invoice-card" data-invoice-id="${inv.id}">
              <div class="invoice-main">
                <div class="invoice-number-row">
                  <span class="invoice-number">${escapeHTML(inv.number)}</span>
                  <span class="badge ${statusInfo.cls}">${escapeHTML(statusInfo.label)}</span>
                </div>
                <span class="invoice-issued">開立日：${escapeHTML(inv.issued_on)}${
                  inv.seller_name ? ` · ${escapeHTML(inv.seller_name)}` : ""
                }</span>
              </div>
              <div class="invoice-side">
                <span class="invoice-amount num-mono">${formatTWD(inv.amount)}</span>
                <span class="record-sub">${escapeHTML(inv.kind === "electronic" ? "電子發票" : "紙本發票")}</span>
              </div>
            </div>
          `;
        })
        .join("");

      dom.invoicesContainer.innerHTML = html;
    } catch (err) {
      dom.invoicesContainer.innerHTML = `<div class="empty-placeholder">${escapeHTML(err.message)}</div>`;
      showToast(err.message, true);
    }
  }

  // ==========================================
  // 7. 事件監聽綁定
  // ==========================================
  function bindEvents() {
    // 連線設定提交
    dom.formConnection.addEventListener("submit", (e) => {
      e.preventDefault();
      handleConnectionSubmit();
    });

    // 清除連線
    dom.btnDisconnect.addEventListener("click", handleDisconnect);

    // 底部導覽分頁切換
    dom.navButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const tabId = btn.getAttribute("data-tab");
        if (tabId) switchTab(tabId);
      });
    });

    // 首頁
    dom.btnRefreshAccounts.addEventListener("click", () => {
      loadHomeData();
      showToast("已重新整理帳戶餘額");
    });

    dom.formInitAccount.addEventListener("submit", (e) => {
      e.preventDefault();
      handleInitAccountSubmit();
    });

    // 記帳切換 (花費 / 入帳)
    dom.btnToggleExpense.addEventListener("click", () => {
      dom.btnToggleExpense.classList.add("active");
      dom.btnToggleExpense.setAttribute("aria-selected", "true");
      dom.btnToggleIncome.classList.remove("active");
      dom.btnToggleIncome.setAttribute("aria-selected", "false");

      dom.panelExpense.classList.remove("hidden");
      dom.panelIncome.classList.add("hidden");
    });

    dom.btnToggleIncome.addEventListener("click", () => {
      dom.btnToggleIncome.classList.add("active");
      dom.btnToggleIncome.setAttribute("aria-selected", "true");
      dom.btnToggleExpense.classList.remove("active");
      dom.btnToggleExpense.setAttribute("aria-selected", "false");

      dom.panelIncome.classList.remove("hidden");
      dom.panelExpense.classList.add("hidden");
    });

    // 快速展開分類建立區塊
    dom.btnOpenCreateExpenseCat.addEventListener("click", () => {
      dom.inlineCreateExpenseCat.classList.toggle("hidden");
    });

    dom.btnOpenCreateIncomeCat.addEventListener("click", () => {
      dom.inlineCreateIncomeCat.classList.toggle("hidden");
    });

    dom.btnSaveExpenseCat.addEventListener("click", handleCreateExpenseCategory);
    dom.btnSaveIncomeCat.addEventListener("click", handleCreateIncomeCategory);

    // 表單提交
    dom.formExpense.addEventListener("submit", (e) => {
      e.preventDefault();
      handleExpenseSubmit();
    });

    dom.formIncome.addEventListener("submit", (e) => {
      e.preventDefault();
      handleIncomeSubmit();
    });

    // 投資
    dom.btnFetchQuotes.addEventListener("click", handleFetchQuotes);

    // 發票重新整理
    dom.btnRefreshInvoices.addEventListener("click", () => {
      loadInvoicesData();
      showToast("已重新整理發票清單");
    });
  }

  // ==========================================
  // 啟動入口
  // ==========================================
  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    initConnection();
  });
})();

