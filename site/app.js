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

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function renderMetrics() {
  const best = data.winner_factor_best || {};
  const summary = data.summary || {};
  const target = document.getElementById("metrics");
  if (!target) return;
  target.innerHTML = [
    ["目前持股", fmtInt((data.june_holdings || []).length), "本月實際持倉"],
    ["最佳勝率", fmtPct(best.win_rate), "暴力回測最佳組合"],
    ["最佳平均報酬", fmtPct(best.avg_return_pct), "單組平均報酬率"],
    ["策略數", fmtInt((data.winner_factor_results || []).length), "前 50 策略清單來源"],
  ].map(([label, value, note]) => `
    <article class="metric-card">
      <div class="eyebrow">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-note">${note}</div>
    </article>
  `).join("");
}

function renderHoldings() {
  const target = document.getElementById("currentHoldings");
  if (!target) return;
  const rows = (data.june_holdings || []).slice(0, 5);
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有本月持股。</div>`;
    return;
  }
  target.innerHTML = rows.map((row, index) => `
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

function renderBestStrategy() {
  const target = document.getElementById("bestStrategyCard");
  if (!target) return;
  const best = data.winner_factor_best || {};
  if (!best.combo) {
    target.innerHTML = `<div class="empty-state">目前沒有最佳策略。</div>`;
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
    <div class="strategy-note">目前保留的最佳暴力回測結果。</div>
  `;
}

function renderStrategyIndex() {
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
      <div class="metric-note">回測條件索引。</div>
    </article>
  `).join("");
}

function renderStrategyHistory() {
  const target = document.getElementById("strategyHistoryTable");
  if (!target) return;
  const rows = (data.winner_factor_results || []).slice(0, 50);
  if (!rows.length) {
    target.innerHTML = `<div class="empty-state">目前沒有策略歷史紀錄。</div>`;
    return;
  }
  target.innerHTML = `
    <div class="trade-row trade-head">
      <div>策略</div>
      <div>勝率</div>
      <div>平均報酬</div>
      <div>月均報酬</div>
      <div>交易數</div>
    </div>
    ${rows.map((row) => `
      <div class="trade-row">
        <div>${row.combo}</div>
        <div>${fmtPct(row.win_rate)}</div>
        <div>${fmtPct(row.avg_return_pct)}</div>
        <div>${fmtPct(row.monthly_avg_return_pct)}</div>
        <div>${fmtInt(row.trades)}</div>
      </div>
    `).join("")}
  `;
}

function initHome() {
  const best = data.winner_factor_best || {};
  setText("heroMainValue", best.combo ? `${fmtPct(best.win_rate)} / ${fmtPct(best.avg_return_pct)}` : "--");
  setText("heroMainNote", "只保留新的戰情室內容");
  renderMetrics();
  renderHoldings();
  renderBestStrategy();
}

function initPast() {
  renderStrategyIndex();
  renderStrategyHistory();
}

if (page === "home") initHome();
if (page === "past") initPast();
