# 寶可夢 TCG 行情追蹤（個人 MVP）

個人用、投機導向的日版 PSA10 鑑定卡＋未開封商品行情儀表板。顯示貨幣僅 **HKD**。  
本目錄為本機 scaffold；之後會由 bot **每日同步**到你的 PC：`C:\Users\leosiu\Documents\pokemonTCG`。

> `scripts/update.py` 會以溫和公開抓取更新真實行情。日本參考價是 Yahoo 結束拍賣裡標題對得上的成交中位數（少於 3 筆就留空）。香港最新賣出價來自 Carousell、HKCardLink、LONO、ShipMyToy、Zenox，多筆相符取中位數，對不上或偏離日本成交太遠就留空。求購／收卡價不算。各源筆數見 `meta.source_status`。`update_stub.py` 仍可產生範例資料。

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

儀表板首頁先分 **卡（PSA10）**／**盒（未開封）**，再睇 **大異動**／**流動性**／**價差**。讀取 `./data/latest.json`。
點擊卡片或流動性列可開啟同頁詳情面板（約 90 日價格／量能圖）；亦可 `?id=sample-001`。

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
