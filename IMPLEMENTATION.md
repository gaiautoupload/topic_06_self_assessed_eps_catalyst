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

4. `build_event_comparisons.py`
   - 補前值、比較值與策略桶

5. `build_2026_h1_local_dataset.py`
   - 在專案內建立 2026 上半年的本地事件池

6. `generate_site_data.py`
   - 將輸出整理成前端資料

7. `sync_site_to_docs.py`
   - 將 `site/` 同步到 `docs/`

## 2. New Comparison Layer

Topic 06 下一個必要模組不是先加更多前端，而是補「比較層」。

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

## 5. 2026 H1 Local Dataset Rule

2026 H1 回測先只用專案自己的本地資料：

- `project_data/2026_h1/main_strategy_events.csv`
- `project_data/2026_h1/manual_review_events.csv`
- `project_data/2026_h1/prices/`

原則：
- 只從共用資料讀
- 不往共用 `D:\dataset` 寫

## 6. Monthly Portfolio Rule

第一版月度資金模型：

- 月資金池：`1,000,000`
- 目標持股數：`5`
- 標準單筆：`200,000`

排序原則：
1. `turnaround_loss_to_profit`
2. `topic_06_eps_catalyst`
3. 有比較基準者優先
4. EPS 較高者優先
5. 公告日較早者優先

補齊原則：
- 若當月事件數 `>= 5`：取前 5 檔，各 `200,000`
- 若當月事件數 `< 5`：全部納入，平均分配到滿 `1,000,000`
- 月內公告收斂點先視為 `10-12` 號

## 7. Next Modules

下一步建議模組：

1. `build_monthly_portfolio.py`
   - 依月份組成投組
   - 套用每月 100 萬、目標 5 檔、10-12 號補齊滿配規則

2. `backtest_2026_h1_local.py`
   - 專吃 `project_data/2026_h1/`
   - 直接產出月度投組回測
