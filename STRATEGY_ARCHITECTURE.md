# Strategy Architecture

## Why Split Strategies

自結 EPS 改善，和「由虧轉盈」不是同一種訊號強度。

前者比較像：
- 盈利能力持續改善
- 市場做估值重評

後者比較像：
- 財務狀態跨過零軸
- 市場重新定價公司狀態

這兩者在量化交易上通常應該分開。

## Topic 06

`topic_06_eps_catalyst`

適用事件：
- 自結 EPS
- 自結獲利
- 本期優於上期 / 上季 / 去年同期

核心欄位：
- `eps_value`
- `mom_pct`
- `qoq_pct`
- `yoy_pct`

## Turnaround Strategy

`turnaround_loss_to_profit`

適用事件：
- 上一期或去年同期為虧損
- 本期為獲利

核心欄位：
- `turned_profit_from_loss`
- `previous_metric_value`
- `current_metric_value`

## Label Rules

### Keep in Topic 06

- 只是成長
- 只是改善
- 只是優於市場預期

### Move to Turnaround

- 前值 < 0 且現值 > 0
- 公告敘述明確提到由虧轉盈
- 同時出現虧轉盈與 EPS 躍升時，優先歸到 turnaround

## Frontend Rules

首頁排序：
1. `turnaround_loss_to_profit`
2. `topic_06_eps_catalyst`

歷史頁：
- 兩種策略可切換

回測頁：
- 兩條策略獨立統計
