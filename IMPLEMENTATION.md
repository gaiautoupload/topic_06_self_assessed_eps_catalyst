# Topic 06 Implementation Plan

## 1. Module Split

建議把流程拆成四個模組：

1. `extract_events.py`
   - 從事件資料中找出自結 EPS 候選。
   - 產出標準化事件表。

2. `build_valuation_snapshot.py`
   - 接股價資料與 EPS。
   - 計算公告日附近的價格與 implied PE。

3. `build_trades.py`
   - 套用進出場規則。
   - 產出交易紀錄與報酬。

4. `report.py`
   - 彙整摘要指標。
   - 輸出靜態頁面所需的表格與圖表資料。

## 2. Data Flow

`material_events.jsonl` / `mops_history`
-> `events.parquet`
-> `valuation_snapshot.parquet`
-> `trades.parquet`
-> report / static site

## 3. Suggested Function Boundaries

### `extract_events.py`

- `load_candidates(...)`
- `normalize_event(...)`
- `classify_event_type(...)`
- `extract_eps_value(...)`
- `deduplicate_events(...)`
- `write_events(...)`

### `build_valuation_snapshot.py`

- `load_prices(stock_id)`
- `find_entry_date(announcement_date, announcement_time)`
- `get_close_on_or_after(date)`
- `calc_implied_pe(close, eps_value)`
- `build_snapshot_row(event, price_row)`

### `build_trades.py`

- `determine_entry_date(event)`
- `determine_exit_date(entry_date, holding_days)`
- `calc_trade_return(entry_price, exit_price)`
- `build_trade_row(event, snapshot)`

## 4. First MVP Scope

先只做以下最小版本：

- 資料來源只用 `processed/material_events.jsonl`
- 事件類型只保留 `self_assessed_eps`
- 持有期只做 `T+5`
- 不先加停利停損
- 先產生 CSV/Parquet，再做靜態頁

