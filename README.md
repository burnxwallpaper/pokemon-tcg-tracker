# 寶可夢 TCG 行情追蹤（個人 MVP）

個人用、投機導向的日版 PSA10 鑑定卡＋未開封商品行情儀表板。顯示貨幣僅 **HKD**。  
本目錄為本機 scaffold；之後會由 bot **每日同步**到你的 PC：`C:\Users\leosiu\Documents\pokemonTCG`。

> `scripts/update.py` 會以溫和公開抓取更新真實行情。最近成交價以 SNKRDUNK 公開成交為主（港元），Yahoo 只在和 SNKRDUNK 同一張卡、價差不離譜時留下。最新賣出價係一個港元池：本地賣盤（Carousell、HKCardLink、LONO、ShipMyToy、Zenox）加上 SNKRDUNK 現時放售（日圓按固定匯率換算）。多筆取中位數，最低賣出價係池入面最低；偏離 SNKRDUNK 市價帶（約 10%–300%）或對不上的刊登留空。詳情頁連到 SNKRDUNK。各源筆數見 `meta.source_status`。`update_stub.py` 仍可產生範例資料。

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

儀表板一打開就係 **卡（PSA10）流動性** 表。盒（未開封）要撳「盒」先至出現。大異動同價差係次要分頁。讀取 `./data/latest.json`。
點擊列可開啟同頁詳情；參考連結會另開來源頁。亦可 `?id=` 直達一張卡，`?section=moves` 或 `?section=spreads` 切去次要頁。

價格欄（全部 HKD）：

| 畫面 | 欄位 | 意思 |
|------|------|------|
| 最近成交價 | `price_hkd` | SNKRDUNK 公開成交；沒有成交時先用接近的 Yahoo 已結束拍賣。一律港元 |
| 最新賣出價 | `hk_ask_hkd` | 已核對賣盤的穩健中位數（本地賣盤 + SNKRDUNK 放售換算港元；只有一筆時即該賣價） |
| 最低賣出價 | `hk_ask_low_hkd` | 同一個港元池入面最低 |
| 買入價／徵求 | `hk_bid_hkd` | 只採用 HKCardLink 公開徵收（`listing_type=wtb`）而且有正數預算。Carousell、LONO、Zenox 冇結構化徵求，對不到就係 `null`（畫面 **暫無**），不會估算 |

---

## 更新真實行情（建議）

```bash
python scripts/update.py
```

先按 Yahoo 結束拍賣筆數重排 PSA10／未開封種子（約 Top 50，見 `data/catalog/liquidity_rank.json`），再抓 JP sold／HK asks。新卡若 series 未夠深，會用 closedsearch 回填每日點（按 date merge，唔會洗走舊歷史）。寫入 `data/latest.json`、`data/history/YYYY-MM-DD.json`、`data/history/series/{id}.json`。

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
| `data/history/` | 每日歷史（約保留 90 天；格式見內文說明） |
| `scripts/update.py` | 真實更新管線：Yahoo JP + Carousell HK（HKCardLink fallback） |
| `scripts/sources/` | 溫和 scrapers |
| `scripts/update_stub.py` | 範例資料 stub（UI 測試） |
| `SOURCES.md` | JP／HK 公開資料源研究與 MVP 優先順序 |
| `README.md` | 本說明 |

---

## 產品設定（摘要）

- 追蹤：PSA10 slabs、sealed（未開封）；raw 單卡非 MVP 重點
- 自動掃描約流動性 Top 50；1日／7日價格＋量能
- 門檻（可於 `config.json` 改）：1日 ±5%、7日 ±12%、量能 ≥1.5×7日均
- 匯率起始：`1 JPY = 0.0495 HKD`（可改）
- 歷史：約 90 天
- 暫無推播；Facebook 本地店稍後再接

---

## 注意

- 僅供個人研究，非正式投資建議。
- 公開站抓取須遵守各站 ToS／robots／頻率限制；實作前請讀 `SOURCES.md`。
- 本 scaffold **不會**自動同步到你的 PC；由上層／日後 bot 負責。
