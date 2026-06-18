const data = window.TOPIC06_DATA;
const page = document.body.dataset.page;
let activeFilter = "all";

function fmtPct(value) {
  if (value === null || value === undefined) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function fmtNum(value) {
  if (value === null || value === undefined) return "N/A";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function fmtInt(value) {
  return Number(value || 0).toLocaleString("zh-TW", { maximumFractionDigits: 0 });
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
  const badges = [
    event.strategy_bucket,
    event.has_compare_context ? "有比較基準" : "缺比較基準",
    event.has_price_file ? "有行情" : "待補行情",
  ];
  if (event.turned_profit_from_loss) badges.push("由虧轉盈");
  if (event.is_selected) badges.push("已納入月投組");

  const tradeMarkup = (event.trades || []).length ? `
    <div class="trade-strip">
      ${event.trades.map((trade) => `
        <div class="trade-pill ${trade.return_pct >= 0 ? "positive" : "negative"}">
          <div class="mini-label">T+${trade.holding_days}</div>
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
            ${badges.map((badge) => `<span class="badge">${badge}</span>`).join("")}
          </div>
        </div>
      </div>
      <div class="event-body">
        <div class="mini-stat">
          <div class="mini-label">EPS</div>
          <div class="mini-value">${fmtNum(event.eps_value)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-label">前期變化</div>
          <div class="mini-value">${fmtPct(event.prev_pct)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-label">YoY 代理</div>
          <div class="mini-value">${fmtPct(event.yoy_pct)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-label">進場價</div>
          <div class="mini-value">${fmtNum(event.entry_price)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-label">最新價</div>
          <div class="mini-value">${fmtNum(event.latest_price)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-label">目前報酬</div>
          <div class="mini-value">${fmtPct(event.marked_return_pct)}</div>
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

function renderGapGrid() {
  const target = document.getElementById("missingGrid");
  if (!target) return;
  const counts = data.main_gap_counts || {};
  const rows = [
    ["缺行情", counts.missing_price_file || 0],
    ["缺比較基準", counts.missing_compare_context || 0],
    ["缺數值", counts.missing_metric_value || 0],
  ];
  target.innerHTML = rows.map(([label, value]) => `
    <div class="missing-chip">${label} ${fmtInt(value)}</div>
  `).join("");
}

function matchesPastFilter(event) {
  if (activeFilter === "all") return true;
  if (activeFilter === "priced") return event.has_price_file;
  if (activeFilter === "missing_price") return !event.has_price_file;
  if (activeFilter === "selected") return event.is_selected;
  return event.strategy_bucket === activeFilter;
}

function wirePastFilters() {
  const buttons = Array.from(document.querySelectorAll(".filter-chip"));
  if (!buttons.length) return;
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      buttons.forEach((node) => node.classList.toggle("is-active", node === button));
      const filtered = data.past_events.filter(matchesPastFilter);
      renderEventList("pastList", filtered, "目前沒有符合條件的過去事件。");
    });
  });
}

function renderTradeTable() {
  const target = document.getElementById("tradeTable");
  if (!target) return;

  const positions = data.marked_positions || [];
  if (!positions.length) {
    target.innerHTML = `<div class="empty-state">目前還沒有可顯示的持倉明細。</div>`;
    return;
  }

  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>股票</div>
      <div>進場日</div>
      <div>進場價</div>
      <div>最新價</div>
      <div>報酬</div>
    </div>
    ${positions.map((row) => `
      <div class="trade-row">
        <div>${row.stock_id} / ${row.company_name}</div>
        <div>${row.entry_date}</div>
        <div>${fmtNum(row.entry_price)}</div>
        <div>${fmtNum(row.latest_price)}</div>
        <div class="${Number(row.marked_return_pct) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(row.marked_return_pct)}</div>
      </div>
    `).join("")}
  `;
}

function buildCoverageBars() {
  const target = document.getElementById("coverageBars");
  if (!target) return;
  const summary = data.local_summary || {};
  const total = summary.main_strategy_events || 0;
  const missingPrices = summary.missing_price_file || 0;
  const missingCompare = summary.missing_compare_context || 0;
  const reviewed = summary.manual_review_events || 0;

  const bars = [
    ["主策略事件", total, summary.selected_events || total || 1],
    ["缺行情", missingPrices, total || 1],
    ["缺比較基準", missingCompare, total || 1],
    ["人工覆核", reviewed, summary.selected_events || 1],
  ];

  target.innerHTML = bars.map(([label, value, base]) => {
    const pct = base ? (Number(value) / Number(base)) * 100 : 0;
    return `
      <div class="bar-card">
        <div class="bar-top"><span>${label}</span><strong>${fmtInt(value)}</strong></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct.toFixed(2)}%"></div></div>
      </div>
    `;
  }).join("");
}

function renderMonthCards() {
  const target = document.getElementById("monthCards");
  if (!target) return;
  const rows = data.month_cards || [];
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有月份配置資料。</div>`;
    return;
  }
  target.innerHTML = rows.map((row) => `
    <article class="metric-card">
      <div class="eyebrow">${row.month}</div>
      <div class="metric-value">${fmtInt(row.selected_events)}</div>
      <div class="metric-note">候選 ${fmtInt(row.candidate_events)} 檔 / 每檔 ${fmtNum(row.allocation_per_event)}</div>
    </article>
  `).join("");
}

function initHome() {
  const summary = data.summary;
  const heroMainValue = document.getElementById("heroMainValue");
  const heroMainNote = document.getElementById("heroMainNote");
  if (heroMainValue) heroMainValue.textContent = String(summary.active_events);
  if (heroMainNote) heroMainNote.textContent = "目前有行情可追蹤的持倉事件";

  buildMetricCards("metrics", [
    ["主策略事件", fmtInt(summary.main_strategy_events), "2026 上半年已挑出的主策略樣本"],
    ["正在交易", fmtInt(summary.active_events), "已選入投組且已有本地行情"],
    ["未來事件", fmtInt(summary.future_events), "事件已挑出，但仍待補行情或補資料"],
    ["人工覆核", fmtInt(summary.manual_review_events), "需要補數據或再判讀的事件"],
  ]);

  renderEventList("ongoingList", data.active_events, "目前首頁沒有可顯示的正在交易事件。");
  renderEventList("upcomingList", data.future_events, "目前沒有新的待補未來事件。");
}

function initPast() {
  renderEventList("pastList", data.past_events, "目前沒有過去事件。");
  renderGapGrid();
  wirePastFilters();
}

function initBacktest() {
  const localBacktest = data.backtest_summary || {};
  const markedSummary = localBacktest.marked_summary || {};
  buildMetricCards("backtestMetrics", [
    ["可見持倉", fmtInt(localBacktest.marked_positions || 0), "目前已能用最新價格標記的持倉數"],
    ["平均報酬", fmtPct(markedSummary.avg_return_pct), "以目前已標記持倉估算"],
    ["勝率", fmtPct(markedSummary.win_rate), "目前已標記持倉中的正報酬比例"],
    ["總損益", fmtNum(markedSummary.total_pnl_amount), "目前持倉累計損益"],
  ]);
  renderTradeTable();
  buildCoverageBars();
  renderMonthCards();
}

if (page === "home") initHome();
if (page === "past") initPast();

function renderParameterTradeTable() {
  const target = document.getElementById("tradeTable");
  if (!target) return;
  const trades = data.best_parameter_trades || [];
  if (!trades.length) {
    target.innerHTML = `<div class="empty-state">目前還沒有可顯示的最佳參數交易明細。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>股票</div>
      <div>進場 / 出場</div>
      <div>價格</div>
      <div>籌碼</div>
      <div>報酬</div>
    </div>
    ${trades.map((row) => `
      <div class="trade-row">
        <div>${row.stock_id} / ${row.company_name}</div>
        <div>${row.entry_date} -> ${row.exit_date}<br><span class="muted">${row.exit_status}</span></div>
        <div>${fmtNum(row.entry_price)} -> ${fmtNum(row.exit_price)}</div>
        <div>外資 ${fmtInt(row.foreign_net_buy_shares)}<br>投信 ${fmtInt(row.investment_trust_net_buy_shares)}<br>法人 ${fmtInt(row.institutional_total_net_buy_shares)}</div>
        <div class="${Number(row.return_pct) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(row.return_pct)}<br>${fmtNum(row.pnl_amount)}</div>
      </div>
    `).join("")}
  `;
}

function initParameterBacktest() {
  const parameterBacktest = data.parameter_backtest_summary || {};
  const best = parameterBacktest.best || {};
  buildMetricCards("backtestMetrics", [
    ["最佳交易數", fmtInt(best.trades || 0), `${fmtInt(best.finalized_trades || 0)} finalized / ${fmtInt(best.as_of_latest_trades || 0)} as-of`],
    ["勝率", fmtPct(best.win_rate), "最佳參數組合中的正報酬比例"],
    ["組合報酬", fmtPct(best.portfolio_return_pct), "以每月 100 萬資金配置估算"],
    ["總損益", fmtNum(best.total_pnl_amount), best.parameter_id || "等待回測結果"],
  ]);
  renderParameterTradeTable();
  buildCoverageBars();
  renderMonthCards();
}

if (page === "backtest") initParameterBacktest();

function renderBatchBestTrades() {
  const target = document.getElementById("tradeTable");
  if (!target) return;
  const trades = data.batch_best_trades || [];
  if (!trades.length) {
    target.innerHTML = `<div class="empty-state">目前沒有批次回測交易明細。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>股票</div>
      <div>買入 / 出場</div>
      <div>報酬</div>
      <div>營收動能</div>
      <div>法人 / 量能</div>
    </div>
    ${trades.map((row) => `
      <div class="trade-row">
        <div>${row.stock_id} / ${row.company_name}<br><span class="muted">${row.revenue_month}</span></div>
        <div>${row.buy_date} -> ${row.exit_date}<br><span class="muted">${row.exit_reason} / ${row.exit_status}</span></div>
        <div class="${Number(row.return_pct) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(row.return_pct)}<br>${fmtNum(row.pnl_amount)}</div>
        <div>MoM ${fmtPct(row.mom_pct)}<br>YoY ${fmtPct(row.yoy_pct)}</div>
        <div>法人 ${fmtInt(row.institutional_total_net_buy_shares)}<br>5日均量 ${fmtInt(row.avg_volume_5d)}<br>量比 ${fmtNum(row.previous_volume_ratio_20d)}</div>
      </div>
    `).join("")}
  `;
}

function renderParameterRanking() {
  const target = document.getElementById("parameterRankingTable");
  if (!target) return;
  const rows = data.batch_parameter_rankings || [];
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有其他參數組合排行。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row ranking-row trade-head">
      <div>排行 / 參數</div>
      <div>交易</div>
      <div>勝率</div>
      <div>報酬</div>
      <div>損益</div>
    </div>
    ${rows.map((row, index) => `
      <div class="trade-row ranking-row">
        <div>#${index + 1}<br><span class="muted">${row.parameter_id}</span></div>
        <div>${fmtInt(row.trades)} 筆<br>${fmtInt(row.full_trade_months)} 個月份滿 5 檔</div>
        <div>${fmtPct(row.win_rate)}</div>
        <div class="${Number(row.portfolio_return_pct) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(row.portfolio_return_pct)}</div>
        <div>${fmtNum(row.total_pnl_amount)}</div>
      </div>
    `).join("")}
  `;
}

function initBatchBacktest() {
  const summary = data.batch_backtest_summary || {};
  const best = summary.best || {};
  const annualized = best.portfolio_return_pct == null
    ? null
    : Math.pow(1 + Number(best.portfolio_return_pct), 12 / 5) - 1;
  buildMetricCards("backtestMetrics", [
    ["每月配置", `${fmtInt(summary.target_positions_per_month || 5)} 檔`, `${fmtInt(best.trades || 0)} 筆交易 / ${fmtInt(best.full_trade_months || 0)} 個月份滿檔`],
    ["勝率", fmtPct(best.win_rate), "批次參數最佳組合"],
    ["總報酬", fmtPct(best.portfolio_return_pct), `年化約 ${fmtPct(annualized)}`],
    ["總損益", fmtNum(best.total_pnl_amount), best.parameter_id || "等待回測結果"],
  ]);
  renderBatchBestTrades();
  renderParameterRanking();
  buildCoverageBars();
  renderMonthCards();
}

if (page === "backtest") initBatchBacktest();

function renderStrategySwitcher() {
  const target = document.getElementById("strategySwitcher");
  if (!target) return;
  const strategies = data.strategy_cards || [];
  if (!strategies.length) {
    target.innerHTML = `<div class="empty-state">暫時沒有策略資料。</div>`;
    return;
  }
  target.innerHTML = strategies.map((strategy, index) => `
    <button class="strategy-pill ${index === 0 ? "is-active" : ""}" data-strategy-index="${index}">
      <span class="strategy-pill-name">${strategy.name}</span>
      <span class="strategy-pill-label">${strategy.label}</span>
    </button>
  `).join("");
}

function renderTopFive(strategyIndex = 0) {
  const target = document.getElementById("topFiveGrid");
  if (!target) return;
  const strategy = (data.strategy_cards || [])[strategyIndex] || (data.strategy_cards || [])[0];
  const sourceRows = strategyIndex === 0 ? (data.batch_best_trades || []) : (data.best_parameter_trades || []);
  const rows = sourceRows.slice(0, 5);
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有可顯示的前五名預測。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="strategy-summary">
      <div class="eyebrow">${strategy.name}</div>
      <div class="strategy-summary-title">${strategy.label}</div>
      <div class="strategy-summary-note">目前顯示預測前五名，依既有策略回測結果排序。</div>
    </div>
    <div class="strategy-top-five">
      ${rows.map((row, index) => `
        <article class="top-five-card">
          <div class="top-five-rank">#${index + 1}</div>
          <div class="top-five-name">${row.company_name || row.stock_id}</div>
          <div class="top-five-meta">${row.stock_id || ""} ${row.revenue_month ? `· ${row.revenue_month}` : ""}</div>
          <div class="top-five-score ${Number(row.return_pct || row.portfolio_return_pct || 0) >= 0 ? "positive-text" : "negative-text"}">
            ${fmtPct(row.return_pct ?? row.portfolio_return_pct)}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function initHomeDashboard() {
  renderStrategySwitcher();
  renderTopFive(0);
  const switcher = document.getElementById("strategySwitcher");
  if (switcher) {
    switcher.addEventListener("click", (event) => {
      const button = event.target.closest(".strategy-pill");
      if (!button) return;
      const index = Number(button.dataset.strategyIndex || 0);
      switcher.querySelectorAll(".strategy-pill").forEach((node) => node.classList.remove("is-active"));
      button.classList.add("is-active");
      renderTopFive(index);
    });
  }
}

if (page === "home") initHomeDashboard();
