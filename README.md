# Topic 06: 自結 EPS 股價催化效應

## 目標

這個主題聚焦在公司公告自結 EPS 或自結獲利後，市場是否出現可交易的短中期催化反應。

網站定位不是單次展示，而是未來的量化交易觀看平台。首頁優先展示正在交易中的事件，歷史事件與回測績效則拆成獨立頁面。

## Topic 06 的主策略邏輯

Topic 06 目前保留「自結 EPS / 自結獲利催化」這條主策略。

核心判斷：
- 公司是否公告自結 EPS 或自結獲利
- 公告內容是否足夠讓我們判斷相對改善或惡化
- 公告後股價是否出現可重複的報酬反應

## 自動比較規則

很多公告只給本期數字，不一定直接寫和前期比較。因此平台需要自動補比較基準。

若公告沒有明寫比較結果，後續資料處理要自動計算：
- 與上月相比增加 / 減少多少
- 與上一季相比增加 / 減少多少
- 與去年同期相比增加 / 減少多少
- 是否由虧轉盈
- 是否由盈轉虧

## 策略拆分原則

### Topic 06 保留

- 自結 EPS 正向催化
- 自結獲利改善
- 與上期或去年同期相比顯著成長

### 另立大策略

`由虧轉盈` 不放在 Topic 06 裡混做同一條策略，而是獨立成另一個大策略。

未來事件標記至少要分成：
- `topic_06_eps_catalyst`
- `turnaround_loss_to_profit`

## 月度資金配置規則

回測先採月度投組規則，而不是單筆事件各自獨立看：

- 每月資金：`100 萬`
- 預設買入檔數：`5 檔`
- 預設單檔資金：`20 萬`

若當月一開始沒有滿 5 檔，不保留現金，而是在當月公告大致揭露完成後補齊：

- 觀察月份內大約到 `10 號到 12 號`
- 若最終當月只有 `N` 檔可買，就把 `100 萬` 平均分給這 `N` 檔

例子：
- 3 檔：每檔 `33.33 萬`
- 4 檔：每檔 `25 萬`
- 5 檔以上：取排序前 5 檔，各 `20 萬`

## 本專案自己的 2026 H1 資料區

2026 上半年的補挖資料全部放在專案內，不寫回共用 `D:\dataset`：

- `project_data/2026_h1/raw_candidates.jsonl`
- `project_data/2026_h1/selected_events.csv`
- `project_data/2026_h1/main_strategy_events.csv`
- `project_data/2026_h1/manual_review_events.csv`
- `project_data/2026_h1/main_event_gaps.csv`
- `project_data/2026_h1/prices_needed.txt`
- `project_data/2026_h1/prices/`
- `project_data/2026_h1/price_specs.json`
- `project_data/2026_h1/price_validation_report.json`

## 後續資料欄位要求

事件表未來需要補這些欄位：
- `period_value_current`
- `period_value_prev_month`
- `period_value_prev_quarter`
- `period_value_yoy`
- `mom_delta`
- `qoq_delta`
- `yoy_delta`
- `mom_pct`
- `qoq_pct`
- `yoy_pct`
- `turned_profit_from_loss`
- `turned_loss_from_profit`
- `strategy_bucket`

## 共用來源

目前只讀取下列共用來源：
- `D:\dataset\processed\material_events.jsonl`
- `D:\dataset\raw\mops_history\...`
- `D:\dataset\mops\20260617\t187ap04_L.json`
- `D:\dataset\processed\company_master.csv`
- `D:\dataset\processed\prices\{stock_id}.csv`

## 目前產出

- `output/events.csv`
- `output/valuation_snapshot.csv`
- `output/trades.csv`
- `output/event_comparisons.csv`
- `site/`
- `docs/`

## 本地價格檔格式

放進 `project_data/2026_h1/prices/` 的價格檔需使用：

- 檔名：`{stock_id}.csv`
- 必要欄位：
  - `trade_date`
  - `stock_id`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`

可先用：
- `python prepare_local_price_specs.py`
- `python validate_local_prices.py`

## 靜態網站

- 原始前端檔放在 `site/`
- GitHub Pages 發佈目錄放在 `docs/`
- 更新網站資料時執行：
  - `python generate_site_data.py`
  - `python sync_site_to_docs.py`
