const data = window.TOPIC06_DASHBOARD || {};
const page = document.body.dataset.page || "home";

const familyLabels = {
  all: "全部策略",
  global: "全局策略",
  breakout_growth: "創高成長",
  undervalued_growth: "低估成長",
  second_breakout: "二次創高",
};

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmtPct(value, digits = 1) {
  const n = toNumber(value);
  if (n === null) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(value, digits = 0) {
  const n = toNumber(value);
  if (n === null) return "—";
  return n.toLocaleString("zh-TW", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtMoney(value) {
  const n = toNumber(value);
  if (n === null) return "—";
  return n.toLocaleString("zh-TW", { maximumFractionDigits: 0 });
}

function fmtText(value) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setHtml(id, html) {
  const node = document.getElementById(id);
  if (node) node.innerHTML = html;
}

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function bestStrategyCard() {
  const cards = data.strategy_cards || [];
  if (!cards.length) return null;
  return [...cards].sort((a, b) => (toNumber(b.objective) || 0) - (toNumber(a.objective) || 0))[0];
}

function renderHero() {
  const best = bestStrategyCard();
  const overview = data.overview || {};
  const currentHoldings = data.current_holdings || [];
  const tradeMonths = data.trade_months || [];
  const latestMonth = (data.monthly_portfolio || [])[data.monthly_portfolio.length - 1] || {};

  setText(
    "heroMainValue",
    best ? `${fmtPct(best.win_rate)} / ${fmtPct(best.avg_return_pct)}` : "—",
  );
  setText(
    "heroMainNote",
    best ? `最佳家族：${best.label} · ${fmtText(best.best_combo)}` : "尚無策略資料",
  );

  const heroChips = [
    ["月資金", fmtMoney(overview.month_budget || 1_000_000), `每月預設 ${fmtNum(overview.target_positions || 5)} 檔`],
    ["本月持股", fmtNum(currentHoldings.length), latestMonth.month ? `${latestMonth.month}` : "最新月份"],
    ["歷史月數", fmtNum(tradeMonths.length), "批次回測月份"],
  ];

  setHtml(
    "heroChips",
    heroChips
      .map(
        ([label, value, note]) => `
          <span class="chip" title="${escapeHtml(note)}">${escapeHtml(label)} · ${escapeHtml(value)}</span>
        `,
      )
      .join(""),
  );

  setHtml(
    "heroMiniStats",
    [
      {
        label: "最佳批次回測",
        value: `${fmtPct(overview.batch_best?.win_rate)} / ${fmtPct(overview.batch_best?.portfolio_return_pct)}`,
      },
      {
        label: "最佳因子組合",
        value: `${fmtPct(overview.winner_best?.win_rate)} / ${fmtPct(overview.winner_best?.avg_return_pct)}`,
      },
      {
        label: "最佳策略家族",
        value: `${fmtPct(best?.win_rate)} / ${fmtPct(best?.avg_return_pct)}`,
      },
    ]
      .map(
        (item) => `
          <div class="mini-stat">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
          </div>
        `,
      )
      .join(""),
  );
}

function renderOverviewKpis() {
  const overview = data.overview || {};
  const cards = [
    {
      label: "批次回測最佳",
      value: `${fmtPct(overview.batch_best?.win_rate)} / ${fmtPct(overview.batch_best?.portfolio_return_pct)}`,
      note: `參數 ${fmtText(overview.batch_best?.parameter_id)}`,
    },
    {
      label: "EPS 參數最佳",
      value: `${fmtPct(overview.parameter_best?.win_rate)} / ${fmtPct(overview.parameter_best?.portfolio_return_pct)}`,
      note: `${fmtText(overview.parameter_best?.parameter_id)}`,
    },
    {
      label: "因子挖掘最佳",
      value: `${fmtPct(overview.winner_best?.win_rate)} / ${fmtPct(overview.winner_best?.avg_return_pct)}`,
      note: `${fmtText(overview.winner_best?.combo)}`,
    },
    {
      label: "全局策略最佳",
      value: `${fmtPct(overview.global_best?.win_rate)} / ${fmtPct(overview.global_best?.avg_return_pct)}`,
      note: `${fmtNum(overview.global_best?.target_positions_per_month)} 檔 / 月`,
    },
  ];

  setHtml(
    "overviewKpis",
    cards
      .map(
        (card, index) => `
          <article class="metric-card fade-in" style="animation-delay:${index * 40}ms">
            <div class="metric-label">${escapeHtml(card.label)}</div>
            <div class="metric-value">${escapeHtml(card.value)}</div>
            <div class="metric-note">${escapeHtml(card.note)}</div>
          </article>
        `,
      )
      .join(""),
  );
}

function renderStrategyCards() {
  const cards = data.strategy_cards || [];
  if (!cards.length) {
    setHtml("strategyCards", `<div class="empty-state">沒有策略資料。</div>`);
    return;
  }

  setHtml(
    "strategyCards",
    cards
      .map((card, index) => {
        const objective = toNumber(card.objective) || 0;
        const objectiveWidth = Math.max(0, Math.min(100, objective * 100));
        return `
          <article class="strategy-card fade-in" style="animation-delay:${index * 50}ms">
            <div class="strategy-badge">${escapeHtml(card.label)}</div>
            <div class="strategy-card__title">${escapeHtml(card.best_combo || "—")}</div>
            <div class="strategy-card__combo">${escapeHtml(card.months ? `${fmtNum(card.months)} 個月 / ${fmtNum(card.trades)} 筆` : `${fmtNum(card.trades)} 筆`)}</div>
            <div class="stat-grid">
              <div class="stat-box">
                <span>勝率</span>
                <strong>${fmtPct(card.win_rate)}</strong>
              </div>
              <div class="stat-box">
                <span>平均報酬</span>
                <strong>${fmtPct(card.avg_return_pct)}</strong>
              </div>
              <div class="stat-box">
                <span>月均報酬</span>
                <strong>${fmtPct(card.monthly_avg_return_pct)}</strong>
              </div>
              <div class="stat-box">
                <span>Objective</span>
                <strong>${fmtNum(card.objective, 3)}</strong>
              </div>
            </div>
            <div class="meter" aria-hidden="true"><span style="width:${objectiveWidth}%"></span></div>
          </article>
        `;
      })
      .join(""),
  );
}

function renderCurrentHoldings() {
  const holdings = data.current_holdings || [];
  const latestMonth = (data.monthly_portfolio || [])[data.monthly_portfolio.length - 1] || {};
  setText(
    "currentHoldingsMeta",
    latestMonth.month
      ? `${latestMonth.month} · ${fmtNum(holdings.length)} 檔 · 總配置 ${fmtMoney(latestMonth.total_allocation || latestMonth.allocated_capital || 0)}`
      : "沒有持股資料",
  );

  if (!holdings.length) {
    setHtml("currentHoldings", `<div class="empty-state">目前沒有可顯示的持股。</div>`);
    return;
  }

  setHtml(
    "currentHoldings",
    holdings
      .map((row, index) => `
        <article class="holding-card fade-in" style="animation-delay:${index * 40}ms">
          <div class="holding-card__top">
            <div class="holding-rank">#${escapeHtml(String(row.selected_rank || index + 1))}</div>
            <div style="flex:1">
              <div class="holding-card__title">${escapeHtml(row.company_name || row.stock_id || "—")}</div>
              <div class="holding-card__meta">${escapeHtml(row.stock_id || "—")} · ${escapeHtml(fmtText(row.announcement_date))}</div>
            </div>
            <div class="holding-card__value">${fmtMoney(row.allocation_amount)}</div>
          </div>
          <div class="holding-card__meta">${escapeHtml(row.title || "—")}</div>
          <div class="holding-card__stats stat-grid">
            <div class="stat-box">
              <span>策略桶</span>
              <strong>${escapeHtml(row.strategy_bucket || "—")}</strong>
            </div>
            <div class="stat-box">
              <span>EPS / 獲利</span>
              <strong>${fmtNum(row.eps_value, 2)} / ${fmtMoney(row.profit_value)}</strong>
            </div>
            <div class="stat-box">
              <span>公告時間</span>
              <strong>${escapeHtml(row.announcement_time || "—")}</strong>
            </div>
            <div class="stat-box">
              <span>來源</span>
              <strong>${escapeHtml(row.source || "—")}</strong>
            </div>
          </div>
        </article>
      `)
      .join(""),
  );
}

function renderBacktestSpotlight() {
  const summaries = data.backtest_summaries || {};
  const batch = summaries.batch?.best || {};
  const factor = summaries.winner_factor?.best_combo || summaries.winner_factor?.best || {};

  setHtml(
    "batchBacktestCard",
    `
      <div class="card-title">批次回測最佳條件</div>
      <div class="card-lead">${escapeHtml(fmtText(batch.parameter_id))}</div>
      <div class="spotlight-grid stat-grid">
        <div class="stat-box"><span>勝率</span><strong>${fmtPct(batch.win_rate)}</strong></div>
        <div class="stat-box"><span>平均報酬</span><strong>${fmtPct(batch.portfolio_return_pct)}</strong></div>
        <div class="stat-box"><span>交易數</span><strong>${fmtNum(batch.trades)}</strong></div>
        <div class="stat-box"><span>月數</span><strong>${fmtNum(batch.full_trade_months || batch.covered_trade_months)}</strong></div>
      </div>
      <div class="inline-note">停損 ${fmtPct(batch.stop_loss)} · 停利 ${batch.take_profit == null ? "無" : fmtPct(batch.take_profit)} · 出場 ${escapeHtml(fmtText(batch.exit_rule))}</div>
    `,
  );

  setHtml(
    "factorBacktestCard",
    `
      <div class="card-title">因子挖掘最佳組合</div>
      <div class="card-lead">${escapeHtml(fmtText(factor.combo))}</div>
      <div class="spotlight-grid stat-grid">
        <div class="stat-box"><span>勝率</span><strong>${fmtPct(factor.win_rate)}</strong></div>
        <div class="stat-box"><span>平均報酬</span><strong>${fmtPct(factor.avg_return_pct)}</strong></div>
        <div class="stat-box"><span>月均報酬</span><strong>${fmtPct(factor.monthly_avg_return_pct)}</strong></div>
        <div class="stat-box"><span>交易數</span><strong>${fmtNum(factor.trades)}</strong></div>
      </div>
      <div class="inline-note">信號 ${fmtNum(summaries.winner_factor?.signal_rows)} · 交易 ${fmtNum(summaries.winner_factor?.trade_rows)} · 達標 ${escapeHtml(String(factor.hit_goal ?? false))}</div>
    `,
  );
}

function renderLeaderboardChips(activeKey = "all") {
  const chips = Object.entries(familyLabels);
  setHtml(
    "strategyFamilyChips",
    chips
      .map(
        ([key, label]) => `
          <button class="leaderboard-filter ${key === activeKey ? "is-active" : ""}" data-family="${escapeHtml(key)}" type="button">${escapeHtml(label)}</button>
        `,
      )
      .join(""),
  );

  document.querySelectorAll("[data-family]").forEach((node) => {
    node.addEventListener("click", () => renderStrategyLeaderboard(node.dataset.family || "all"));
  });
}

function renderStrategyLeaderboard(family = "all") {
  const boards = data.strategy_leaderboards || {};
  const rows =
    family === "all"
      ? boards.raw_all || boards.all || []
      : family === "global"
        ? boards.raw_global || boards.global || []
        : boards.raw_families?.[family] || boards.families?.[family] || [];

  const target = document.getElementById("strategyLeaderboard");
  if (!target) return;

  renderLeaderboardChips(family);

  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">沒有策略排行榜資料。</div>`;
    return;
  }

  target.innerHTML = `
    <div class="leaderboard-row leaderboard-row--head">
      <div>#</div>
      <div>策略</div>
      <div>交易數 / 月數</div>
      <div>勝率</div>
      <div>平均報酬</div>
      <div>月均報酬</div>
      <div>Objective</div>
    </div>
    ${rows
      .map(
        (row, index) => `
          <article class="leaderboard-row fade-in" style="animation-delay:${Math.min(index, 20) * 20}ms">
            <div class="leaderboard-rank">${index + 1}</div>
            <div>
              <div class="leaderboard-row__title">${escapeHtml(row.family || familyLabels[family] || "—")}</div>
              <div class="leaderboard-row__meta">${
                escapeHtml(
                  row.combo || row.best_combo || [
                    `T${fmtNum(row.target_positions_per_month)}`,
                    `min${fmtNum(row.min_trades_per_month)}`,
                    `chip ${fmtNum(row.chip_w, 1)}`,
                    `tech ${fmtNum(row.tech_w, 1)}`,
                    `fund ${fmtNum(row.fundamental_w, 1)}`,
                    `val ${fmtNum(row.value_w, 1)}`,
                    `thr ${fmtNum(row.min_score, 1)}`,
                  ].join(" · "),
                )
              }</div>
            </div>
            <div class="leaderboard-row__meta">${fmtNum(row.trades)} / ${fmtNum(row.months)}</div>
            <div class="leaderboard-row__meta">${fmtPct(row.win_rate)}</div>
            <div class="leaderboard-row__meta">${fmtPct(row.avg_return_pct)}</div>
            <div class="leaderboard-row__meta">${fmtPct(row.monthly_avg_return_pct)}</div>
            <div class="leaderboard-row__objective">${fmtNum(row.objective, 3)}</div>
          </article>
        `,
      )
      .join("")}
  `;
}

function renderPortfolioMonths() {
  const months = data.monthly_portfolio || [];
  const target = document.getElementById("portfolioMonthsGrid");
  if (!target) return;

  if (!months.length) {
    target.innerHTML = `<div class="empty-state">沒有月度配置資料。</div>`;
    return;
  }

  const latestMonth = months[months.length - 1]?.month;
  target.innerHTML = months
    .map((month) => {
      const open = month.month === latestMonth;
      const entries = month.entries || [];
      return `
        <details class="month-card fade-in" ${open ? "open" : ""}>
          <summary>
            <div class="month-card__summary">
              <div style="flex:1">
                <div class="month-pill">${escapeHtml(month.month)}</div>
                <div class="month-card__title">候選 ${fmtNum(month.candidate_events)} 檔 · 選出 ${fmtNum(month.selected_events)} 檔</div>
                <div class="month-card__meta">${escapeHtml(fmtText(month.fill_rule))}</div>
              </div>
              <div class="holding-card__value">${fmtMoney(month.allocated_capital || month.total_allocation)}</div>
            </div>
          </summary>
          <div class="month-card__body">
            <div class="month-card__stats">
              <div class="stat-box">
                <span>單檔配置</span>
                <strong>${fmtMoney(month.allocation_per_event)}</strong>
              </div>
              <div class="stat-box">
                <span>總配置</span>
                <strong>${fmtMoney(month.total_allocation || month.allocated_capital)}</strong>
              </div>
              <div class="stat-box">
                <span>選股數</span>
                <strong>${fmtNum(month.selected_events)}</strong>
              </div>
              <div class="stat-box">
                <span>候選數</span>
                <strong>${fmtNum(month.candidate_events)}</strong>
              </div>
            </div>
            <div class="month-entry-list">
              ${entries
                .map(
                  (row, index) => `
                    <article class="month-entry-card">
                      <div class="month-entry-card__top">
                        <div class="holding-rank">${escapeHtml(String(row.selected_rank || index + 1))}</div>
                        <div style="flex:1">
                          <div class="month-entry-card__title">${escapeHtml(row.company_name || row.stock_id || "—")}</div>
                          <div class="month-entry-card__meta">${escapeHtml(row.stock_id || "—")} · ${escapeHtml(fmtText(row.announcement_date))} · ${escapeHtml(fmtText(row.announcement_time))}</div>
                        </div>
                        <div class="holding-card__value">${fmtMoney(row.allocation_amount)}</div>
                      </div>
                      <div class="month-entry-card__meta">${escapeHtml(row.title || "—")}</div>
                      <div class="trade-card__chips">
                        <span class="trade-pill">${escapeHtml(fmtText(row.strategy_bucket))}</span>
                        <span class="trade-pill">EPS ${fmtNum(row.eps_value, 2)}</span>
                        <span class="trade-pill">獲利 ${fmtMoney(row.profit_value)}</span>
                      </div>
                    </article>
                  `,
                )
                .join("")}
            </div>
          </div>
        </details>
      `;
    })
    .join("");
}

function renderTradeMonths() {
  const months = data.trade_months || [];
  const target = document.getElementById("tradeMonthsGrid");
  if (!target) return;

  const latest = months[0];
  setText(
    "historyMainValue",
    latest ? `${latest.month} / ${fmtNum(latest.trade_count)} 筆` : "—",
  );
  setText(
    "historyMainNote",
    latest ? "往下可以看每月買進與賣出明細" : "沒有回測明細",
  );

  if (!months.length) {
    target.innerHTML = `<div class="empty-state">沒有歷史買賣資料。</div>`;
    return;
  }

  target.innerHTML = months
    .map((month, monthIndex) => {
      const open = monthIndex === 0;
      return `
        <details class="month-card fade-in" ${open ? "open" : ""}>
          <summary>
            <div class="month-card__summary">
              <div style="flex:1">
                <div class="month-pill">${escapeHtml(month.month)}</div>
                <div class="month-card__title">${fmtNum(month.trade_count)} 筆 · 勝率 ${fmtPct(month.win_rate)} · 平均 ${fmtPct(month.avg_return_pct)}</div>
                <div class="month-card__meta">總損益 ${fmtMoney(month.total_pnl_amount)}</div>
              </div>
              <div class="holding-card__value ${month.avg_return_pct >= 0 ? "positive-text" : "negative-text"}">${fmtPct(month.avg_return_pct)}</div>
            </div>
          </summary>
          <div class="month-card__body">
            <div class="month-card__stats">
              <div class="stat-box">
                <span>交易數</span>
                <strong>${fmtNum(month.trade_count)}</strong>
              </div>
              <div class="stat-box">
                <span>勝率</span>
                <strong>${fmtPct(month.win_rate)}</strong>
              </div>
              <div class="stat-box">
                <span>平均報酬</span>
                <strong>${fmtPct(month.avg_return_pct)}</strong>
              </div>
              <div class="stat-box">
                <span>總損益</span>
                <strong>${fmtMoney(month.total_pnl_amount)}</strong>
              </div>
            </div>
            <div class="month-entry-list">
              ${month.trades
                .map(
                  (trade, tradeIndex) => `
                    <article class="trade-card">
                      <div class="trade-card__top">
                        <div class="trade-rank">${tradeIndex + 1}</div>
                        <div style="flex:1">
                          <div class="trade-card__title">${escapeHtml(trade.company_name || trade.stock_id || "—")}</div>
                          <div class="trade-card__meta">${escapeHtml(trade.stock_id || "—")} · ${escapeHtml(fmtText(trade.parameter_id || trade.strategy_bucket))}</div>
                        </div>
                        <div class="trade-card__return ${Number(trade.return_pct || 0) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(trade.return_pct)}</div>
                      </div>
                      <div class="trade-card__meta">${escapeHtml(trade.title || "—")}</div>
                      <div class="trade-card__dates trade-card__meta">
                        <span>買進 ${escapeHtml(fmtText(trade.buy_date))} @ ${fmtNum(trade.buy_price, 2)}</span>
                        <span>賣出 ${escapeHtml(fmtText(trade.exit_date))} @ ${fmtNum(trade.exit_price, 2)}</span>
                      </div>
                      <div class="trade-card__chips">
                        <span class="trade-pill">損益 ${fmtMoney(trade.pnl_amount)}</span>
                        <span class="trade-pill">部位 ${fmtMoney(trade.allocation_amount)}</span>
                        <span class="trade-pill">持有 ${fmtNum(trade.holding_days)} 日</span>
                        <span class="trade-pill">${escapeHtml(fmtText(trade.exit_reason))}</span>
                      </div>
                    </article>
                  `,
                )
                .join("")}
            </div>
          </div>
        </details>
      `;
    })
    .join("");
}

function initHome() {
  renderHero();
  renderOverviewKpis();
  renderStrategyCards();
  renderCurrentHoldings();
  renderBacktestSpotlight();
}

function initPast() {
  renderStrategyLeaderboard("all");
  renderPortfolioMonths();
  renderTradeMonths();
}

if (page === "home") {
  initHome();
}

if (page === "past") {
  initPast();
}
