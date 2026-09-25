# 公開資料源研究筆記（JP / HK · PSA10 + 未開封）

研究日期：2026-09-24（HK）。
**已實作溫和 scraper**（`scripts/update.py`）：
- SNKRDUNK（https://snkrdunk.com/en/）公開目錄 → 身份對照、最近成交（有公開 sales-history 時）、PSA10 放售 ✅ **JP 主參考**，放售換算港元後就是最新賣出價
- Yahoo Auctions JP closedsearch → `__NEXT_DATA__` sold comps ✅ **次要交叉檢查**
- LONO、ShipMyToy、Zenox、Facebook、Mercari、Cardrush、遊々亭、magi → **已移除**，不再抓取、不併入賣出價、不寫入 `latest.json`
- Carousell HK 與 HKCardLink → **已移除**，不再抓取、不併入賣出價或徵求價、不寫入 `latest.json`
狀態見每次更新的 `meta.source_status`（只會列出 SNKRDUNK 同 Yahoo）。  
目標：個人溫和抓取／公開頁面，支撐 PSA10 slabs 與 sealed 的流動性＋價格。SNKRDUNK 放售換成港元；Yahoo 只作已結束拍賣對照。

誠實前提：幾乎沒有官方、穩定、免費的「成交 API」。多數是 HTML／內部 JSON、第三方聚合（Apify 等），或商店標價（非成交）。ToS 多禁止未授權爬取；個人研究也應限頻、快取、可識別 User-Agent，並優先 sold／公開列表。

---

## MVP 優先建議（總覽）

| 優先 | 來源 | 角色 | 為何 |
|------|------|------|------|
| **P0** | SNKRDUNK（https://snkrdunk.com/en/） | JP 身份＋市價主參考 | 目錄頁有正確卡名／編號／圖；密封品有公開成交，PSA10 有最低叫價。與 Yahoo 差太遠就信 SNKRDUNK 或留空 |
| **P0** | Yahoo Auctions JP（ヤフオク）結束拍賣 | JP 成交交叉檢查 | 日版樣本大，但搜尋會混卡。只在和 SNKRDUNK 同一身份、價差不離譜時採用 median |
| **P1** | Mercari JP（メルカリ）售出 | — | **已移除**，不接入 |
| **P1** | Cardrush（カードラッシュ） | — | **已移除**，不接入 |
| **P2** | magi.camp | — | **已移除**，不接入 |
| **P2** | 遊々亭 (Yuyu-tei) | — | **已移除**，不接入 |
| **不做** | 香港卡店／Facebook | — | LONO、ShipMyToy、Zenox、Facebook、Carousell、HKCardLink 都不接入 |

---

## 各源詳述

### 1. Yahoo Auctions Japan（ヤフオク）— **P0，次要交叉檢查**

- **提供什麼**：進行中＋**結束（落札）**拍賣；標題、落札價 JPY、入札數、結束時間、URL。
- **PSA10 適配**：高。關鍵字如 `ポケモンカード … PSA10`；成交價可用。
- **Sealed 適配**：高。`未開封`／`シュリンク`／`BOX`。
- **流動性訊號**：結束筆數、入札數、單位時間成交量 → 很適合 Top-50 by liquidity。
- **抓取難度**：中高。公開搜尋／結束搜尋頁；結構常變；可能要日文關鍵字＋代理。無官方公開 API。第三方（如 Apify yahoo-auction-sold-comps）有 sold summary。
- **ToS／限制**：Yahoo 服務條款通常限制自動化；需溫和頻率、尊重 robots。**勿大量並行。**
- **MVP 用法**：每日關鍵字列表抽 ended sold → median。只在和同一張卡的 SNKRDUNK 成交或 PSA10 叫價差距不離譜時顯示；否則留空。

### 2. Mercari、Cardrush、magi、遊々亭 — **已移除**

不抓取，不寫入 `latest.json`。

### 3. Carousell Hong Kong — **不接入**

已從每日管線移除。不再抓 `listingCards`，不併入港元賣出價，也不在畫面放搜尋連結。

### 4. SNKRDUNK（https://snkrdunk.com/en/）— **P0，JP 主參考**

- **提供什麼**：公開目錄頁的卡名、系列、編號、商品圖，以及市價。密封品 `sales-history` 有最近成交。單卡 PSA10 公開的是該評級最低叫價（last sale 陣列常是空的）。參考連結用英文商品頁 `https://snkrdunk.com/en/trading-cards/{id}`。
- **身份**：搜尋結果的 `[系列 編號]` 必須和 watchlist 是同一張卡。對不上就不貼連結、不拿來改價。待核對的列不猜。
- **價格**：有公開成交就用成交中位數當最近成交價，Yahoo 只作對照。只有 PSA10 最低叫價時，Yahoo 成交中位數要落在叫價的 1.75 倍以內才保留；差更遠就留空，不用那個 Yahoo 數字，也不把叫價標成成交。
- **賣出價（港元）**：PSA10 在售叫價（已售唔算）同未開封 `minPrice`，按 `fx_jpy_to_hkd` 換成港元。`hk_ask_hkd` 係呢個池的穩健中位數，`hk_ask_low_hkd` 係最低。畫面只標港元。對不上商品就留空。
- **連結**：詳情頁參考連結第一條是 `https://snkrdunk.com/en/trading-cards/{id}`。
- **抓取**：免登入 GET，沿用全站 ≥1.6 秒間隔。搜尋頁 `https://snkrdunk.com/search`、商品頁 `https://snkrdunk.com/apparels/{id}`、`/v1/apparels/{id}/sales-history`，PSA10 中位數另讀 `/v1/apparels/{id}/used`。不登入、不繞過。
- **ToS**：服務條款可限制自動化；只讀公開頁、低頻、可在 `config.json` 關掉 `sources.snkrdunk`。

### 8. 香港本地店 — **已移除**

LONO、ShipMyToy、Zenox 不再抓取，不併入港元賣出價，畫面也不放店舖連結。`hk_bid_hkd` 保持 null。

### 9. Facebook HK — **已移除**

公開頁探測沒有可用標價。不接入，不探測，不寫入 `latest.json`。

Carousell HK 與 HKCardLink 同樣已移除。

### 其他提及（非優先）

- **Suruga-ya / 駿河屋**：二手雜項；TCG 非最強。
- **付費 Apify／ReefAPI**：可加速原型，但有費用、依賴第三方、合規仍須自評。

---

## 建議的 MVP 資料流（實作時）

1. **Watchlist**：約 50 個高流動 PSA10＋熱門 BOX（日文關鍵字）。
2. **JP**：先對 SNKRDUNK 目錄（身份＋成交或 PSA10 叫價）。ヤフオク ended median 只在和 SNKRDUNK 同一張卡、價差不離譜時留下；否則留空。
3. **訊號**：1日／7日 %、量能 vs 7日均、liquidity_score。
4. **賣出價**：SNKRDUNK 現時放售 × `fx_jpy_to_hkd` → `hk_ask_hkd`（多筆用中位數）。沒有放售就留空。徵求價不接入。
5. **校準**：SNKRDUNK 是日本主參考，也是港元賣出價。Yahoo 只在同一張卡、價差不離譜時留下成交。

---

## 合規備註（請務必閱讀）

- 本檔僅研究筆記，**不構成**鼓勵違反各站 ToS 的指示。
- 個人、低頻率、公開頁、加快取、可停用開關（`config.json` → `sources.*.enabled`）是務實底線。
- 若站方提供官方 API／合作再優先改走官方。
- 顯示與儲存僅供個人研究；轉售或公開再分發第三方數據前請自行確認授權。
