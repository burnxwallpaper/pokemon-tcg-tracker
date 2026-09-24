# 公開資料源研究筆記（JP / HK · PSA10 + 未開封）

研究日期：2026-09-24（HK）。
**已實作溫和 scraper**（`scripts/update.py`）：
- Yahoo Auctions JP closedsearch → `__NEXT_DATA__` sold comps ✅
- Carousell HK → 住宅 IP 可讀 `listingCards`（標題＋HK$），只收標題命中的**賣出叫價**（略過求購／WTB）
- HKCardLink → 公開 Supabase listings，與 Carousell 合併；`listing_type` 為求購的不計
- LONO `lono.com.hk` → PSA／寶可夢分類頁公開標價
- ShipMyToy `shipmytoy.com.hk` → 日版補充包 BOX；同一卡上的低價是單包，只留盒價
- Zenox `zenoxstore.com` → Shopify 日版補充包 BOX，以及有貨的 PSA10 變體（略過 PSA9）
- SNKRDUNK `snkrdunk.com/en` → 同一張卡的身份（set code＋編號）與 PSA10／BOX 日圓叫價，用來擋離譜的香港賣出價；詳情頁連回該商品
- Facebook Marketplace → 此環境 HTTP 400，無登入、不繞牆
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
| **身份＋市價帶** | SNKRDUNK（スニーカーダンク） | 對卡＋HK 叫價帶 | 公開搜尋對上 `[set 編號]`；PSA10／BOX 日圓叫價是香港賣出價的 10%–300% 帶 |
| **P1** | Cardrush（カードラッシュ） | JP 店頭賣／買 | 標價＋買取；流動性弱於拍賣但穩定可對帳 |
| **P2** | magi.camp | 未開封 BOX 上架 | sealed 上架密度高；多為 ask 非 sold |
| **P2** | 遊々亭 (Yuyu-tei) | 單卡店價 | raw／店售為主；PSA10 次要 |
| **P3** | 香港卡店官網／Facebook | 本地零售 | MVP 後；FB 需登入／反爬，先記清單 |

---

## 各源詳述

### 1. Yahoo Auctions Japan（ヤフオク）— **P0**

- **提供什麼**：進行中＋**結束（落札）**拍賣；標題、落札價 JPY、入札數、結束時間、URL。
- **PSA10 適配**：高。關鍵字如 `ポケモンカード … PSA10`；成交價可用。寫入 `price_jpy` 前會再對標題：PSA10 必須有 PSA10；未開封必須是 BOX／未開封，不是單包或卡頓。有卡號時標題要帶那個號碼（或 Erika／火箭隊超夢這類專名）。對不上、或對得上的成交少於 3 筆，最近成交價留空。`jp_sold_samples` 留最多 3 筆標題、日圓、拍賣連結。
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
- **MVP 用法**：對 Top 流動性品項搜 HK 關鍵字 → 取合理 ask 中位數 → `spread_jp_hk_pct`。Facebook 稍後再接。

### 4. SNKRDUNK（snkrdunk.com）— **身份＋市價帶**

- **提供什麼**：英文搜尋 `https://snkrdunk.com/en/v1/search` 回傳卡名（含 `[SV2a 173/165]` 這類編號）。商品日圓在 `https://snkrdunk.com/v1/apparels/{id}`；PSA10 叫價在該商品的 used 列表（`wearCount` = `tradingCardSingleConditionPSA10`）。裸卡 `usedMinPrice` 不是 PSA10。
- **怎麼對卡**：單卡搜尋用 set code＋收藏編號，標題括號裡的系列與編號都要對上，並拒絕標題帶 `EN` 的英文再版（MEW EN 201 不是 SV2a 噴火龍）。未開封用日文盒名，略過 no shrink、抽選、開封済。
- **市價**：PSA10 取至少兩筆叫價的中位數（不足兩筆才把已售 PSA10 補進）。未開封用 `minPrice`，沒有才用 `usedMinPrice`。這個日圓換算後是香港賣出價的 10%–300% 帶；沒有命中才退回 Yahoo 成交中位數。畫面上的日本參考仍是 Yahoo，不拿 SNKRDUNK 覆蓋。
- **連結**：單卡 `https://snkrdunk.com/en/trading-cards/{id}`，詳情頁「日本參考」下方。
- **ToS**：限頻（與其他來源同一間隔），只讀公開 JSON，不登入、不繞過。

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

