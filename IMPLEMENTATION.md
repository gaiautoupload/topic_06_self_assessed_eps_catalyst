# Topic 06 Implementation Plan

## 1. Current Modules

現有流程：

1. `extract_events.py`
   - 找出自結 EPS / 自結獲利候選事件

2. `build_valuation_snapshot.py`
   - 將事件對到價格資料
   - 產出事件日的價格快照

3. `build_trades.py`
   - 建立固定持有期交易

4. `generate_site_data.py`
   - 將輸出整理成前端資料

5. `sync_site_to_docs.py`
   - 將 `site/` 同步到 `docs/`

## 2. New Comparison Layer

Topic 06 下一個必要模組不是先加更多前端，而是補「比較層」。

建議新增：

`build_event_comparisons.py`

用途：
- 對每個事件補本期數值
- 對照上月、上一季、去年同期
- 算出改善幅度
- 標記是否由虧轉盈 / 由盈轉虧

## 3. New Output Fields

`events.csv` / `events.parquet` 後續要補：

- `metric_current`
- `metric_prev_month`
- `metric_prev_quarter`
- `metric_yoy_base`
- `mom_delta`
- `qoq_delta`
- `yoy_delta`
- `mom_pct`
- `qoq_pct`
- `yoy_pct`
- `turned_profit_from_loss`
- `turned_loss_from_profit`
- `comparison_source`
- `strategy_bucket`

## 4. Strategy Buckets

### Bucket A

`topic_06_eps_catalyst`

條件：
- 自結 EPS 或自結獲利存在
- 與可比基準相比為改善
- 不屬於由虧轉盈的 regime shift

### Bucket B

`turnaround_loss_to_profit`

條件：
- 前一期或去年同期小於 0
- 本期大於 0

這條策略要獨立分析，不和 Topic 06 混算。

## 5. Suggested Function Boundaries

### `build_event_comparisons.py`

- `load_events(...)`
- `extract_current_metric(...)`
- `lookup_previous_period_metric(...)`
- `calc_delta(...)`
- `calc_pct_change(...)`
- `detect_turnaround(...)`
- `assign_strategy_bucket(...)`
- `write_comparison_output(...)`

## 6. Website Implications

前端之後要能顯示：

- 正在交易事件的改善方向
- `MoM / QoQ / YoY`
- 是否由虧轉盈
- 所屬策略桶

首頁優先展示：
- 正在交易的 `topic_06_eps_catalyst`
- 正在交易的 `turnaround_loss_to_profit`

過去事件頁：
- 可以依策略桶過濾

回測績效頁：
- Topic 06 與由虧轉盈必須分開展示
