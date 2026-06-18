const data = window.TOPIC06_DATA;
const page = document.body.dataset.page;

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

function renderCurrentHoldings() {
  const target = document.getElementById("currentHoldings");
  if (!target) return;
  const holdings = data.june_holdings || [];
  if (!holdings.length) {
    target.innerHTML = `<div class="empty-state">目前沒有本月持股。</div>`;
    return;
  }
  target.innerHTML = holdings.slice(0, 5).map((row, index) => `
    <article class="holding-card">
      <div class="holding-rank">#${index + 1}</div>
      <div>
        <div class="holding-name">${row.company_name || row.stock_id}</div>
        <div class="holding-meta">${row.stock_id} · ${row.buy_date}</div>
      </div>
      <div class="holding-return ${Number(row.return_pct || 0) >= 0 ? "positive-text" : "negative-text"}">${fmtPct(row.return_pct)}</div>
    </article>
  `).join("");
}

function renderBestStrategyCard() {
  const target = document.getElementById("bestStrategyCard");
  if (!target) return;
  const best = data.winner_factor_best || {};
  if (!best.combo) {
    target.innerHTML = `<div class="empty-state">目前沒有最佳策略資料。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="strategy-title">${best.combo}</div>
    <div class="strategy-statline">
      <div><span>勝率</span><strong>${fmtPct(best.win_rate)}</strong></div>
      <div><span>平均報酬</span><strong>${fmtPct(best.avg_return_pct)}</strong></div>
      <div><span>月均報酬</span><strong>${fmtPct(best.monthly_avg_return_pct)}</strong></div>
      <div><span>交易數</span><strong>${fmtInt(best.trades)}</strong></div>
    </div>
    <div class="strategy-note">這是目前保留下來的最佳暴力回測組合。</div>
  `;
}

function initHome() {
  const summary = data.summary || {};
  const heroMainValue = document.getElementById("heroMainValue");
  const heroMainNote = document.getElementById("heroMainNote");
  if (heroMainValue) heroMainValue.textContent = bestSummaryText();
  if (heroMainNote) heroMainNote.textContent = "只保留持倉與最佳策略";

  buildMetricCards("metrics", [
    ["目前持股", fmtInt(summary.active_events), "本月實際進場標的"],
    ["最佳策略勝率", fmtPct((data.winner_factor_best || {}).win_rate), "暴力回測最佳值"],
    ["最佳策略報酬", fmtPct((data.winner_factor_best || {}).avg_return_pct), "平均報酬率"],
    ["策略組數", fmtInt((data.winner_factor_results || []).length || 0), "可回看歷史策略"],
  ]);

  renderCurrentHoldings();
  renderBestStrategyCard();
}

function bestSummaryText() {
  const best = data.winner_factor_best || {};
  if (!best.combo) return "--";
  return `${fmtPct(best.win_rate)} / ${fmtPct(best.avg_return_pct)}`;
}

function renderStrategyPalette() {
  const target = document.getElementById("strategyPalette");
  if (!target) return;
  const cards = [
    ["暴力最佳", "trust_buy_positive + prev_vol_ratio_gt_1_5 + breakout_20d"],
    ["分數制", "籌碼 + 技術 + 基本面加權"],
    ["月營收篩選", "月增 > 0 且 年增 > 0"],
  ];
  target.innerHTML = cards.map(([title, note]) => `
    <article class="metric-card">
      <div class="eyebrow">${title}</div>
      <div class="metric-value" style="font-size:1.1rem">${note}</div>
      <div class="metric-note">策略條件索引。</div>
    </article>
  `).join("");
}

function renderStrategyHistory() {
  const target = document.getElementById("strategyHistoryTable");
  if (!target) return;
  const rows = data.winner_factor_results || [];
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有策略歷史紀錄。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>策略</div>
      <div>交易數</div>
      <div>勝率</div>
      <div>平均報酬</div>
      <div>月均報酬</div>
    </div>
    ${rows.slice(0, 30).map((row) => `
      <div class="trade-row">
        <div>${row.combo}</div>
        <div>${fmtInt(row.trades)}</div>
        <div>${fmtPct(row.win_rate)}</div>
        <div>${fmtPct(row.avg_return_pct)}</div>
        <div>${fmtPct(row.monthly_avg_return_pct)}</div>
      </div>
    `).join("")}
  `;
}

function initPast() {
  renderStrategyPalette();
  renderStrategyHistory();
}

if (page === "home") initHome();
if (page === "past") initPast();
