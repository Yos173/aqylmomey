(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  // telegram-web-app.js создаёт window.Telegram.WebApp всегда, даже вне Telegram (с пустым initData) —
  // поэтому "мы внутри Telegram?" нужно проверять по непустому initData, а не по наличию tg самого по себе.
  const isTelegram = !!(tg && tg.initData);

  function applyTheme() {
    if (!tg) return;
    const params = tg.themeParams || {};
    const root = document.documentElement.style;
    const map = {
      bg_color: "--tg-theme-bg-color",
      text_color: "--tg-theme-text-color",
      hint_color: "--tg-theme-hint-color",
      link_color: "--tg-theme-link-color",
      button_color: "--tg-theme-button-color",
      button_text_color: "--tg-theme-button-text-color",
      secondary_bg_color: "--tg-theme-secondary-bg-color",
      section_bg_color: "--tg-theme-section-bg-color",
    };
    for (const [key, cssVar] of Object.entries(map)) {
      if (params[key]) root.setProperty(cssVar, params[key]);
    }
  }

  if (tg) {
    tg.ready();
    tg.expand();
    applyTheme();
    tg.onEvent("themeChanged", applyTheme);
  }
  if (isTelegram) {
    document.querySelectorAll(".header-nav").forEach((el) => (el.style.display = "none"));
  }

  // ---------- Веб-сессия (сайт, без пароля) ----------
  const SESSION_TOKEN_KEY = "aqm_session_token";
  const SESSION_NICKNAME_KEY = "aqm_nickname";

  function getSessionToken() {
    return localStorage.getItem(SESSION_TOKEN_KEY) || "";
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
  }

  function formatTenge(n) {
    return Math.round(n).toLocaleString("ru-RU") + " тенге";
  }

  function formatUsd(n) {
    return "$" + Number(n).toFixed(2);
  }

  function formatPct(n, digits = 1) {
    const sign = n >= 0 ? "+" : "";
    return `${sign}${n.toFixed(digits)}%`;
  }

  let toastTimer = null;
  function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.style.background = isError ? "var(--red)" : "var(--tg-text)";
    toast.style.color = isError ? "#fff" : "var(--tg-bg)";
    toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 3200);
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    const sessionToken = getSessionToken();
    if (sessionToken) {
      headers["X-Web-Session-Token"] = sessionToken;
    } else if (isTelegram) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    }
    const response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      data = null;
    }
    if (!response.ok) {
      if (response.status === 401 && sessionToken) {
        // Сессия ссылается на web_users, которых больше нет (например, база сбросилась при
        // передеплое на Render — диск эфемерный) — сбрасываем токен и просим онбординг заново
        // вместо того, чтобы пользователь навсегда застрял на ошибке "недействительный токен".
        localStorage.removeItem(SESSION_TOKEN_KEY);
        localStorage.removeItem(SESSION_NICKNAME_KEY);
        location.reload();
        throw new Error("Сессия устарела — обновляю страницу...");
      }
      const detail = (data && data.detail) || `Ошибка запроса (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }

  // ---------- Онбординг (ник + школа, без пароля) ----------
  function ensureOnboarded() {
    if (isTelegram) return Promise.resolve(); // в Telegram identity уже есть, регистрация не нужна
    if (getSessionToken()) return Promise.resolve();

    const overlay = document.getElementById("onboarding-overlay");
    overlay.classList.remove("hidden");

    return new Promise((resolve) => {
      document.getElementById("onboarding-submit-btn").addEventListener("click", async () => {
        const nickname = document.getElementById("onboarding-nickname").value.trim();
        if (!nickname) {
          showToast("Введите ник", true);
          return;
        }
        const school = document.getElementById("onboarding-school").value.trim() || null;
        const grade = document.getElementById("onboarding-grade").value.trim() || null;
        try {
          const result = await api("/api/auth/register", { method: "POST", body: { nickname, school, grade } });
          localStorage.setItem(SESSION_TOKEN_KEY, result.session_token);
          localStorage.setItem(SESSION_NICKNAME_KEY, result.nickname);
          overlay.classList.add("hidden");
          resolve();
        } catch (err) {
          showToast(err.message, true);
        }
      });
    });
  }

  // ---------- Main tabs ----------
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");
  let investOpened = false;
  let ratingOpened = false;

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => b.classList.toggle("active", b === btn));
      const target = btn.dataset.tab;
      tabPanels.forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${target}`));
      if (target !== "invest") {
        stopMarketsPolling();
        stopInstrumentPolling();
      }
      if (target === "budget") loadBudgetSummary();
      if (target === "invest" && !investOpened) {
        investOpened = true;
        loadPortfolio();
      }
      if (target === "rating" && !ratingOpened) {
        ratingOpened = true;
        showRatingSubtab("quiz");
      }
    });
  });

  // ---------- Antifraud ----------
  const antifraudTextEl = document.getElementById("antifraud-text");
  const antifraudResultEl = document.getElementById("antifraud-result");
  const antifraudBtn = document.getElementById("antifraud-check-btn");

  function renderAntifraudResult(result, transcribedText) {
    antifraudResultEl.className = `result-box risk-${result.verdict}`;

    const sourceBadge =
      result.score_source === "rules+ai"
        ? '<span class="pill up" style="margin-left:6px;">🤖 оценено ИИ</span>'
        : "";
    const transcribedHtml = transcribedText
      ? `<div class="hint" style="margin-bottom:8px;">Распознанный текст: «${escapeHtml(transcribedText)}»</div>`
      : "";
    const aiFlagsHtml =
      result.ai_red_flags && result.ai_red_flags.length
        ? `<div style="margin-top:8px;">
             <span class="row-sub">Дополнительно от ИИ:</span>
             <ul style="margin:4px 0 0; padding-left:18px;">
               ${result.ai_red_flags.map((flag) => `<li style="font-size:13px;">${escapeHtml(flag)}</li>`).join("")}
             </ul>
           </div>`
        : "";

    antifraudResultEl.innerHTML = `
      ${transcribedHtml}
      <div><strong>${escapeHtml(result.verdict_title)}</strong>${sourceBadge}</div>
      <div>Оценка риска: ${result.score}/100</div>
      <div style="margin-top:8px;">${escapeHtml(result.explanation)}</div>
      ${aiFlagsHtml}
      <div style="margin-top:8px; color: var(--tg-hint); font-size:12px;">
        Это автоматическая обучающая оценка, а не юридическое заключение. При сомнениях не переводите деньги
        и не сообщайте коды из СМС.
      </div>
    `;
    antifraudResultEl.classList.remove("hidden");
  }

  antifraudBtn.addEventListener("click", async () => {
    const text = antifraudTextEl.value.trim();
    if (!text) {
      showToast("Введите текст для проверки", true);
      return;
    }
    antifraudBtn.disabled = true;
    antifraudBtn.textContent = "Проверяю...";
    try {
      const result = await api("/api/antifraud/check", { method: "POST", body: { text } });
      renderAntifraudResult(result);
    } catch (err) {
      showToast(err.message, true);
    } finally {
      antifraudBtn.disabled = false;
      antifraudBtn.textContent = "Проверить текст";
    }
  });

  const antifraudImageInput = document.getElementById("antifraud-image-input");
  antifraudImageInput.addEventListener("change", () => {
    const file = antifraudImageInput.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = String(reader.result).split(",")[1] || "";
      antifraudBtn.disabled = true;
      try {
        const result = await api("/api/antifraud/check-image", {
          method: "POST",
          body: { image_base64: base64, media_type: file.type || "image/png" },
        });
        renderAntifraudResult(result, result.transcribed_text);
      } catch (err) {
        showToast(err.message, true);
      } finally {
        antifraudBtn.disabled = false;
        antifraudImageInput.value = "";
      }
    };
    reader.readAsDataURL(file);
  });

  // ---------- Budget ----------
  const budgetKindButtons = document.querySelectorAll("#budget-kind .segmented-btn");
  let budgetKind = "income";
  budgetKindButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      budgetKindButtons.forEach((b) => b.classList.toggle("active", b === btn));
      budgetKind = btn.dataset.kind;
      document.getElementById("budget-category").placeholder =
        budgetKind === "income" ? "Источник (например: стипендия)" : "Категория (например: еда)";
    });
  });

  async function loadBudgetSummary() {
    const card = document.getElementById("budget-summary-card");
    try {
      const summary = await api("/api/budget/summary");
      renderBudgetSummary(summary);
    } catch (err) {
      card.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderBudgetSummary(summary) {
    const card = document.getElementById("budget-summary-card");
    let topHtml = "";
    if (summary.top_expenses.length) {
      topHtml =
        '<div style="margin-top:10px;">' +
        summary.top_expenses
          .map(
            (item) =>
              `<div class="row"><span class="row-title">${escapeHtml(item.category)}</span><span class="row-value">${formatTenge(item.amount)}</span></div>`
          )
          .join("") +
        "</div>";
    }
    card.innerHTML = `
      <div class="row"><span class="row-title">Доходы</span><span class="row-value">${formatTenge(summary.income)}</span></div>
      <div class="row"><span class="row-title">Расходы</span><span class="row-value">${formatTenge(summary.expense)}</span></div>
      <div class="total-row"><span>Баланс</span><span>${formatTenge(summary.balance)}</span></div>
      ${topHtml}
    `;
  }

  document.getElementById("budget-add-btn").addEventListener("click", async () => {
    const amountEl = document.getElementById("budget-amount");
    const categoryEl = document.getElementById("budget-category");
    const amount = parseFloat(String(amountEl.value).replace(",", "."));
    if (!amount || amount <= 0) {
      showToast("Введите корректную сумму", true);
      return;
    }
    const defaultCategory = budgetKind === "income" ? "доход" : "прочее";
    const category = categoryEl.value.trim() || defaultCategory;
    try {
      const summary = await api("/api/budget/transaction", {
        method: "POST",
        body: { kind: budgetKind, category, amount },
      });
      renderBudgetSummary(summary);
      amountEl.value = "";
      categoryEl.value = "";
      showToast("Записал операцию");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // ---------- Invest ----------
  const investSubtabButtons = document.querySelectorAll("#panel-invest .sub-tab-btn");
  const investSubpanels = document.querySelectorAll("#panel-invest .sub-panel");
  let marketsCache = null;
  let currentInstrumentReturnTo = "markets";
  let activeChart = null;

  // ---------- Живые котировки: пока вкладка "Рынки" или карточка инструмента открыты, тихо
  // обновляем цены каждые ~17 сек. Сервер сам кэширует котировки на 2 минуты (см. market_data.py),
  // так что частый опрос с фронта не бьёт лишний раз в Yahoo Finance и не рискует rate-limit.
  const LIVE_POLL_MS = 17000;
  let marketsPollTimer = null;
  let instrumentPollTimer = null;
  let currentInstrumentTicker = null;

  function stopMarketsPolling() {
    if (marketsPollTimer) {
      clearInterval(marketsPollTimer);
      marketsPollTimer = null;
    }
  }

  function startMarketsPolling() {
    stopMarketsPolling();
    marketsPollTimer = setInterval(async () => {
      if (document.hidden) return;
      try {
        marketsCache = await api("/api/invest/markets");
        renderMarketsList();
      } catch (err) {
        // Тихий фоновый рефреш — на экране просто остаются последние известные цены.
      }
    }, LIVE_POLL_MS);
  }

  function stopInstrumentPolling() {
    if (instrumentPollTimer) {
      clearInterval(instrumentPollTimer);
      instrumentPollTimer = null;
    }
  }

  function startInstrumentPolling(ticker) {
    stopInstrumentPolling();
    instrumentPollTimer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const data = await api(`/api/invest/instrument/${encodeURIComponent(ticker)}`);
        updateInstrumentPrice(data);
      } catch (err) {
        // Тихий фоновый рефреш.
      }
    }, LIVE_POLL_MS);
  }

  investSubtabButtons.forEach((btn) => {
    btn.addEventListener("click", () => showInvestSubtab(btn.dataset.subtab));
  });

  function showInvestSubtab(name) {
    investSubtabButtons.forEach((b) => b.classList.toggle("active", b.dataset.subtab === name));
    investSubpanels.forEach((panel) => panel.classList.toggle("active", panel.id === `invest-${name}`));
    stopMarketsPolling();
    stopInstrumentPolling();
    if (name === "portfolio") loadPortfolio();
    if (name === "markets") {
      loadMarkets();
      startMarketsPolling();
    }
  }

  function showInstrumentPanel(returnTo) {
    currentInstrumentReturnTo = returnTo;
    investSubtabButtons.forEach((b) => b.classList.remove("active"));
    investSubpanels.forEach((panel) => panel.classList.toggle("active", panel.id === "invest-instrument"));
    stopMarketsPolling();
  }

  document.getElementById("instrument-back-btn").addEventListener("click", () => {
    showInvestSubtab(currentInstrumentReturnTo);
  });

  async function loadPortfolio() {
    const container = document.getElementById("portfolio-content");
    container.innerHTML = '<div class="skeleton">Загрузка портфеля...</div>';
    try {
      const data = await api("/api/invest/portfolio");
      renderPortfolio(data);
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderPortfolio(data) {
    const container = document.getElementById("portfolio-content");
    if (!data.has_portfolio) {
      container.innerHTML = `
        <div class="card">
          <p>У вас ещё нет портфеля.</p>
          <button class="btn primary" id="portfolio-quiz-btn">📝 Пройти риск-квиз</button>
          <button class="btn secondary" id="portfolio-markets-btn">📉 Перейти к рынкам</button>
        </div>
      `;
      document.getElementById("portfolio-quiz-btn").addEventListener("click", startQuiz);
      document.getElementById("portfolio-markets-btn").addEventListener("click", () => showInvestSubtab("markets"));
      return;
    }

    let holdingsHtml = '<p class="hint">Активов пока нет — загляните в «Рынки», чтобы купить.</p>';
    if (data.holdings.length) {
      holdingsHtml = data.holdings
        .map((h) => {
          const pnlClass = h.pnl_pct >= 0 ? "up" : "down";
          return `
            <div class="list-item" data-ticker="${escapeHtml(h.ticker)}">
              <div>
                <div class="row-title">${escapeHtml(h.ticker)}</div>
                <div class="row-sub">${h.shares.toFixed(4)} шт. · ${escapeHtml(h.name)}</div>
              </div>
              <div style="text-align:right;">
                <div class="row-value">${formatTenge(h.current_value)}</div>
                <span class="pill ${pnlClass}">${formatPct(h.pnl_pct)}</span>
              </div>
            </div>
          `;
        })
        .join("");
    }

    container.innerHTML = `
      <div class="card">
        <div class="row"><span class="row-title">Риск-профиль</span><span class="row-value">${escapeHtml(data.risk_profile_title)}</span></div>
        <div class="row"><span class="row-title">Свободные тенге</span><span class="row-value">${formatTenge(data.virtual_cash)}</span></div>
      </div>
      <div class="card">
        ${holdingsHtml}
        <div class="total-row"><span>Итого с кэшем</span><span>${formatTenge(data.total_value)}</span></div>
      </div>
      <button class="btn secondary" id="portfolio-requiz-btn">🔄 Пройти квиз заново</button>
    `;

    container.querySelectorAll(".list-item").forEach((item) => {
      item.addEventListener("click", () => openInstrument(item.dataset.ticker, "portfolio"));
    });
    document.getElementById("portfolio-requiz-btn").addEventListener("click", startQuiz);
  }

  let activeMarketCategory = "stock";

  async function loadMarkets() {
    const listEl = document.getElementById("markets-list");
    if (!marketsCache) {
      listEl.innerHTML = '<div class="skeleton">Загрузка котировок...</div>';
      try {
        marketsCache = await api("/api/invest/markets");
      } catch (err) {
        listEl.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
        return;
      }
      renderMarketCategoryButtons();
    }
    renderMarketsList();
  }

  function renderMarketCategoryButtons() {
    const container = document.getElementById("market-category");
    const categories = Object.keys(marketsCache.titles);
    if (!categories.includes(activeMarketCategory)) activeMarketCategory = categories[0];

    container.innerHTML = categories
      .map(
        (cat) =>
          `<button class="segmented-btn${cat === activeMarketCategory ? " active" : ""}" data-category="${escapeHtml(cat)}">${escapeHtml(marketsCache.titles[cat])}</button>`
      )
      .join("");

    container.querySelectorAll(".segmented-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        container.querySelectorAll(".segmented-btn").forEach((b) => b.classList.toggle("active", b === btn));
        activeMarketCategory = btn.dataset.category;
        renderMarketsList();
      });
    });
  }

  function renderMarketsList() {
    const listEl = document.getElementById("markets-list");
    if (!marketsCache) return;
    const items = marketsCache.categories[activeMarketCategory] || [];
    listEl.innerHTML = items
      .map((item) => {
        if (item.price === null) {
          return `
            <div class="list-item" data-ticker="${escapeHtml(item.ticker)}">
              <div>
                <div class="row-title">${escapeHtml(item.ticker)}</div>
                <div class="row-sub">${escapeHtml(item.name)}</div>
              </div>
              <div class="row-sub">цена недоступна</div>
            </div>
          `;
        }
        const pillClass = item.change_pct >= 0 ? "up" : "down";
        return `
          <div class="list-item" data-ticker="${escapeHtml(item.ticker)}">
            <div>
              <div class="row-title">${escapeHtml(item.ticker)}</div>
              <div class="row-sub">${escapeHtml(item.name)}</div>
            </div>
            <div style="text-align:right;">
              <div class="row-value">${formatUsd(item.price)}</div>
              <span class="pill ${pillClass}">${formatPct(item.change_pct, 2)}</span>
            </div>
          </div>
        `;
      })
      .join("");
    listEl.querySelectorAll(".list-item").forEach((el) => {
      el.addEventListener("click", () => openInstrument(el.dataset.ticker, "markets"));
    });
  }

  async function openInstrument(ticker, returnTo) {
    showInstrumentPanel(returnTo);
    currentInstrumentTicker = ticker;
    const container = document.getElementById("instrument-content");
    container.innerHTML = '<div class="skeleton">Загрузка...</div>';
    try {
      const data = await api(`/api/invest/instrument/${encodeURIComponent(ticker)}`);
      renderInstrument(data);
      startInstrumentPolling(ticker);
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderPriceSlot(data) {
    return data.price === null
      ? '<p class="hint">Цена сейчас недоступна, попробуйте позже.</p>'
      : `<div class="row"><span class="row-title">Цена</span><span class="row-value">${formatUsd(data.price)}
          <span class="pill ${data.change_pct >= 0 ? "up" : "down"}">${formatPct(data.change_pct, 2)}</span></span></div>`;
  }

  function updateInstrumentPrice(data) {
    // Пользователь мог уже уйти с этой карточки, пока летел запрос — не затираем чужой экран.
    if (data.ticker !== currentInstrumentTicker) return;
    const slot = document.getElementById("instrument-price-slot");
    if (slot) slot.innerHTML = renderPriceSlot(data);
  }

  function renderInstrument(data) {
    const container = document.getElementById("instrument-content");
    const categoryLabel = data.category === "stock" ? "Акция" : "Фонд (ETF)";
    const priceHtml = `<div id="instrument-price-slot">${renderPriceSlot(data)}</div>`;
    const heldHtml =
      data.held_shares > 1e-9
        ? `<div class="row"><span class="row-title">У вас</span><span class="row-value">${data.held_shares.toFixed(4)} шт.</span></div>`
        : "";

    container.innerHTML = `
      <div class="card">
        <h2 style="margin:0 0 4px;">${escapeHtml(data.ticker)}</h2>
        <p class="row-sub" style="margin:0 0 10px;">${escapeHtml(data.name)} · ${categoryLabel}</p>
        ${priceHtml}
        ${heldHtml}
        <div id="instrument-chart" style="height:180px; margin-top:10px;"></div>
      </div>
      <div class="card">
        <h3 style="margin-top:0;">Купить</h3>
        <input type="number" id="buy-amount" placeholder="Сумма, тенге" inputmode="decimal" />
        <button class="btn primary" id="buy-btn">💵 Купить</button>
      </div>
      ${
        data.held_shares > 1e-9
          ? `
      <div class="card">
        <h3 style="margin-top:0;">Продать</h3>
        <input type="number" id="sell-amount" placeholder="Количество, шт." inputmode="decimal" />
        <button class="btn secondary" id="sell-btn">Продать количество</button>
        <button class="btn danger" id="sell-all-btn">Продать всё (${data.held_shares.toFixed(4)} шт.)</button>
      </div>`
          : ""
      }
    `;

    document.getElementById("buy-btn").addEventListener("click", async () => {
      const amountEl = document.getElementById("buy-amount");
      const amount = parseFloat(String(amountEl.value).replace(",", "."));
      if (!amount || amount <= 0) {
        showToast("Введите сумму покупки", true);
        return;
      }
      try {
        const result = await api("/api/invest/buy", { method: "POST", body: { ticker: data.ticker, amount } });
        showToast(`Куплено ${result.bought_shares.toFixed(4)} ${result.ticker}`);
        marketsCache = null;
        await openInstrument(data.ticker, currentInstrumentReturnTo);
      } catch (err) {
        showToast(err.message, true);
      }
    });

    const sellBtn = document.getElementById("sell-btn");
    if (sellBtn) {
      sellBtn.addEventListener("click", async () => {
        const amountEl = document.getElementById("sell-amount");
        const shares = parseFloat(String(amountEl.value).replace(",", "."));
        if (!shares || shares <= 0) {
          showToast("Введите количество для продажи", true);
          return;
        }
        await doSell(data.ticker, { shares });
      });
    }

    const sellAllBtn = document.getElementById("sell-all-btn");
    if (sellAllBtn) {
      sellAllBtn.addEventListener("click", () => doSell(data.ticker, { sell_all: true }));
    }

    renderInstrumentChart(data.ticker);
  }

  function themeColor(cssVar, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
    return value || fallback;
  }

  async function renderInstrumentChart(ticker) {
    const container = document.getElementById("instrument-chart");
    if (!container || typeof LightweightCharts === "undefined") return;

    if (activeChart) {
      activeChart.remove();
      activeChart = null;
    }

    try {
      const data = await api(`/api/invest/instrument/${encodeURIComponent(ticker)}/history`);
      if (!data.points || data.points.length < 2) {
        container.innerHTML = '<p class="hint">Недостаточно данных для графика.</p>';
        return;
      }

      const chart = LightweightCharts.createChart(container, {
        height: 180,
        layout: {
          background: { type: "solid", color: "transparent" },
          textColor: themeColor("--tg-hint", "#8e8e93"),
        },
        grid: {
          vertLines: { visible: false },
          horzLines: { color: themeColor("--border-color", "rgba(0,0,0,0.08)") },
        },
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false },
        handleScroll: false,
        handleScale: false,
      });

      const accent = themeColor("--tg-button", "#2481cc");
      const series = chart.addSeries(LightweightCharts.AreaSeries, {
        lineColor: accent,
        topColor: accent + "55",
        bottomColor: accent + "05",
        lineWidth: 2,
      });
      series.setData(data.points);
      chart.timeScale().fitContent();

      activeChart = chart;
    } catch (err) {
      container.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
    }
  }

  async function doSell(ticker, payload) {
    try {
      const result = await api("/api/invest/sell", { method: "POST", body: { ticker, ...payload } });
      showToast(`Продано ${result.sold_shares.toFixed(4)} ${result.ticker} (${formatPct(result.pnl_pct)})`);
      marketsCache = null;
      await openInstrument(ticker, currentInstrumentReturnTo);
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // ---------- Risk quiz ----------
  let quizQuestions = null;
  let quizAnswers = [];

  async function startQuiz() {
    investSubtabButtons.forEach((b) => b.classList.remove("active"));
    investSubpanels.forEach((panel) => panel.classList.toggle("active", panel.id === "invest-quiz"));
    quizAnswers = [];

    const container = document.getElementById("quiz-content");
    container.innerHTML = '<div class="skeleton">Загрузка вопросов...</div>';
    if (!quizQuestions) {
      try {
        const data = await api("/api/invest/quiz-questions");
        quizQuestions = data.questions;
      } catch (err) {
        container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
        return;
      }
    }
    renderQuizStep(0);
  }

  function renderQuizStep(index) {
    const container = document.getElementById("quiz-content");
    const question = quizQuestions[index];
    const questionText = question.text.replace(/^\d+\/\d+\.\s*/, "");
    const optionsHtml = question.options
      .map((opt) => `<button class="btn secondary quiz-option" data-value="${opt[1]}">${escapeHtml(opt[0])}</button>`)
      .join("");
    container.innerHTML = `
      <div class="card">
        <div class="quiz-question">${index + 1}/${quizQuestions.length}. ${escapeHtml(questionText)}</div>
        ${optionsHtml}
      </div>
    `;
    container.querySelectorAll(".quiz-option").forEach((btn) => {
      btn.addEventListener("click", () => {
        quizAnswers.push(Number(btn.dataset.value));
        if (index + 1 < quizQuestions.length) {
          renderQuizStep(index + 1);
        } else {
          submitQuiz();
        }
      });
    });
  }

  async function submitQuiz() {
    const container = document.getElementById("quiz-content");
    container.innerHTML = '<div class="skeleton">Считаю портфель по текущим рыночным ценам...</div>';
    try {
      const result = await api("/api/invest/quiz", { method: "POST", body: { answers: quizAnswers } });
      const holdingsHtml = result.holdings
        .map(
          (h) =>
            `<div class="row"><span class="row-title">${escapeHtml(h.ticker)}</span><span class="row-value">${(h.weight * 100).toFixed(0)}% · ${formatUsd(h.price)}</span></div>`
        )
        .join("");
      container.innerHTML = `
        <div class="card">
          <p>✅ Риск-профиль: <strong>${escapeHtml(result.risk_profile_title)}</strong></p>
          <p>Стартовый капитал: ${formatTenge(result.virtual_cash_start)}</p>
          ${holdingsHtml}
        </div>
        <button class="btn primary" id="quiz-done-btn">К портфелю</button>
      `;
      document.getElementById("quiz-done-btn").addEventListener("click", () => showInvestSubtab("portfolio"));
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  // ---------- Rating: financial IQ quiz, badges, leaderboard ----------
  const ratingSubtabButtons = document.querySelectorAll("#panel-rating .sub-tab-btn");
  const ratingSubpanels = document.querySelectorAll("#panel-rating .sub-panel");

  ratingSubtabButtons.forEach((btn) => {
    btn.addEventListener("click", () => showRatingSubtab(btn.dataset.subtab));
  });

  function showRatingSubtab(name) {
    ratingSubtabButtons.forEach((b) => b.classList.toggle("active", b.dataset.subtab === name));
    ratingSubpanels.forEach((panel) => panel.classList.toggle("active", panel.id === `rating-${name}`));
    if (name === "quiz") loadFinancialQuiz();
    if (name === "badges") loadBadges();
    if (name === "leaderboard") loadLeaderboard();
  }

  let fiqQuestions = null;
  let fiqAnswers = [];

  async function loadFinancialQuiz() {
    const container = document.getElementById("fiq-content");
    container.innerHTML = '<div class="skeleton">Загрузка вопросов...</div>';
    fiqAnswers = [];
    try {
      if (!fiqQuestions) {
        const data = await api("/api/quiz/financial-iq/questions");
        fiqQuestions = data.questions;
      }
      renderFiqStep(0);
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderFiqStep(index) {
    const container = document.getElementById("fiq-content");
    const question = fiqQuestions[index];
    const optionsHtml = question.options
      .map((opt, i) => `<button class="btn secondary fiq-option" data-value="${i}">${escapeHtml(opt)}</button>`)
      .join("");
    container.innerHTML = `
      <div class="card">
        <div class="quiz-question">${index + 1}/${fiqQuestions.length}. ${escapeHtml(question.text)}</div>
        ${optionsHtml}
      </div>
    `;
    container.querySelectorAll(".fiq-option").forEach((btn) => {
      btn.addEventListener("click", () => {
        fiqAnswers.push(Number(btn.dataset.value));
        if (index + 1 < fiqQuestions.length) {
          renderFiqStep(index + 1);
        } else {
          submitFinancialQuiz();
        }
      });
    });
  }

  async function submitFinancialQuiz() {
    const container = document.getElementById("fiq-content");
    container.innerHTML = '<div class="skeleton">Считаю результат...</div>';
    try {
      const result = await api("/api/quiz/financial-iq/submit", { method: "POST", body: { answers: fiqAnswers } });
      const earnedHtml = result.badges
        .filter((b) => b.earned)
        .map((b) => `<span class="badge-chip">${b.icon} ${escapeHtml(b.title)}</span>`)
        .join("");
      const mistakes = result.review || [];
      const reviewToggleHtml = mistakes.length
        ? `<button class="btn secondary" id="fiq-review-btn">📖 Разбор ошибок (${mistakes.length})</button>`
        : `<p class="hint" style="margin-top:12px;">Все ответы верные — отличный результат! 🎉</p>`;

      container.innerHTML = `
        <div class="card">
          <p>✅ Результат: <strong>${result.score}/${result.total}</strong></p>
          ${earnedHtml ? `<p class="hint" style="margin-top:12px;">Заработанные бэйджи:</p><div class="badge-row">${earnedHtml}</div>` : ""}
          ${reviewToggleHtml}
          <div id="fiq-review-list" class="hidden" style="margin-top:12px;"></div>
        </div>
        <div class="card">
          <p class="hint">Хотите разобрать ошибки подробнее или узнать что-то новое по теме?</p>
          <button class="btn secondary" id="fiq-ask-ai-btn">🤖 Спросить AI-помощника</button>
        </div>
        <button class="btn secondary" id="fiq-retry-btn">Пройти ещё раз</button>
      `;

      const reviewBtn = document.getElementById("fiq-review-btn");
      if (reviewBtn) {
        reviewBtn.addEventListener("click", () => {
          const listEl = document.getElementById("fiq-review-list");
          const wasHidden = listEl.classList.contains("hidden");
          if (wasHidden) {
            listEl.innerHTML = mistakes
              .map(
                (m) => `
                  <div class="list-item" style="display:block;">
                    <div class="row-title">${escapeHtml(m.question)}</div>
                    ${m.your_answer ? `<div class="row-sub">Ваш ответ: ${escapeHtml(m.your_answer)}</div>` : ""}
                    <div class="row-sub">Правильно: ${escapeHtml(m.correct_answer)}</div>
                    <div class="hint" style="margin-top:4px;">${escapeHtml(m.explanation)}</div>
                  </div>
                `
              )
              .join("");
          }
          listEl.classList.toggle("hidden", !wasHidden);
          reviewBtn.textContent = wasHidden ? "📖 Скрыть разбор" : `📖 Разбор ошибок (${mistakes.length})`;
        });
      }

      document.getElementById("fiq-ask-ai-btn").addEventListener("click", () => {
        const question = mistakes.length
          ? `Я ошибся в финансовом квизе по темам: ${mistakes.map((m) => m.question).join(" / ")}. Объясни эти темы простыми словами и приведи примеры.`
          : "Я прошёл финансовый квиз без ошибок — расскажи что-нибудь новое и полезное про личные финансы или инвестиции.";
        const assistantTabBtn = document.querySelector('.tab-btn[data-tab="assistant"]');
        if (assistantTabBtn) assistantTabBtn.click();
        assistantQuestionEl.value = question;
        assistantQuestionEl.focus();
      });

      document.getElementById("fiq-retry-btn").addEventListener("click", loadFinancialQuiz);
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadBadges() {
    const container = document.getElementById("badges-content");
    container.innerHTML = '<div class="skeleton">Загрузка...</div>';
    try {
      const data = await api("/api/me/badges");
      container.innerHTML = data.badges
        .map(
          (b) => `
          <div class="list-item" style="cursor:default;">
            <div>
              <div class="row-title">${b.icon} ${escapeHtml(b.title)}</div>
              <div class="row-sub">${escapeHtml(b.description)}</div>
            </div>
            <span class="pill ${b.earned ? "up" : "neutral"}">${b.earned ? "получен" : "нет"}</span>
          </div>
        `
        )
        .join("");
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadLeaderboard() {
    const container = document.getElementById("leaderboard-content");
    container.innerHTML = '<div class="skeleton">Загрузка...</div>';
    try {
      const data = await api("/api/leaderboard");
      if (!data.entries.length) {
        container.innerHTML = '<p class="hint">Пока никто не прошёл IQ-квиз. Будьте первым!</p>';
        return;
      }
      container.innerHTML = data.entries
        .map((e, i) => {
          const schoolPart = e.school ? ` <span class="row-sub">(${escapeHtml(e.school)})</span>` : "";
          return `
            <div class="row">
              <span class="row-title">${i + 1}. ${escapeHtml(e.nickname)}${schoolPart}</span>
              <span class="row-value">${e.best_score}/${e.total}</span>
            </div>
          `;
        })
        .join("");
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  // ---------- AI-помощник (коуч + советник, один чат без истории) ----------
  const assistantQuestionEl = document.getElementById("assistant-question");
  const assistantResultEl = document.getElementById("assistant-result");
  const assistantAskBtn = document.getElementById("assistant-ask-btn");

  assistantAskBtn.addEventListener("click", async () => {
    const question = assistantQuestionEl.value.trim();
    if (!question) {
      showToast("Введите вопрос", true);
      return;
    }
    assistantAskBtn.disabled = true;
    assistantAskBtn.textContent = "Думаю...";
    try {
      const result = await api("/api/assistant/ask", { method: "POST", body: { question } });
      assistantResultEl.className = "result-box";
      assistantResultEl.innerHTML = escapeHtml(result.answer);
      assistantResultEl.classList.remove("hidden");
    } catch (err) {
      showToast(err.message, true);
    } finally {
      assistantAskBtn.disabled = false;
      assistantAskBtn.textContent = "Спросить";
    }
  });

  ensureOnboarded();
})();
