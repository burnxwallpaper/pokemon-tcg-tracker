# 公開資料源研究筆記（JP / HK · PSA10 + 未開封）

研究日期：2026-09-24（HK）。
**已實作溫和 scraper**（`scripts/update.py`）：
- Yahoo Auctions JP closedsearch → `__NEXT_DATA__` sold comps ✅
- Carousell HK → 目前 Cloudflare 403；fallback HKCardLink 公開 Supabase listings ✅（部分命中）
- Facebook HK（Marketplace／專頁／社團）→ 2026-09-24 無登入探測失敗，**未接入**。見 §8
狀態見每次更新的 `meta.source_status`。  
目標：個人溫和抓取／公開頁面，支撐 PSA10 slabs 與 sealed 的流動性＋價格，並與香港叫價比對。

誠實前提：幾乎沒有官方、穩定、免費的「成交 API」。多數是 HTML／內部 JSON、第三方聚合（Apify 等），或商店標價（非成交）。ToS 多禁止未授權爬取；個人研究也應限頻、快取、可識別 User-Agent，並優先 sold／公開列表。

---

## MVP 優先建議（總覽）

| 優先 | 來源 | 角色 | 為何 |
|------|------|------|------|
| **P0** | Yahoo Auctions JP（ヤフオク）結束拍賣 | JP 成交＋流動性 | 日版 PSA10／BOX 成交樣本最大；可算 median／量 |
| **P0** | Mercari JP（メルカリ）售出 | JP 成交補完 | C2C 量大、PSA10／未開封關鍵字好搜 |
| **P0** | Carousell HK | HK MVP 叫價 | 本地面交／寄賣主戰場；價差區塊必要 |
| **P1** | SNKRDUNK（スニーカーダンク） | JP 市價參考 | 鑑定卡 last-sold／ask 整齊；適合 PSA10 watchlist |
| **P1** | Cardrush（カードラッシュ） | JP 店頭賣／買 | 標價＋買取；流動性弱於拍賣但穩定可對帳 |
| **P2** | magi.camp | 未開封 BOX 上架 | sealed 上架密度高；多為 ask 非 sold |
| **P2** | 遊々亭 (Yuyu-tei) | 單卡店價 | raw／店售為主；PSA10 次要 |
| **P3** | 香港卡店官網 | 本地零售 | 只接免登入目錄（Shopify `products.json`、Shopline 分類頁） |
| **不做** | Facebook HK | 本地叫價 | 2026-09-24 無登入探測無標價。見 §8 下一步 |

---

## 各源詳述

### 1. Yahoo Auctions Japan（ヤフオク）— **P0**

- **提供什麼**：進行中＋**結束（落札）**拍賣；標題、落札價 JPY、入札數、結束時間、URL。
- **PSA10 適配**：高。關鍵字如 `ポケモンカード … PSA10`；成交價可用。
- **Sealed 適配**：高。`未開封`／`シュリンク`／`BOX`。
- **流動性訊號**：結束筆數、入札數、單位時間成交量 → 很適合 Top-50 by liquidity。
- **抓取難度**：中高。公開搜尋／結束搜尋頁；結構常變；可能要日文關鍵字＋代理。無官方公開 API。第三方（如 Apify yahoo-auction-sold-comps）有 sold summary。
- **ToS／限制**：Yahoo 服務條款通常限制自動化；需溫和頻率、尊重 robots。**勿大量並行。**
- **MVP 用法**：每日關鍵字列表（watchlist）抽 ended sold → median JPY → × FX → HKD；記 `volume_today`。

### 2. Mercari Japan（jp.mercari.com）— **P0**

- **提供什麼**：C2C 上架＋**售出（売り切れ）**；售出價、狀態、標題。
- **PSA10／Sealed**：高（同關鍵字策略）。售出可作 comps；在售可作 ask。
- **流動性**：售出速度／筆數佳；與ヤフオク互補（固價 vs 競價）。
- **抓取難度**：中高。前端多為客戶端渲染；實務常打內部 JSON 或用第三方（Apify mercari sold、ReefAPI 等）。HTML 裸抓困難。
- **ToS**：禁止未授權爬取／濫用的條款常見；第三方 API 屬灰色、付費、且可能隨時失效。
- **MVP 用法**：與ヤフオク同一 watchlist 合併 median；量能加總。

### 3. Carousell Hong Kong（hk.carousell.com）— **P0（HK）**

- **提供什麼**：本地二手／收藏叫價（ask）；PSA10、sealed BOX 都有刊登。分類路徑約在 Hobbies → Collectibles → Trading cards。
- **PSA10／Sealed**：中高（標題品質參差，需正規化）。
- **流動性**：刊登數＋「聊過／想要」可粗估；**成交價多半不可見** → 價差用 ask vs JP sold。
- **抓取難度**：中。列表／搜尋頁；地區選 HK；反爬與登入牆可能出現。
- **ToS**：平台禁止未授權 scraping 的機率高；個人低頻搜尋較務實。
- **MVP 用法**：對 Top 流動性品項搜 HK 關鍵字 → 取合理 ask 中位數 → `spread_jp_hk_pct`。香港 Facebook 叫價見 §8，目前不能接。

### 4. SNKRDUNK（snkrdunk.com）— **P1**

- **提供什麼**：球鞋起家的鑑定卡市集；last sold／最低 ask 等（以站上顯示為準）。第三方有卡片搜尋／報價工具與非官方 API 包裝。
- **PSA10**：很高（市集偏 graded）。
- **Sealed**：中（以單卡／鑑定為主；BOX 較少）。
- **流動性**：有成交次數可用；適合 PSA10 核心清單。
- **抓取難度**：中高。無穩定公開官方 API；第三方 Parse／Spider 等需評估授權與費用。
- **ToS**：服務條款可限制自動化；**不要假設可自由 bulk scrape**。
- **MVP 用法**：PSA10 參考價第二來源；與ヤフオク／メルカリ交叉驗證異常跳動。

