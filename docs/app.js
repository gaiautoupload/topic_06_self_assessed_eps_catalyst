const data = window.TOPIC06_DATA;

const metricsEl = document.getElementById("metrics");
const eventListEl = document.getElementById("eventList");
const missingGridEl = document.getElementById("missingGrid");
const coverageBarsEl = document.getElementById("coverageBars");
const heroCoverageEl = document.getElementById("heroCoverage");
const filterButtons = Array.from(document.querySelectorAll(".filter-chip"));

let activeFilter = "all";

function fmtPct(value) {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(2)}%`;
}

function fmtNum(value) {
  if (value === null || value === undefined) return "N/A";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function buildMetrics() {
  const summary = data.summary;
  const cards = [
    ["候選事件", summary.events, "目前經規則收斂後保留的主題事件數"],
    ["價格覆蓋", `${Math.round(summary.coverage_ratio * 100)}%`, "有價格資料可接回測的事件比例"],
    ["交易筆數", summary.trades, "固定持有期 T+5 / T+10 / T+20 產生的交易"],
    ["平均報酬", fmtPct(summary.average_trade_return), "目前可回測樣本的平均交易報酬"],
  ];

  metricsEl.innerHTML = cards
    .map(
      ([label, value, note]) => `
        <article class="metric-card">
          <div class="eyebrow">${label}</div>
          <div class="metric-value">${value}</div>
          <div class="metric-note">${note}</div>
        </article>
      `
    )
    .join("");

  heroCoverageEl.textContent = `${Math.round(summary.coverage_ratio * 100)}%`;
}

function buildCoverageBars() {
  const summary = data.summary;
  const bars = [
    ["有價格資料", summary.priced_events, summary.events],
    ["缺價格資料", summary.missing_prices, summary.events],
    ["可算 PE", summary.events_with_implied_pe, summary.events],
  ];

  coverageBarsEl.innerHTML = bars
    .map(([label, value, total]) => {
      const pct = total ? (value / total) * 100 : 0;
      return `
        <div class="bar-card">
          <div class="bar-top">
            <span>${label}</span>
            <strong>${value}/${total}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct.toFixed(2)}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function matchesFilter(event) {
  if (activeFilter === "all") return true;
  if (activeFilter === "priced" || activeFilter === "missing_price") {
    return event.coverage === activeFilter;
  }
  return event.signal_strength === activeFilter;
}

function renderEvents() {
  const filtered = data.event_cards.filter(matchesFilter);
  eventListEl.innerHTML = filtered
    .map((event) => {
      const tradeMarkup = event.trades.length
        ? `
          <div class="trade-strip">
            ${event.trades
              .map((trade) => {
                const state = trade.return_pct >= 0 ? "positive" : "negative";
                return `
                  <div class="trade-pill ${state}">
                    <div class="mini-label">${trade.strategy_tag}</div>
                    <div class="mini-value">${fmtPct(trade.return_pct)}</div>
                  </div>
                `;
              })
              .join("")}
          </div>
        `
        : "";

      return `
        <article class="event-card">
          <div class="event-top">
            <div>
              <div class="eyebrow">${event.stock_id} / ${event.company_name} / ${event.announcement_date}</div>
              <h3 class="event-title">${event.title}</h3>
              <div class="badge-row">
                <span class="badge signal-${event.signal_strength}">${event.signal_strength} 級訊號</span>
                <span class="badge coverage-${event.coverage}">${event.coverage === "priced" ? "已接價格" : "待補價格"}</span>
                <span class="badge">${event.event_type}</span>
              </div>
            </div>
          </div>
          <div class="event-body">
            <div class="mini-stat">
              <div class="mini-label">EPS</div>
              <div class="mini-value">${fmtNum(event.eps_value)}</div>
            </div>
            <div class="mini-stat">
              <div class="mini-label">進場價</div>
              <div class="mini-value">${fmtNum(event.entry_close)}</div>
            </div>
            <div class="mini-stat">
              <div class="mini-label">Implied PE</div>
              <div class="mini-value">${fmtNum(event.implied_pe)}</div>
            </div>
            <div class="mini-stat">
              <div class="mini-label">平均報酬</div>
              <div class="mini-value">${fmtPct(event.avg_return_pct)}</div>
            </div>
          </div>
          ${tradeMarkup}
        </article>
      `;
    })
    .join("");
}

function renderMissing() {
  missingGridEl.innerHTML = data.missing_stock_ids
    .map((stockId) => `<div class="missing-chip">${stockId}</div>`)
    .join("");
}

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    filterButtons.forEach((node) => node.classList.toggle("is-active", node === button));
    renderEvents();
  });
});

buildMetrics();
buildCoverageBars();
renderEvents();
renderMissing();
