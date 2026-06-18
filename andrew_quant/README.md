# finlab 還原版（自結 EPS 催化策略）

把原專案策略（root 的 `extract_events.py` / `build_valuation_snapshot.py` / `build_trades.py`）
**邏輯逐字沿用、資料源換成 finlab** 的還原。未做任何優化。產出 **finlab 原生回測 report**。

- 事件文本：finlab `important_info_announcement`（重大訊息全文，2006–2026，1.23M 列）
- 個股價格：finlab `price:收盤價`（還原權值）

## 檔案

單一檔 **`self_assessed_eps_strategy.py`** 從頭到尾：
事件萃取(關鍵字/分級/去重) → 進場(盤後≥13:30順延) → T+5/10/20 出場 → 報酬 →
攤成等權重重疊投組跑 `sim()` → 輸出 **finlab 原生 report**（年度報酬熱力圖/權益曲線/回撤）到 `reports/`。

選股/事件偵測條件區塊：關鍵字清單、強候選 `is_strong_candidate`、分級 `classify_event_type`、
去重 `deduplicate_events`、進出場 `build_snapshots_and_trades`、報表 `build_native_reports`。

## 跑法
```bash
cd <repo>/andrew_quant
# 完整：事件→交易→4 份原生報表
uv run --with finlab --with pyarrow --with plotly python self_assessed_eps_strategy.py
# 只重產報表（讀現有 data/trades.csv）
uv run --with finlab --with pyarrow --with plotly python self_assessed_eps_strategy.py --report-only
```

## 產出
- `data/` — **整包 .gitignore**（本機產物、可再生）：跑 `self_assessed_eps_strategy.py` 即重生
- `reports/`（**有進版控**）— 4 份 finlab 原生互動 report HTML：
  `自結EPS_T20_raw` / `T20_cost` / `T10_cost` / `T5_cost`（瀏覽器開）

⚠️ 權益曲線是等權重重疊投組：早期事件少→集中度高、小型股再平衡有波動收割假象，總報酬被膨脹，
**非真 edge**。真實力看交易層級（淨報酬≤0、勝率45%）——細節見 gquant `deliverables/topic06_自結EPS催化_finlab還原/策略說明.md`。

## 結論
全市場 8,808 事件 20 年實測：自結 EPS 公告**無可靠正向催化**，扣成本後淨報酬 ≤ 0。誠實的 null result。
