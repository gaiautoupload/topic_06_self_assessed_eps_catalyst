# Topic 06: 自結 EPS 股價催化效應

## 目標

這個主題聚焦在公司公告自結 EPS 或自結獲利後，市場是否出現可交易的短中期催化反應。

網站定位不是單次展示，而是未來的量化交易觀看平台。首頁優先展示正在交易中的事件，歷史事件與回測績效則拆成獨立頁面。

## Topic 06 的主策略邏輯

Topic 06 目前只保留「自結 EPS / 自結獲利催化」這條主策略。

核心判斷：
- 公司是否公告了自結 EPS 或自結獲利
- 公告內容是否足夠讓我們判斷相對改善或惡化
- 公告後股價是否出現可重複的報酬反應

## 自動比較規則

實務上很多公告只給本期數字，不一定直接寫和前期比較。因此平台需要自動補比較基準。

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

原因：
- 由虧轉盈本身就是非常強的 regime shift 訊號
- 市場反應常常不同於單純 EPS 成長
- 進出場規則、樣本分布、勝率特性都可能不同

也就是說，未來事件標記上至少要能分成：
- `topic_06_eps_catalyst`
- `turnaround_loss_to_profit`

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

## 資料來源

- `D:\dataset\processed\material_events.jsonl`
- `D:\dataset\raw\mops_history\...`
- `D:\dataset\mops\20260617\t187ap04_L.json`
- `D:\dataset\processed\company_master.csv`
- `D:\dataset\processed\prices\{stock_id}.csv`

## 目前產出

- `output/events.csv`
- `output/valuation_snapshot.csv`
- `output/trades.csv`
- `site/`
- `docs/`

## 靜態網站

- 原始前端檔放在 `site/`
- GitHub Pages 發佈目錄放在 `docs/`
- 更新網站資料時執行：
  - `python generate_site_data.py`
  - `python sync_site_to_docs.py`

## 待辦

- [ ] 修正原始文字編碼，讓網站中文正常顯示
- [ ] 把公告數字轉成可比較的 period metrics
- [ ] 補 `mom / qoq / yoy` 比較欄位
- [ ] 將 `由虧轉盈` 拆成獨立策略桶
- [ ] 補更多價格資料，提升可回測樣本數
