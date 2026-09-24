# 本地持久化規則（重要）

搵到嘅資料一律留低，之後只增量更新，唔好次次由零重跑。

## 存什麼
- 卡／盒身份：`id`、`name_zh`、`name_jp`、`kind`、`set`
- 官方圖：`data/images/{id}.*`（已存在且 ≥500B 就跳過下載；來源 TCGdex / pokemon-card.com）
- 官方圖 URL／`tcgdex_id`：寫入 `config.json` watchlist 同 `data/catalog/{id}.json`
- 價格走勢：`data/history/series/{id}.json`（按 date merge／append）
- 目錄索引：`data/catalog/{id}.json`（穩定欄位 + image 路徑／來源）

## 更新原則
1. `update.py` 讀舊 series／catalog，只加新成交日或刷新當日點
2. 官方圖：本地已有就跳過下載
3. 唔好用 sample 覆蓋已有真實點
4. `latest.json` 係當日快照；歷史真相喺 series／catalog
5. 流動性重排（`discover_watchlist.py`）只改 `config.json` 嘅 active watchlist。跌出名單嘅 id **唔刪** series、官方圖、`data/catalog/{id}.json`