### 5. Cardrush（cardrush.jp / cardrush.media）— **P1**

- **提供什麼**：大型日系 TCG 店網路；**賣價＋買取價**、庫存、狀態（含鑑定表記）。`cardrush.media` 買取列表曾出現可帶 `to_json_option` 的列表介面（社群／文章有範例）— **非正式 API，隨時可能關**。
- **PSA10**：中高（店內鑑定品／標註）。
- **Sealed**：中（BOX／パック買取與販售有，但成交量不如 C2C）。
- **流動性**：庫存變化可參考；不如拍賣「真成交量」。
- **抓取難度**：中。商店 HTML／疑似 JSON 列表；Apify 有 CardRush／Pokémon price actor。
- **ToS**：零售站通常不歡迎 bulk；限頻＋快取。
- **MVP 用法**：店價錨點、買取下限；不單獨當「市場成交」。

### 6. magi（magi.camp）— **P2**

- **提供什麼**：個人／店家出價市集；**未開封 BOX** 上架多。
- **PSA10**：中低。
- **Sealed**：高（ask 密度）。
- **流動性**：上架數可參考；sold 較難系統化。
- **抓取難度**：中。
- **MVP 用法**：sealed 叫價輔助；成交仍以ヤフオク／メルカリ為準。

### 7. 遊々亭 Yuyu-tei（yuyu-tei.jp）— **P2**

- **提供什麼**：大型單卡店賣價／買取、稀有度、庫存；第三方 scraper 可拉 sell+buy spread。
- **PSA10**：低～中（主戰場是 raw／店況）。
- **Sealed**：低。
- **MVP 用法**：非本產品核心；若日後擴 raw 再升優先。

### 8. Facebook HK 叫價 — **公開探測失敗，不接入**

2026-09-24 從本 worker 探測。一般瀏覽器 User-Agent、無 cookie、無登入、不解 challenge、不打需 `fb_dtsg` 的 GraphQL。

| 表面 | 結果 |
|------|------|
| `www.facebook.com/marketplace/hongkong/search?query=pokemon+PSA10` | HTTP 400，標題 Error，「Sorry, something went wrong」。無 listing、無 HK$ |
| 同上路徑的 `m.facebook.com`、`touch.facebook.com` | 轉到 www，同樣 HTTP 400 |
| `mbasic.facebook.com/marketplace/...`、專頁、`/groups/` | HTTP 400，或首頁 HTTP 200 但只顯示「目前無法在此瀏覽器上使用 Facebook」。`og:title` 為「登入或註冊即可查看」 |
| `www.facebook.com/`、`/Pokemon/`、`/zenoxstore/` | 同樣 HTTP 400，沒有貼文或標價 |
| Ads Library（`country=HK`） | HTTP 403，頁內是 JS challenge。不解 |
| `graph.facebook.com` search，空 token | OAuth 錯誤。Marketplace 沒有免 token 的公開列表 |
| `robots.txt` | 開頭寫明未經 Facebook 書面許可禁止自動化蒐集；對所有 user-agent `Disallow: /` |

沒有可解析的標題＋HKD。因此**不加** `scripts/sources`、不開 `config.json` 開關、不把個人 session 放進 `update.py`。

**下一步（重試條件，要同時成立）：**

1. 同一個無 cookie GET 回到 **HTTP 200**。
2. 本文已含商品標題與 HKD 標價。登入頁、「Sorry, something went wrong」、「目前無法在此瀏覽器上使用」、Ads Library challenge 都算失敗，停。
3. 只為那個**具體公開 URL** 寫 parser（例如某店免登入的 Shopify `products.json` 或 Shopline 分類頁）。不要做 Marketplace 關鍵字搜尋，也不要抓社團。
4. 官方另一條路：Meta App 通過 Page Public Content Access，且只讀已授權專頁。那不是 Marketplace 成交／叫價；此 repo 沒有這組憑證，每日 job 不要等它。

在上述條件出現之前，香港叫價維持 Carousell／HKCardLink。店家官網若本身免登入列出標價，另開一源，不經 Facebook。

### 其他提及（非優先）

- **Suruga-ya / 駿河屋**：二手雜項；TCG 非最強。
- **HKCardLink 等聚合**：可能快取 SNKRDUNK 等；宜當 UI 靈感，資料請回源站驗證，並注意其免責。
- **付費 Apify／ReefAPI**：可加速原型，但有費用、依賴第三方、合規仍須自評。

---

## 建議的 MVP 資料流（實作時）

1. **Watchlist**：約 50 個高流動 PSA10＋熱門 BOX（日文關鍵字）。
2. **JP sold**：ヤフオク ended ＋ メルカリ sold_out → 正規化 HKD。
3. **訊號**：1日／7日 %、量能 vs 7日均、liquidity_score。
4. **HK**：Carousell ask → 價差。
5. **校準**：SNKRDUNK／Cardrush 作異常檢查，不覆蓋成交主源。

---

## 合規備註（請務必閱讀）

- 本檔僅研究筆記，**不構成**鼓勵違反各站 ToS 的指示。
- 個人、低頻率、公開頁、加快取、可停用開關（`config.json` → `sources.*.enabled`）是務實底線。
- 若站方提供官方 API／合作再優先改走官方。
- 顯示與儲存僅供個人研究；轉售或公開再分發第三方數據前請自行確認授權。