只收**標題對得上** watchlist 的公開**賣出價**（不是收卡／求購）。寫入 `hk_ask_hkd`（香港最新賣出價）的是核對後的叫價：多筆相符取中位數；只有一筆時，標題必須自帶 set code 或卡號，而且價錢要落在日本成交中位數的 10%–300% 內，否則留空（畫面顯示 —）。`hk_listings_n` 是採用的筆數，`hk_listing_url` 是最接近該價的一則連結。日本 Yahoo 成交仍是參考價。`meta.source_status` 分開計數。

拒絕（不當賣出價）：

- 標題沒有 set code、公開系列名（151／黑炎／閃色…）或收藏編號。噴火龍不等於噴火龍 151，夢幻不等於超夢，噴火龍 X 不等於一般噴火龍。
- PSA10 對上 PSA 1–9、裸卡、AR／SR／UR（查的是 SAR 時），或編號對不上（173/165 不是 198/165，sv5k 097 不是 088）。
- 未開封對上單包、ETB、禮盒、牌組、公仔、繁中、原箱、多盒。
- 求購、WTB、收卡。
- 叫價低於對照市價一成，或高於三倍。對照市價優先用 [SNKRDUNK](https://snkrdunk.com/en/) 上同一張卡的 PSA10 叫價（未開封則用 BOX 叫價）；沒有 SNKRDUNK 時才退回 Yahoo 成交中位數。詳情頁有 SNKRDUNK 連結。單獨一筆又沒有 set code／卡號，同樣不顯示。

| 來源 | 怎麼拿 | 用什麼 |
|---|---|---|
| **Carousell HK** | `https://www.carousell.com.hk/search/{關鍵字}/` 頁內 `listingCards`（`title` + `price`） | PSA10 與未開封 BOX。住宅網路可 200；遇 Cloudflare 403 就停，不繞過 |
| **HKCardLink** | 前端 anon key → Supabase `listings` | 近期 PSA10／BOX 目錄，客戶端對標題 |
| **LONO** | `https://www.lono.com.hk/categories/psa-ptcg` 與 `/categories/pokemon-tcg` 公開分類頁（Shopline HTML，`HK$` 標價） | 店內 PSA10 與盒子。略過繁中盒，避免拿來標日版 |
| **Zenox** | `.../booster-packs-collection-box-jp/products.json` 與 `.../pokemon-psa/products.json` | 日版 Booster Box，以及**有貨**的 PSA10 變體。略過 Case、DX、PSA9、售罄變體 |
| **ShipMyToy** | `https://www.shipmytoy.com.hk/categories/pokemon-tcg` Shopline 分類頁 | 日版 BOX。同一商品若同時有單包與整盒價，丢掉低於盒價四成的那個 |
| **Facebook** | 公開 Marketplace URL 探一次 | 此 worker 回 HTTP 400，沒有可用列表。不用登入瀏覽器，也不繞登入牆 |

試過但未當價格源：`cardland.com.hk` products.json 403；`hkpokemon.com` 不是可用目錄；Price.com.hk 搜尋結果不是穩定的卡牌標價。

### 其他提及（非優先）

- **Suruga-ya / 駿河屋**：二手雜項；TCG 非最強。
- **HKCardLink 等聚合**：可能快取 SNKRDUNK 等；宜當 UI 靈感，資料請回源站驗證，並注意其免責。
- **付費 Apify／ReefAPI**：可加速原型，但有費用、依賴第三方、合規仍須自評。

---

## 建議的 MVP 資料流（實作時）

1. **Watchlist**：約 50 個高流動 PSA10＋熱門 BOX（日文關鍵字）。
2. **JP sold**：ヤフオク ended ＋ メルカリ sold_out → 正規化 HKD。
3. **訊號**：1日／7日 %、量能 vs 7日均、liquidity_score。
4. **HK**：Carousell／HKCardLink／LONO／ShipMyToy／Zenox 標題命中、並通過上面拒絕規則的賣出價 → `hk_ask_hkd`（多筆用中位數）。Yahoo 只作日本參考。不編造買價。
5. **校準**：SNKRDUNK 同一張卡的 PSA10／BOX 叫價是香港賣出價的市價帶；Yahoo 成交仍是畫面上的日本參考，不拿 SNKRDUNK 覆蓋它。

---

## 合規備註（請務必閱讀）

- 本檔僅研究筆記，**不構成**鼓勵違反各站 ToS 的指示。
- 個人、低頻率、公開頁、加快取、可停用開關（`config.json` → `sources.*.enabled`）是務實底線。
- 若站方提供官方 API／合作再優先改走官方。
- 顯示與儲存僅供個人研究；轉售或公開再分發第三方數據前請自行確認授權。
