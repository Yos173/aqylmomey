(() => {
  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
  }

  const VERDICT_LABELS = { low: "🟢 Низкий риск", medium: "🟡 Средний риск", high: "🔴 Высокий риск" };

  async function loadRadar() {
    const container = document.getElementById("radar-content");
    container.innerHTML = '<div class="skeleton">Загрузка статистики...</div>';
    try {
      const response = await fetch("/api/radar/stats");
      if (!response.ok) throw new Error(`Ошибка запроса (${response.status})`);
      const data = await response.json();
      render(data);
    } catch (err) {
      container.innerHTML = `<div class="skeleton">${escapeHtml(err.message)}</div>`;
    }
  }

  function render(data) {
    const container = document.getElementById("radar-content");

    const verdictTiles = Object.entries(VERDICT_LABELS)
      .map(([key, label]) => {
        const count = data.verdict_breakdown[key] || 0;
        return `
          <div class="radar-tile">
            <div class="radar-tile-value">${count.toLocaleString("ru-RU")}</div>
            <div class="radar-tile-label">${label}</div>
          </div>
        `;
      })
      .join("");

    const maxCategoryCount = Math.max(1, ...data.top_categories.map((c) => c.count));
    const categoriesHtml = data.top_categories.length
      ? data.top_categories
          .map(
            (c) => `
            <div class="radar-bar-row">
              <div class="radar-bar-label">${escapeHtml(c.label)}</div>
              <div class="radar-bar-track">
                <div class="radar-bar-fill" style="width:${(c.count / maxCategoryCount) * 100}%"></div>
              </div>
              <div class="radar-bar-count">${c.count}</div>
            </div>
          `
          )
          .join("")
      : '<p class="hint">Пока недостаточно данных для топ-категорий.</p>';

    const maxTrendCount = Math.max(1, ...data.trend_by_day.map((d) => d.count));
    const trendHtml = data.trend_by_day.length
      ? `<div class="radar-trend">${data.trend_by_day
          .map((d) => {
            const heightPct = Math.max(4, (d.count / maxTrendCount) * 100);
            const shortDay = d.day.slice(5); // MM-DD
            return `
              <div class="radar-trend-col" title="${escapeHtml(d.day)}: ${d.count}">
                <div class="radar-trend-bar" style="height:${heightPct}%"></div>
                <div class="radar-trend-label">${escapeHtml(shortDay)}</div>
              </div>
            `;
          })
          .join("")}</div>`
      : '<p class="hint">Пока недостаточно данных для тренда.</p>';

    container.innerHTML = `
      <div class="card">
        <div class="radar-total">${data.total_checks.toLocaleString("ru-RU")}</div>
        <div class="hint">проверок всего</div>
      </div>
      <div class="radar-tiles">${verdictTiles}</div>
      <div class="card">
        <h3 style="margin-top:0;">Топ признаков мошенничества</h3>
        ${categoriesHtml}
      </div>
      <div class="card">
        <h3 style="margin-top:0;">Проверок по дням</h3>
        ${trendHtml}
      </div>
    `;
  }

  document.getElementById("radar-refresh-btn").addEventListener("click", loadRadar);
  loadRadar();
})();
