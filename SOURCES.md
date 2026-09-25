# 公開資料源研究筆記（JP / HK · PSA10 + 未開封）

研究日期：2026-09-24（HK）。
**已實作溫和 scraper**（`scripts/update.py`）：
- SNKRDUNK（https://snkrdunk.com/en/）公開目錄 → 身份對照、最近成交（有公開 sales-history 時）、PSA10 最低叫價 ✅ **JP 主參考**
- Yahoo Auctions JP closedsearch → `__NEXT_DATA__` sold comps ✅ **次要交叉檢查**
- LONO `lono.com.hk`、ShipMyToy `shipmytoy.com.hk`、Zenox `zenoxstore.com`（日版 BOX 與有貨 PSA10）→ 香港賣出價。偏離 SNKRDUNK 日圓市價 10%–300% 的叫價留空
- Facebook HK → 無登入探測失敗，**未接入**。見 §9
- Carousell HK 與 HKCardLink → **已移除**，不再抓取、不併入賣出價或徵求價、不寫入 `latest.json`
狀態見每次更新的 `meta.source_status`。  
目標：個人溫和抓取／公開頁面，支撐 PSA10 slabs 與 sealed 的流動性＋價格，並與香港叫價比對。

誠實前提：幾乎沒有官方、穩定、免費的「成交 API」。多數是 HTML／內部 JSON、第三方聚合（Apify 等），或商店標價（非成交）。ToS 多禁止未授權爬取；個人研究也應限頻、快取、可識別 User-Agent，並優先 sold／公開列表。

---

## MVP 優先建議（總覽）

| 優先 | 來源 | 角色 | 為何 |
|------|------|------|------|
| **P0** | SNKRDUNK（https://snkrdunk.com/en/） | JP 身份＋市價主參考 | 目錄頁有正確卡名／編號／圖；密封品有公開成交，PSA10 有最低叫價。與 Yahoo 差太遠就信 SNKRDUNK 或留空 |
| **P0** | Yahoo Auctions JP（ヤフオク）結束拍賣 | JP 成交交叉檢查 | 日版樣本大，但搜尋會混卡。只在和 SNKRDUNK 同一身份、價差不離譜時採用 median |
| **P1** | Mercari JP（メルカリ）售出 | JP 成交補完 | C2C 量大；目前未接入 |
| **P1** | Cardrush（カードラッシュ） | JP 店頭賣／買 | 標價＋買取；流動性弱於拍賣但穩定可對帳 |
| **P2** | magi.camp | 未開封 BOX 上架 | sealed 上架密度高；多為 ask 非 sold |
| **P2** | 遊々亭 (Yuyu-tei) | 單卡店價 | raw／店售為主；PSA10 次要 |
| **P3** | 香港卡店官網 | 本地零售 | 已接免登入目錄：LONO、ShipMyToy、Zenox。Carousell 與 HKCardLink 不接入 |
| **不做** | Facebook HK | 本地叫價 | 2026-09-24 無登入探測無標價。見 §8 下一步 |

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

### 2. Mercari Japan（jp.mercari.com）— **P0**

- **提供什麼**：C2C 上架＋**售出（売り切れ）**；售出價、狀態、標題。
- **PSA10／Sealed**：高（同關鍵字策略）。售出可作 comps；在售可作 ask。
- **流動性**：售出速度／筆數佳；與ヤフオク互補（固價 vs 競價）。
- **抓取難度**：中高。前端多為客戶端渲染；實務常打內部 JSON 或用第三方（Apify mercari sold、ReefAPI 等）。HTML 裸抓困難。
- **ToS**：禁止未授權爬取／濫用的條款常見；第三方 API 屬灰色、付費、且可能隨時失效。
- **MVP 用法**：與ヤフオク同一 watchlist 合併 median；量能加總。

### 3. Carousell Hong Kong — **不接入**

已從每日管線移除。不再抓 `listingCards`，不併入港元賣出價，也不在畫面放搜尋連結。

### 4. SNKRDUNK（https://snkrdunk.com/en/）— **P0，JP 主參考**

