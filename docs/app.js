const data = window.TOPIC06_DATA;
const page = document.body.dataset.page;
let activeFilter = "all";

function fmtPct(value) {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(2)}%`;
}

function fmtNum(value) {
  if (value === null || value === undefined) return "N/A";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function buildMetricCards(targetId, cards) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.innerHTML = cards.map(([label, value, note]) => `
    <article class="metric-card">
      <div class="eyebrow">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-note">${note}</div>
    </article>
  `).join("");
}

function eventCard(event) {
  const trades = event.trades || [];
  const tradeMarkup = trades.length ? `
    <div class="trade-strip">
      ${trades.map((trade) => `
        <div class="trade-pill ${trade.return_pct >= 0 ? "positive" : "negative"}">
          <div class="mini-label">${trade.strategy_tag}</div>
          <div class="mini-value">${fmtPct(trade.return_pct)}</div>
        </div>
      `).join("")}
    </div>
  ` : "";

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
}

function renderEventList(targetId, events, emptyText) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!events.length) {
    target.innerHTML = `<div class="empty-state">${emptyText}</div>`;
    return;
  }
  target.innerHTML = events.map(eventCard).join("");
}

function buildCoverageBars() {
  const target = document.getElementById("coverageBars");
  if (!target) return;
  const summary = data.summary;
  const bars = [
    ["有價格資料", summary.priced_events, summary.events],
    ["缺價格資料", summary.missing_prices, summary.events],
    ["可算 PE", summary.events_with_implied_pe, summary.events],
  ];
  target.innerHTML = bars.map(([label, value, total]) => {
    const pct = total ? (value / total) * 100 : 0;
    return `
      <div class="bar-card">
        <div class="bar-top"><span>${label}</span><strong>${value}/${total}</strong></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct.toFixed(2)}%"></div></div>
      </div>
    `;
  }).join("");
}

function renderMissing() {
  const target = document.getElementById("missingGrid");
  if (!target) return;
  target.innerHTML = data.missing_stock_ids.map((stockId) => `<div class="missing-chip">${stockId}</div>`).join("");
}

function matchesPastFilter(event) {
  if (activeFilter === "all") return true;
  if (activeFilter === "priced" || activeFilter === "missing_price") return event.coverage === activeFilter;
  return event.signal_strength === activeFilter;
}

function wirePastFilters() {
  const buttons = Array.from(document.querySelectorAll(".filter-chip"));
  if (!buttons.length) return;
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      buttons.forEach((node) => node.classList.toggle("is-active", node === button));
      const filtered = data.past_events.filter(matchesPastFilter);
      renderEventList("pastList", filtered, "目前沒有符合這個條件的過去事件。");
    });
  });
}

function renderTradeTable() {
  const target = document.getElementById("tradeTable");
  if (!target) return;
  const trades = [];
  data.event_cards.forEach((event) => {
    event.trades.forEach((trade) => trades.push({
      stock_id: event.stock_id,
      company_name: event.company_name,
      strategy_tag: trade.strategy_tag,
      entry_date: trade.entry_date,
      exit_date: trade.exit_date,
      return_pct: trade.return_pct,
    }));
  });
  if (!trades.length) {
    target.innerHTML = `<div class="empty-state">目前還沒有可展示的交易資料。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>事件</div>
      <div>策略</div>
      <div>進場</div>
      <div>出場</div>
      <div>報酬</div>
    </div>
    ${trades.map((trade) => `
      <div class="trade-row">
        <div>${trade.stock_id} / ${trade.company_name}</div>
        <div>${trade.strategy_tag}</div>
        <div>${trade.entry_date}</div>
        <div>${trade.exit_date}</div>
        <div class="${trade.return_pct >= 0 ? "positive-text" : "negative-text"}">${fmtPct(trade.return_pct)}</div>
      </div>
    `).join("")}
  `;
}

function initHome() {
  const summary = data.summary;
  const heroMainValue = document.getElementById("heroMainValue");
  if (heroMainValue) heroMainValue.textContent = String(summary.ongoing_events);
  buildMetricCards("metrics", [
    ["正在交易", summary.ongoing_events, "目前仍在交易窗口內的事件數"],
    ["未來事件", summary.upcoming_events, "尚未進入交易視窗的事件數"],
    ["過去事件", summary.past_events, "已歸檔到歷史頁的事件數"],
    ["價格覆蓋", `${Math.round(summary.coverage_ratio * 100)}%`, "可接到價格資料的目前覆蓋率"],
  ]);
  renderEventList("ongoingList", data.ongoing_events, "目前沒有事件落在正在交易區間。這是正常的，等資料流變成即時後，這一區會開始亮起來。");
  renderEventList("upcomingList", data.upcoming_events, "目前沒有未來事件。現有資料都是歷史樣本。");
}

function initPast() {
  renderEventList("pastList", data.past_events, "目前沒有過去事件。");
  renderMissing();
  wirePastFilters();
}

function initBacktest() {
  const summary = data.summary;
  buildMetricCards("backtestMetrics", [
    ["交易筆數", summary.trades, "目前固定持有期產生的交易數"],
    ["平均報酬", fmtPct(summary.average_trade_return), "現階段可回測樣本的平均報酬"],
    ["勝率", fmtPct(summary.positive_trade_ratio), "正報酬交易比例"],
    ["可算 PE", summary.events_with_implied_pe, "目前有 EPS 與價格可計算 PE 的事件數"],
  ]);
  renderTradeTable();
  buildCoverageBars();
}

if (page === "home") initHome();
if (page === "past") initPast();
if (page === "backtest") initBacktest();
