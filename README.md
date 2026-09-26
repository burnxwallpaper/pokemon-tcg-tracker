# 寶可夢 TCG 行情追蹤（個人 MVP）

個人用、投機導向的日版 PSA10 鑑定卡＋未開封商品行情儀表板。顯示貨幣僅 **HKD**。  
本目錄為本機 scaffold；之後會由 bot **每日同步**到你的 PC：`C:\Users\leosiu\Documents\pokemonTCG`。

> `scripts/update.py` 會以溫和公開抓取更新真實行情。最近成交價以 SNKRDUNK 公開成交為主（港元），Yahoo 只在和 SNKRDUNK 同一張卡、價差不離譜時留下。最新賣出價係 SNKRDUNK 現時放售（日圓按固定匯率換算港元）的中位數。最低賣出價係池入面最低。沒有放售就留空。詳情頁連到 SNKRDUNK 同 Yahoo 已結束拍賣。各源筆數見 `meta.source_status`（只會有 SNKRDUNK 同 Yahoo）。`update_stub.py` 仍可產生範例資料。

---

## 如何開啟儀表板

瀏覽器直接開 `file://` 通常會被擋 `fetch`，請用本機靜態伺服器：

### 方式 A（建議）

在專案根目錄（本資料夾）執行：

```bash
python -m http.server 8080
```

然後瀏覽：

- http://localhost:8080/ （GitHub Pages 同樣讀根目錄 `index.html` 同 `./data/latest.json`）

### 方式 B（Windows 雙擊前先開 server）

1. 雙擊或在終端執行 `python -m http.server 8080`（工作目錄須為本專案根目錄）
2. 再開瀏覽器連到上述網址

儀表板一打開就係 **卡（PSA10）流動性** 表。盒（未開封）要撳「盒」先至出現。大異動係次要分頁。讀取 `./data/latest.json`。
點擊列可開啟同頁詳情；參考連結會另開來源頁。亦可 `?id=` 直達一張卡，`?section=moves` 切去大異動。

價格欄（全部 HKD）：

| 畫面 | 欄位 | 意思 |
|------|------|------|
| 最近成交價 | `price_hkd` | SNKRDUNK 公開成交；沒有成交時先用接近的 Yahoo 已結束拍賣。一律港元 |
| 最新賣出價 | `hk_ask_hkd` | SNKRDUNK 現時放售換算港元後的穩健中位數（只有一筆時即該賣價） |
| 最低賣出價 | `hk_ask_low_hkd` | 同一個港元池入面最低 |

---

## 更新真實行情（建議）

```bash
python scripts/update.py
```

先收 SNKRDUNK 商品頁 **Hottest Items**（例：https://snkrdunk.com/en/trading-cards/704407?slide=right ，API `/en/v1/brands/pokemon/streetwears?department=tradingCard`），再用 search `sort=hottest` 填滿剩餘名額（上限約 200，見 `data/catalog/liquidity_rank.json`），然後抓 Yahoo 已結束拍賣同 SNKRDUNK 放售。新卡若 series 未夠深，會用 closedsearch 回填每日點（按 date merge，唔會洗走舊歷史）。寫入 `data/latest.json`、`data/history/YYYY-MM-DD.json`、`data/history/series/{id}.json`。

90 日價格趨勢同成交量來自 SNKRDUNK 圖表，再按日期 merge 入 `data/history/series/{id}.json`（唔會洗走已有點）。PSA10 只用 used sales-chart 的 PSA10 option（`salesChartOptionId=22`），`range=threeMonths`；該段未開或冇點就改用 `all` 再裁到 90 日。每日價係當日圖點的中位數（只有一點時即該價），成交量係當日點數。3 個月／全部圖通常每日一個價位，所以嗰啲日的成交量係 1。未開封用新品 `sales-chart` 的「1個」；圖空先用 sales-history 的單件日期。冇 PSA10 成交就留空。詳情頁讀 series 檔，唔再用 `latest.json` 入面嗰一日快照。

```bash
python scripts/backfill_snkrdunk_history.py
```

只重排名單：`python scripts/discover_watchlist.py --force`  
跳過重排：`python scripts/update.py --no-discover`

## 重新產生範例資料

```bash
python scripts/update_stub.py
```

僅 UI／pipeline 測試用；會覆寫最新檔為範例資料。

---

## 檔案說明

| 路徑 | 用途 |
|------|------|
| `config.json` | 匯率、門檻、top_n、history_days、來源開關（目前皆關閉） |
| `dashboard/index.html` | 繁中本機儀表板（單檔 HTML+CSS+JS） |
| `data/latest.json` | 最新快照（含 meta、items、三區塊 sections） |
| `data/name_zh_map.json` | 日文→繁中對照（物種、系列、稀有度／商品詞）。`scripts/name_zh_map.translate()` 最長鍵優先 |
| `data/history/` | 每日歷史（約保留 90 天；格式見內文說明） |
| `scripts/update.py` | 真實更新管線：Yahoo JP + SNKRDUNK |
| `scripts/backfill_snkrdunk_history.py` | 用 SNKRDUNK PSA10／未開封圖表回填約 90 日價格同成交量 |
| `scripts/sources/` | 溫和 scrapers |
| `scripts/update_stub.py` | 範例資料 stub（UI 測試） |
| `SOURCES.md` | JP／HK 公開資料源研究與 MVP 優先順序 |
| `README.md` | 本說明 |

---

## 產品設定（摘要）

- 追蹤：PSA10 slabs、sealed（未開封）；raw 單卡非 MVP 重點
- PSA10 卡只用 PSA10 成交同 PSA10 放售。冇 PSA10 成交又冇 PSA10 叫價，最近成交價同賣出價留空，唔會用 A/B/C/D 補。
- 自動掃描 Hottest Items，再以搜尋熱門填到約 200（160 PSA10 + 40 未開封）；1日／7日價格＋量能
- 門檻（可於 `config.json` 改）：1日 ±15%、7日 ±25%、30日 ±50%、量能 ≥1.5×7日均
- `liquidity_score`（0–99，絕對值，唔係當日清單百分位）：`60 * log1p(約 7 日成交) / log1p(80)` ＋ `39 * log1p(放售筆數) / log1p(800)`。PSA10 用一週圖表，未開封用 sales-history 日期；卡用 `usedListingCount`，盒用 `listingCount`。冇 SNKRDUNK 成交先至用 Yahoo 今日＋7日量。約 80 筆成交或約 800 個放售先至頂滿嗰一邊，所以一般 Hottest 會落喺中段，99 要成交同放售都深。見 `discovery.liquidity_score_note`。
- 匯率起始：`1 JPY = 0.0495 HKD`（可改）
- 最低上架價：`min_list_price_hkd` = **HK$100**。有賣出價就用賣出價，否則用最近成交價；低過呢個數唔會出現喺清單。Hottest Items 的 `minPrice` 已是港元；搜尋標題係日圓 × 匯率。低過 HK$100 唔會掃入。冇可靠報價先至留空，唔會用其他等級嘅價頂上。
- 歷史：約 90 天。趨勢同成交量由 SNKRDUNK PSA10（option 22）`threeMonths` 圖回填；未開封用「1個」sales-chart
- 暫無推播。資料源只有 SNKRDUNK 同 Yahoo。

---

## 注意

- 僅供個人研究，非正式投資建議。
- 公開站抓取須遵守各站 ToS／robots／頻率限制；實作前請讀 `SOURCES.md`。
- 本 scaffold **不會**自動同步到你的 PC；由上層／日後 bot 負責。