- **提供什麼**：公開目錄頁的卡名、系列、編號、商品圖，以及市價。密封品 `sales-history` 有最近成交。單卡 PSA10 公開的是該評級最低叫價（last sale 陣列常是空的）。參考連結用英文商品頁 `https://snkrdunk.com/en/trading-cards/{id}`。
- **身份**：搜尋結果的 `[系列 編號]` 必須和 watchlist 是同一張卡。對不上就不貼連結、不拿來改價。待核對的列不猜。
- **價格**：有公開成交就用成交中位數當最近成交價，Yahoo 只作對照。只有 PSA10 最低叫價時，Yahoo 成交中位數要落在叫價的 1.75 倍以內才保留；差更遠就留空，不用那個 Yahoo 數字，也不把叫價標成成交。
- **賣出價（港元）**：PSA10 在售叫價（已售唔算）的最低、中位、最高，以及未開封 `minPrice`，按 `fx_jpy_to_hkd` 換成港元後，同已核對的本地賣盤合成一個池。`hk_ask_hkd` 係池的穩健中位數，`hk_ask_low_hkd` 係最低。畫面只標港元。對不上商品就留空。
- **本地市價帶**：同一商品的 used 列表裡，PSA10 叫價取中位數（少於兩筆才把已售 PSA10 補進，呢個中位數只用來篩本地賣盤，唔會當成放售）。未開封用 `minPrice`，沒有才用 `usedMinPrice`。換算 HKD 後，本地賣出價落在這條市價的 10%–300% 外就丢掉；寧可留空，也不顯示一個離譜數字。標題帶 `EN` 的英文再版不算同一張卡。151 BOX 不會採用單包、ETB 或其他卡的叫價。
- **連結**：詳情頁參考連結第一條是 `https://snkrdunk.com/en/trading-cards/{id}`。
- **抓取**：免登入 GET，沿用全站 ≥1.6 秒間隔。搜尋頁 `https://snkrdunk.com/search`、商品頁 `https://snkrdunk.com/apparels/{id}`、`/v1/apparels/{id}/sales-history`，PSA10 中位數另讀 `/v1/apparels/{id}/used`。不登入、不繞過。
- **ToS**：服務條款可限制自動化；只讀公開頁、低頻、可在 `config.json` 關掉 `sources.snkrdunk`。

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

### 8. 香港本地叫價（已接入）

只收**標題對得上** watchlist 的公開**賣出價**。沒有接入徵求／WTB，`hk_bid_hkd` 保持 null。多筆相符取中位數寫入 `hk_ask_hkd`。只有一筆時，標題要自帶 set code 或卡號，而且價錢要落在 SNKRDUNK 市價的 10%–300% 內，否則留空。拒絕英文再版、151 盒對上單包／ETB／卡、以及 PSA10 對上其他評級。`meta.source_status` 分開計數。

| 來源 | 怎麼拿 | 用什麼 |
|---|---|---|
| **LONO** | `https://www.lono.com.hk/categories/psa-ptcg` 與 `/categories/pokemon-tcg` 公開分類頁（Shopline HTML，`HK$` 標價） | 店內 PSA10 與盒子。略過繁中盒，避免拿來標日版 |
| **Zenox** | `.../booster-packs-collection-box-jp/products.json` 與 `.../pokemon-psa/products.json` | 日版 Booster Box，以及有貨的 PSA10 變體。略過 Case、DX、PSA9、售罄 |
| **ShipMyToy** | `https://www.shipmytoy.com.hk/categories/pokemon-tcg` | 日版 BOX。同一商品若同時有單包與整盒價，丢掉低於盒價四成的那個 |
| **Facebook** | 公開 Marketplace URL 探一次 | 此 worker 回 HTTP 400，沒有可用列表。不用登入瀏覽器，也不繞登入牆 |

Carousell HK 與 HKCardLink 已從這張表拿掉，不再當價格源。

試過但未當價格源：`cardland.com.hk` products.json 403；`hkpokemon.com` 不是可用目錄；Price.com.hk 搜尋結果不是穩定的卡牌標價。

### 9. Facebook HK 叫價 — **公開探測失敗，不接入**

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

在上述條件出現之前，香港叫價維持 LONO／ShipMyToy／Zenox。店家官網若本身免登入列出標價，另開一源，不經 Facebook。

### 其他提及（非優先）

- **Suruga-ya / 駿河屋**：二手雜項；TCG 非最強。
- **付費 Apify／ReefAPI**：可加速原型，但有費用、依賴第三方、合規仍須自評。

---

## 建議的 MVP 資料流（實作時）

1. **Watchlist**：約 50 個高流動 PSA10＋熱門 BOX（日文關鍵字）。
2. **JP**：先對 SNKRDUNK 目錄（身份＋成交或 PSA10 叫價）。ヤフオク ended median 只在和 SNKRDUNK 同一張卡、價差不離譜時留下；否則留空。
3. **訊號**：1日／7日 %、量能 vs 7日均、liquidity_score。
4. **HK**：LONO／ShipMyToy／Zenox 標題命中、並通過拒絕規則的賣出價 → `hk_ask_hkd`（多筆用中位數）。對不上或超出 SNKRDUNK 市價帶就留空。徵求價不接入。
5. **校準**：SNKRDUNK 是日本主參考，也是香港賣出價的市價帶。Cardrush 仍只作店價錨點，不覆蓋成交。

---

## 合規備註（請務必閱讀）

- 本檔僅研究筆記，**不構成**鼓勵違反各站 ToS 的指示。
- 個人、低頻率、公開頁、加快取、可停用開關（`config.json` → `sources.*.enabled`）是務實底線。
- 若站方提供官方 API／合作再優先改走官方。
- 顯示與儲存僅供個人研究；轉售或公開再分發第三方數據前請自行確認授權。
