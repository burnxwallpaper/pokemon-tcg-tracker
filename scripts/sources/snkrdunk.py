"""SNKRDUNK public catalog: identity match and JP market check.

Search HTML and apparel pages are readable without a login. PSA10 asks and
recent sales come from the used feed filtered to condition 22 (PSA10). When
that feed and the PSA10 chart are both empty, condition A (18) single-copy
listings on the same product fill last sale and asks. Other grades stay out.
The apparel sales-history feed is for sealed boxes and is empty for slabs.
A last sale replaces Yahoo. An ask that is far from Yahoo blanks the Yahoo figure.
Multi-box lot sizes (2個 and up) and multi-copy lots (2枚 and up) are not this SKU.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

from ._http import polite_get
from .hk_match import (
    _SET_IDS,
    _card_print,
    _groups_in,
    _identity_aligned,
    _identity_codes,
    _is_box,
    _is_illustration_rare,
    _non_jp,
    _sealed_side_product,
    _stage_conflict,
    _stated_rarity_conflict,
    _wants_illustration_rare,
    robust_median,
)
from .jp_match import _identity, _item_fraction, _item_set_code, robust_median_jpy

SEARCH_URL = "https://snkrdunk.com/search"
APPAREL_URL = "https://snkrdunk.com/apparels/{apparel_id}"
SALES_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/sales-history"
SALES_CHART_USED_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/sales-chart/used"
EN_URL = "https://snkrdunk.com/en/trading-cards/{apparel_id}"
APPAREL_JSON_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}"
USED_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/used"
PSA10_WEAR = "tradingCardSingleConditionPSA10"
PSA10_CONDITION_IDS = "22"
RAW_A_WEAR = "tradingCardSingleConditionNearlyUnused"
RAW_A_CONDITION_IDS = "18"
_UNIT_COUNT = re.compile(r"(\d+)\s*(?:個|箱|ボックス|boxes|box)", re.I)
_SHEET_COUNT = re.compile(r"(\d+)\s*枚")
_BRACKET = re.compile(
    r"\[([A-Za-z]+\d+[A-Za-z]*)\s+(\d{2,3})(?:\s*/\s*\d{2,3})?\]"
)
_SEALED_SKIP = re.compile(r"no shrink|シュリンクなし|抽選|開封済|campaign ended", re.I)
_SEALED_NOISE = re.compile(r"未開封|シュリンク付き|シュリンク|shrink", re.I)
_MULTI_BOX = re.compile(r"(?<!\d)(\d{1,2})\s*(?:box|ボックス|箱|盒)", re.I)
_EN_REPRINT = re.compile(r"\bEN\b|\[EN|英語", re.I)

# Yahoo vs SNKRDUNK. Beyond this ratio the Yahoo median is not shown.
DISAGREE_RATIO = 1.75

_TILE = re.compile(
    r'href="https://snkrdunk.com/apparels/(\d+)(?:/used/\d+)?"[^>]*aria-label="([^"]+)"'
)
_CARD_NO = re.compile(
    r"\[([A-Za-z]+\d+[A-Za-z]*)\s+(\d{2,3})(?:\s*/\s*(\d{2,3}))?\]"
)
_YEN = re.compile(r"¥\s*([\d,]+)\s*$")
_COND = re.compile(
    r'"filterConditionId":"([^"]+)"'
    r'(?:,"usedMinPrice":(\d+))?'
    r',"text":"([^"]+)","hasListing":(true|false)'
)
_PRIMARY_IMAGE = re.compile(
    r"https://cdn\.snkrdunk\.com/upload_bg_removed/[0-9a-f-]+\.webp"
)


def official_face_matches(url: str | None, set_code: str | None, number: str | None) -> bool:
    """True only when the URL is this set+number, and not an English stand-in.

    A pokemon-card.com file named after the base ex (no collector number) does
    not match a SAR/UR/gold print. Prefer no face over that art.
    """
    if not url or not set_code or not number or not str(number).isdigit():
        return False
    if re.search(r"SVP_EN|_EN_|/en/|英語|英語版", url, re.I):
        return False
    wanted = int(number)
    code = set_code.lower()
    segments = [part.lower() for part in url.split("/") if part]
    if code not in segments and not any(code in part for part in segments):
        return False
    for part in segments:
        stem = part.split(".")[0]
        if stem.isdigit() and int(stem) == wanted:
            return True
        for piece in re.findall(r"\d{2,3}", stem):
            if int(piece) == wanted and code in stem:
                return True
    return False


def en_product_url(apparel_id: str | None) -> str | None:
    if not apparel_id:
        return None
    return EN_URL.format(apparel_id=apparel_id)


def parse_tiles(page_html: str) -> list[dict[str, Any]]:
    """Unique catalog hits from a public search page."""
    seen: set[str] = set()
    tiles: list[dict[str, Any]] = []
    for apparel_id, raw_label in _TILE.findall(page_html or ""):
        if apparel_id in seen:
            continue
        seen.add(apparel_id)
        label = html.unescape(raw_label).strip()
        price = None
        yen = _YEN.search(label)
        name = label
        if yen:
            price = int(yen.group(1).replace(",", ""))
            name = label[: yen.start()].strip(" -")
        number = _CARD_NO.search(name)
        tiles.append(
            {
                "apparel_id": apparel_id,
                "label": name,
                "tile_price_jpy": price,
                "set_code": number.group(1) if number else None,
                "number": number.group(2) if number else None,
                "denom": number.group(3) if number else None,
            }
        )
    return tiles


def _local_number(item: dict) -> str | None:
    found = re.search(r"/\s*(\d{2,3})\s*$", str(item.get("set") or "").strip())
    if not found:
        return None
    return found.group(1)


def _pack_only(label: str) -> bool:
    if "パック" not in label:
        return False
    folded = label.lower()
    return "ボックス" not in label and "box" not in folded


def tile_matches(tile: dict, item: dict) -> bool:
    """True when the catalog title is this watchlist card or box."""
    label = str(tile.get("label") or "")
    folded = label.lower().replace(" ", "").replace("　", "")
    identity = _identity(item)
    if not identity or identity not in folded:
        return False
    if _EN_REPRINT.search(label):
        return False
    if str(item.get("kind") or "") == "sealed":
        if _pack_only(label) or ("ボックス" not in label and "box" not in folded):
            return False
        if _SEALED_SKIP.search(label) or "シュリンク無" in label:
            return False
        if re.search(r"カートン|\bcase\b", label, re.I):
            return False
        multi = _MULTI_BOX.search(label)
        if multi and int(multi.group(1)) >= 2:
            return False
    code = _item_set_code(item)
    tile_code = str(tile.get("set_code") or "").lower()
    if code and tile_code and tile_code != code:
        return False
    frac = _item_fraction(item)
    number = tile.get("number")
    denom = tile.get("denom")
    if frac:
        if number != frac[0]:
            return False
        if denom and denom != frac[1]:
            return False
        return True
    local = _local_number(item)
    if local and number and number != local:
        return False
    return True


_CATALOG_SKIP = re.compile(
    r"遊戯王|ネックレス|necklace|bracelet|hoodie|t-shirt|sukajan|シュリンクなし|"
    r"シュリンク無|カートン|\bcase\b|英語版|\[EN\b",
    re.I,
)


def catalog_kind(tile: dict) -> str | None:
    """Hottest-search hit we are willing to track. None drops jewelry, EN, and packs."""
    label = str(tile.get("label") or "")
    if not label or _CATALOG_SKIP.search(label) or _EN_REPRINT.search(label):
        return None
    if str(tile.get("set_code") or "") and str(tile.get("number") or ""):
        return "psa10"
    if "ポケモン" in label and _is_box(label) and not _pack_only(label):
        if re.search(r"カートン|\bcase\b", label, re.I):
            return None
        multi = _MULTI_BOX.search(label)
        if multi and int(multi.group(1)) >= 2:
            return None
        return "sealed"
    return None


def collect_hottest_tiles(
    *,
    pages: int,
    min_interval: float,
    keywords: tuple[str, ...] = ("ポケモンカード", "ポケモンカード PSA10", "ポケモンカード ボックス"),
) -> list[dict]:
    """Hottest SNKRDUNK search hits, first-seen order, one row per apparel id."""
    seen: set[str] = set()
    tiles: list[dict] = []
    for keyword in keywords:
        for page in range(1, max(1, pages) + 1):
            try:
                resp = polite_get(
                    SEARCH_URL,
                    params={"keywords": keyword, "sort": "hottest", "page": str(page)},
                    min_interval=min_interval,
                    timeout=25,
                    headers={"Accept-Language": "ja,en;q=0.8"},
                )
            except Exception:
                break
            if resp.status_code != 200:
                break
            batch = parse_tiles(resp.text)
            fresh = 0
            for tile in batch:
                apparel_id = str(tile.get("apparel_id") or "")
                if not apparel_id or apparel_id in seen:
                    continue
                if catalog_kind(tile) is None:
                    continue
                seen.add(apparel_id)
                tiles.append(tile)
                fresh += 1
            if fresh == 0:
                break
    return tiles


def search_queries(item: dict) -> list[str]:
    name = str(item.get("name_jp") or item.get("search_jp") or "")
    name = re.sub(r"（待核對）", " ", name)
    name = re.sub(r"PSA\s*10", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return []
    queries = [name]
    frac = _item_fraction(item)
    if frac:
        queries.insert(0, f"{name} {frac[0]}/{frac[1]}")
    short = re.sub(r"BOX|未開封|シュリンク", " ", name, flags=re.I)
    short = re.sub(r"\s+", " ", short).strip()
    if short and short not in queries:
        queries.append(short)
    return queries


def choose_match(tiles: list[dict], item: dict) -> dict | None:
    hits = [tile for tile in tiles if tile_matches(tile, item)]
    ids = {str(tile.get("apparel_id")) for tile in hits}
    if len(ids) != 1:
        return None
    return hits[0]


def parse_condition_asks(page_html: str) -> dict[str, int]:
    """Grade label → lowest public ask, when the page prints one."""
    asks: dict[str, int] = {}
    for _fid, price, text, has in _COND.findall(page_html or ""):
        if has != "true" or not price:
            continue
        asks[text] = int(price)
    return asks


def single_sku_sale(row: dict) -> bool:
    """A 2個 / 6個 / 10個 lot is not the single box on the watchlist."""
    size = str((row or {}).get("size") or "")
    found = _UNIT_COUNT.search(size)
    if found and int(found.group(1)) >= 2:
        return False
    return True


def single_sheet(row: dict) -> bool:
    """1枚 is this card. 2枚 and up are lots, not the single on the watchlist."""
    size = (row or {}).get("size")
    label = ""
    if isinstance(size, dict):
        label = str(size.get("localizedName") or "")
    elif isinstance(size, str):
        label = size
    found = _SHEET_COUNT.search(label)
    if found and int(found.group(1)) >= 2:
        return False
    return True


def parse_sales_history(payload: dict) -> int | None:
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return None
    prices: list[int] = []
    for row in history:
        if not isinstance(row, dict) or not single_sku_sale(row):
            continue
        try:
            price = int(row.get("price"))
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
        if len(prices) >= 12:
            break
    return robust_median_jpy(prices)


def prices_disagree(left: int, right: int) -> bool:
    lo = min(left, right)
    hi = max(left, right)
    if lo <= 0:
        return True
    return hi / lo >= DISAGREE_RATIO


def _pos_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return int(round(value))


def choose_jp_price(yahoo_jpy: int | None, snkr: dict | None) -> tuple[int | None, str]:
    """SNKRDUNK last sale wins. An ask only vetoes a distant Yahoo median."""
    snkr = snkr or {}
    last = _pos_int(snkr.get("last_sale_jpy"))
    ask = _pos_int(snkr.get("ask_jpy"))
    yahoo = _pos_int(yahoo_jpy)
    if last is not None:
        return last, "snkrdunk_last_sale"
    if yahoo is not None and ask is not None and prices_disagree(yahoo, ask):
        return None, "blank_yahoo_vs_snkrdunk"
    if yahoo is not None:
        return yahoo, "yahoo_auctions_jp"
    return None, "empty"


def _product_image(page_html: str) -> str | None:
    """Catalog photo next to primaryMedia. Ignore the site-wide OGP logo."""
    start = (page_html or "").find("primaryMedia")
    if start < 0:
        return None
    found = _PRIMARY_IMAGE.search(page_html[start : start + 600])
    if not found:
        return None
    return found.group(0)


def _media_url(apparel: dict) -> str | None:
    media = (apparel or {}).get("primaryMedia")
    if isinstance(media, str) and media.startswith("https://cdn.snkrdunk.com/"):
        return media
    if isinstance(media, dict):
        for key in ("imageUrl", "imageURL", "url"):
            url = media.get(key)
            if isinstance(url, str) and "cdn.snkrdunk.com" in url:
                return url
    return None


def product_name_ok(item: dict, name: str) -> bool:
    """Page title is this watchlist print. EN reprints and other finishes fail."""
    if str(item.get("id") or "") == "psa10-van-gogh-pikachu":
        blob = name or ""
        low = blob.lower()
        if "ゴッホ" in blob or "grey felt hat" in low or "van gogh" in low:
            return True
    if not name or _EN_REPRINT.search(name):
        return False
    if str(item.get("kind") or "") == "sealed":
        if sealed_same(item, name):
            return True
        if not _is_box(name) or _sealed_side_product(name):
            return False
        if re.search(r"カートン|\bcase\b", name, re.I):
            return False
        multi = _MULTI_BOX.search(name)
        if multi and int(multi.group(1)) >= 2:
            return False
        return True
    return bool(same_print(item, name))


def _empty_fetch() -> dict[str, Any]:
    return {
        "ok": False,
        "apparel_id": None,
        "url": None,
        "name": None,
        "ask_jpy": None,
        "last_sale_jpy": None,
        "image_url": None,
        "error": None,
    }


def psa10_sold_prices(rows: list[dict]) -> list[int]:
    """Completed or in-flight PSA10 sales. Active asks and other grades stay out."""
    prices: list[int] = []
    for row in rows:
        if row.get("wearCount") != PSA10_WEAR or not row.get("isDisplaySold"):
            continue
        price = _pos_int(row.get("price"))
        if price is not None:
            prices.append(price)
    return prices


def psa10_last_sale_jpy(rows: list[dict]) -> int | None:
    """Robust median of the newest PSA10 sales on the filtered used feed."""
    return robust_median_jpy(psa10_sold_prices(rows)[:12])


def raw_a_sold_prices(rows: list[dict]) -> list[int]:
    """Completed condition-A sales of one copy. Lots, asks, and other grades stay out."""
    prices: list[int] = []
    for row in rows:
        if row.get("wearCount") != RAW_A_WEAR or not row.get("isDisplaySold"):
            continue
        if not single_sheet(row):
            continue
        price = _pos_int(row.get("price"))
        if price is not None:
            prices.append(price)
    return prices


def raw_a_last_sale_jpy(rows: list[dict]) -> int | None:
    """Robust median of the newest condition-A single-copy sales."""
    return robust_median_jpy(raw_a_sold_prices(rows)[:12])


def raw_a_active_ask_prices(rows: list[dict]) -> list[int]:
    """Condition-A listings still for sale, one copy only."""
    prices: list[int] = []
    for row in rows:
        if row.get("wearCount") != RAW_A_WEAR or row.get("isDisplaySold"):
            continue
        if not single_sheet(row):
            continue
        price = _pos_int(row.get("price"))
        if price is not None and price not in prices:
            prices.append(price)
    return prices


def raw_a_ask_quote(rows: list[dict], *, floor_jpy: int | None) -> dict[str, Any]:
    """Ask band for condition A. A cheaper chip price is a lot or another grade."""
    prices = raw_a_active_ask_prices(rows)
    floor = _pos_int(floor_jpy)
    if not prices or (floor is not None and floor < min(prices)):
        floor = None
    band = summarize_ask_prices(prices, floor=floor)
    return {
        "market_jpy": band["min"],
        "ask_jpy": band["min"],
        "ask_prices_jpy": band["prices"],
        "ask_min_jpy": band["min"],
        "ask_median_jpy": band["median"],
        "ask_max_jpy": band["max"],
        "error": None,
    }


def has_psa10_quote(
    rows: list[dict],
    *,
    floor_jpy: int | None,
    last_sale_jpy: int | None,
) -> bool:
    """True when the PSA10 feed, chip, or chart already has a sale or an ask."""
    if last_sale_jpy is not None or _pos_int(floor_jpy) is not None:
        return True
    return bool(psa10_active_ask_prices(rows))


def chart_last_sale_jpy(payload: dict) -> int | None:
    """Latest point on the PSA10 used sales chart. Points are ``[epoch_ms, yen]``."""
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list) or not points:
        return None
    last = points[-1]
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        return _pos_int(last[1])
    return None


def _chart_last_sale(
    apparel_id: str,
    *,
    min_interval: float,
    option_id: str = PSA10_CONDITION_IDS,
    range_key: str = "oneMonth",
) -> int | None:
    try:
        chart = polite_get(
            SALES_CHART_USED_URL.format(apparel_id=apparel_id),
            params={"salesChartOptionId": option_id, "range": range_key},
            min_interval=min_interval,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if chart.status_code != 200:
            return None
        return chart_last_sale_jpy(chart.json())
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None


def _sealed_last_sale(apparel_id: str, *, min_interval: float) -> int | None:
    try:
        hist = polite_get(
            SALES_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if hist.status_code != 200:
            return None
        return parse_sales_history(hist.json())
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return None


def relevant_list_price_hkd(item: dict) -> float | None:
    """Sell ask when present, otherwise last sold. Both are already HKD."""
    ask = item.get("hk_ask_hkd")
    if isinstance(ask, (int, float)) and not isinstance(ask, bool) and ask > 0:
        return float(ask)
    sold = item.get("price_hkd")
    if isinstance(sold, (int, float)) and not isinstance(sold, bool) and sold > 0:
        return float(sold)
    return None


def meets_min_list_price(item: dict, minimum: float) -> bool:
    """Keep a row with no quote. Drop one whose ask (else last sold) is under the floor."""
    if minimum <= 0:
        return True
    rel = relevant_list_price_hkd(item)
    if rel is None:
        return True
    return rel >= float(minimum)


def headline_under_min(tile: dict, *, fx: float, minimum: float) -> bool:
    """True when the search-tile yen converts under the HKD floor."""
    if minimum <= 0 or fx <= 0:
        return False
    raw = tile.get("tile_price_jpy")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        return False
    return float(raw) * float(fx) < float(minimum)


def _empty_quote() -> dict[str, Any]:
    return {
        "market_jpy": None,
        "ask_jpy": None,
        "ask_prices_jpy": [],
        "ask_min_jpy": None,
        "ask_median_jpy": None,
        "ask_max_jpy": None,
    }


def _psa10_used_rows(apparel_id: str, *, min_interval: float) -> list[dict]:
    try:
        return _used_rows(
            int(apparel_id),
            min_interval=min_interval,
            condition_ids=PSA10_CONDITION_IDS,
        )
    except (TypeError, ValueError):
        return []


def _raw_a_used_rows(apparel_id: str, *, min_interval: float) -> list[dict]:
    try:
        return _used_rows(
            int(apparel_id),
            min_interval=min_interval,
            condition_ids=RAW_A_CONDITION_IDS,
        )
    except (TypeError, ValueError):
        return []


def _quote_fields(item: dict, apparel_id: str, *, page_html: str, min_interval: float) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    asks = parse_condition_asks(page_html)
    image = _product_image(page_html)
    if kind == "sealed":
        last_sale = _sealed_last_sale(apparel_id, min_interval=min_interval)
        try:
            quote = build_ask_quote(
                kind="sealed",
                floor_jpy=None,
                used_rows=None,
                apparel=_apparel_json(int(apparel_id), min_interval=min_interval),
            )
        except (TypeError, ValueError, Exception):
            quote = _empty_quote()
        return {"quote": quote, "last_sale": last_sale, "image_url": image}

    ask = asks.get("PSA10")
    used_rows = _psa10_used_rows(apparel_id, min_interval=min_interval)
    last_sale = psa10_last_sale_jpy(used_rows)
    if last_sale is None:
        last_sale = _chart_last_sale(apparel_id, min_interval=min_interval)
    if has_psa10_quote(used_rows, floor_jpy=ask, last_sale_jpy=last_sale):
        try:
            quote = build_ask_quote(
                kind="psa10",
                floor_jpy=ask,
                used_rows=used_rows,
                apparel=None,
            )
        except (TypeError, ValueError, Exception):
            quote = _empty_quote()
            if isinstance(ask, int) and ask > 0:
                quote = build_ask_quote(kind="psa10", floor_jpy=ask, used_rows=[], apparel=None)
        return {"quote": quote, "last_sale": last_sale, "image_url": image}

    raw_rows = _raw_a_used_rows(apparel_id, min_interval=min_interval)
    last_sale = raw_a_last_sale_jpy(raw_rows)
    if last_sale is None:
        last_sale = _chart_last_sale(
            apparel_id,
            min_interval=min_interval,
            option_id=RAW_A_CONDITION_IDS,
            range_key="all",
        )
    quote = raw_a_ask_quote(raw_rows, floor_jpy=asks.get("A"))
    return {"quote": quote, "last_sale": last_sale, "image_url": image}


def _fetch_known_apparel(item: dict, apparel_id: str, *, min_interval: float) -> dict[str, Any]:
    """Price a catalog id we already accepted. Mismatched page title stays empty."""
    empty = _empty_fetch()
    empty["apparel_id"] = apparel_id
    empty["url"] = en_product_url(apparel_id)
    try:
        apparel = _apparel_json(int(apparel_id), min_interval=min_interval)
    except (TypeError, ValueError, Exception) as exc:
        empty["error"] = type(exc).__name__
        return empty
    local = apparel.get("localizedName")
    english = apparel.get("name")
    name = local.strip() if isinstance(local, str) and local.strip() else (
        english.strip() if isinstance(english, str) else ""
    )
    empty["name"] = name or None
    if not product_name_ok(item, name):
        empty["error"] = "identity_mismatch"
        return empty
    try:
        page = polite_get(
            APPAREL_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=25,
            headers={"Accept-Language": "ja,en;q=0.8"},
        )
    except Exception as exc:
        empty["error"] = type(exc).__name__
        return empty
    if page.status_code != 200:
        empty["error"] = f"apparel HTTP {page.status_code}"
        return empty
    packed = _quote_fields(item, apparel_id, page_html=page.text, min_interval=min_interval)
    quote = packed["quote"]
    image = packed.get("image_url") or _media_url(apparel)
    return {
        "ok": True,
        "apparel_id": apparel_id,
        "url": en_product_url(apparel_id),
        "name": name,
        "ask_jpy": quote.get("ask_jpy"),
        "ask_prices_jpy": quote.get("ask_prices_jpy") or [],
        "ask_min_jpy": quote.get("ask_min_jpy"),
        "ask_median_jpy": quote.get("ask_median_jpy"),
        "ask_max_jpy": quote.get("ask_max_jpy"),
        "market_jpy": quote.get("market_jpy"),
        "last_sale_jpy": packed.get("last_sale"),
        "image_url": image,
        "error": None,
    }


def fetch_watchlist_item(item: dict, *, min_interval: float = 1.6) -> dict[str, Any]:
    """One catalog match. Empty when the public page does not identify the SKU."""
    empty = _empty_fetch()
    if item.get("identity_review"):
        empty["error"] = "identity_review"
        return empty
    known = str(item.get("snkrdunk_apparel_id") or "").strip()
    if known.isdigit():
        return _fetch_known_apparel(item, known, min_interval=min_interval)
    chosen: dict | None = None
    last_error: str | None = None
    for query in search_queries(item):
        try:
            resp = polite_get(
                SEARCH_URL,
                params={"keywords": query},
                min_interval=min_interval,
                timeout=25,
                headers={"Accept-Language": "ja,en;q=0.8"},
            )
        except Exception as exc:
            last_error = type(exc).__name__
            continue
        if resp.status_code != 200:
            last_error = f"search HTTP {resp.status_code}"
            continue
        chosen = choose_match(parse_tiles(resp.text), item)
        if chosen:
            break
    if not chosen:
        empty["error"] = last_error or "no catalog match"
        return empty
    apparel_id = str(chosen["apparel_id"])
    try:
        page = polite_get(
            APPAREL_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=25,
            headers={"Accept-Language": "ja,en;q=0.8"},
        )
    except Exception as exc:
        empty["error"] = type(exc).__name__
        empty["apparel_id"] = apparel_id
        empty["url"] = en_product_url(apparel_id)
        empty["name"] = chosen.get("label")
        return empty
    if page.status_code != 200:
        empty["error"] = f"apparel HTTP {page.status_code}"
        empty["apparel_id"] = apparel_id
        empty["url"] = en_product_url(apparel_id)
        return empty
    packed = _quote_fields(item, apparel_id, page_html=page.text, min_interval=min_interval)
    quote = packed["quote"]
    return {
        "ok": True,
        "apparel_id": apparel_id,
        "url": en_product_url(apparel_id),
        "name": chosen.get("label"),
        "ask_jpy": quote.get("ask_jpy"),
        "ask_prices_jpy": quote.get("ask_prices_jpy") or [],
        "ask_min_jpy": quote.get("ask_min_jpy"),
        "ask_median_jpy": quote.get("ask_median_jpy"),
        "ask_max_jpy": quote.get("ask_max_jpy"),
        "market_jpy": quote.get("market_jpy"),
        "last_sale_jpy": packed.get("last_sale"),
        "image_url": packed.get("image_url") or _product_image(page.text),
        "error": None,
    }


def search_keywords(item: dict) -> list[str]:
    """Set code + number for a single. A sealed box drops 未開封 / シュリンク so search still hits."""
    if (item.get("kind") or "psa10") != "sealed":
        codes = sorted(_identity_codes(item))
        printed = _card_print(item)
        number = printed[0] if printed else ""
        code = codes[0] if codes else ""
        keyword = f"{code} {number}".strip()
        return [keyword] if keyword else []
    found: list[str] = []
    for raw in (item.get("search_jp"), item.get("name_jp")):
        cleaned = _SEALED_NOISE.sub(" ", str(raw or ""))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned not in found:
            found.append(cleaned)
    return found


def search_keyword(item: dict) -> str:
    keywords = search_keywords(item)
    return keywords[0] if keywords else ""


def bracket_print(name: str) -> tuple[str, str] | None:
    match = _BRACKET.search(name or "")
    if not match:
        return None
    return match.group(1).lower(), match.group(2)


def same_print(item: dict, name: str) -> bool:
    """The SNKRDUNK title's [set number] is this watchlist card, not an English reprint."""
    found = bracket_print(name)
    printed = _card_print(item)
    if not found or not printed:
        return False
    code, number = found
    try:
        if int(number) != int(printed[0]):
            return False
    except ValueError:
        return False
    codes = {c.lower() for c in _identity_codes(item)}
    if codes and code not in codes:
        return False
    if re.search(r"\bEN\b", name):
        return False
    card_name = re.sub(r"\([^)]*\)", " ", name)
    query = " ".join(
        str(item.get(key) or "")
        for key in ("name_jp", "name_zh", "search_jp", "search_hk")
    )
    if _stated_rarity_conflict(card_name, query):
        return False
    if _wants_illustration_rare(query) and not _is_illustration_rare(card_name):
        return False
    if _stage_conflict(card_name, query):
        return False
    return True


def sealed_same(item: dict, name: str) -> bool:
    """Catalog box title. Rejects English reprints, cases, and multi-box lots."""
    if _sealed_side_product(name) or not _is_box(name) or _non_jp(name):
        return False
    if _EN_REPRINT.search(name):
        return False
    if re.search(r"カートン|\bcase\b", name, re.I):
        return False
    multi = _MULTI_BOX.search(name)
    if multi and int(multi.group(1)) >= 2:
        return False
    query = " ".join(
        str(item.get(key) or "")
        for key in ("name_jp", "name_zh", "search_jp", "search_hk", "set")
    )
    if not _identity_aligned(query, name, number_hit=False, card_number=None):
        return False
    query_sets = {group["id"] for group in _groups_in(query) if group["id"] in _SET_IDS}
    title_sets = {group["id"] for group in _groups_in(name) if group["id"] in _SET_IDS}
    if query_sets and title_sets and not title_sets <= query_sets:
        return False
    return True


def choose_hit(item: dict, rows: list[dict]) -> dict | None:
    for row in rows:
        name = str(row.get("name") or "")
        if _SEALED_SKIP.search(name):
            continue
        if (item.get("kind") or "psa10") == "sealed":
            if sealed_same(item, name):
                return row
            continue
        if same_print(item, name):
            return row
    return None


def psa10_active_ask_prices(rows: list[dict]) -> list[int]:
    """PSA10 listings still for sale. Sold rows and other grades are not asks."""
    prices: list[int] = []
    for row in rows:
        if row.get("wearCount") != PSA10_WEAR or row.get("isDisplaySold"):
            continue
        price = _pos_int(row.get("price"))
        if price is not None:
            prices.append(price)
    return prices


def summarize_ask_prices(prices: list[int], *, floor: int | None = None) -> dict[str, Any]:
    """Min, median, and max of the ask book. ``floor`` is the page's lowest ask."""
    vals: list[int] = []
    for price in prices:
        parsed = _pos_int(price)
        if parsed is not None and parsed not in vals:
            vals.append(parsed)
    floor_i = _pos_int(floor)
    if floor_i is not None and floor_i not in vals:
        vals.append(floor_i)
    vals.sort()
    if not vals:
        return {"min": None, "median": None, "max": None, "prices": []}
    mid = robust_median([float(price) for price in vals])
    median_i = int(round(mid)) if mid is not None else vals[0]
    return {"min": vals[0], "median": median_i, "max": vals[-1], "prices": vals}


def sealed_ask_prices(apparel: dict) -> list[int]:
    """Current sealed asks. MSRP (regularPrice) is not a listing."""
    prices: list[int] = []
    for key in ("minPrice", "minPriceOfNewListing", "usedMinPrice", "maxPrice"):
        price = _pos_int((apparel or {}).get(key))
        if price is not None and price not in prices:
            prices.append(price)
    return prices


def sell_ask_jpy_points(snkr: dict | None, *, kind: str) -> list[int]:
    """Asks safe to convert into the HKD pool. Requires a catalog match (``ok``).

    A stored price list wins. Otherwise PSA10 uses the ask summaries only —
    ``market_jpy`` may be filled from sold rows. A sealed box may use ``market_jpy``,
    which is the current ``minPrice``.
    """
    snkr = snkr or {}
    if not snkr.get("ok"):
        return []
    listed = snkr.get("ask_prices_jpy")
    if isinstance(listed, list):
        points: list[int] = []
        for value in listed:
            price = _pos_int(value)
            if price is not None and price not in points:
                points.append(price)
        return points
    keys = ["ask_min_jpy", "ask_median_jpy", "ask_max_jpy", "ask_jpy"]
    if kind == "sealed":
        keys.append("market_jpy")
    points = []
    for key in keys:
        price = _pos_int(snkr.get(key))
        if price is not None and price not in points:
            points.append(price)
    return points


def build_ask_quote(
    *,
    kind: str,
    floor_jpy: int | None,
    used_rows: list[dict] | None,
    apparel: dict | None,
) -> dict[str, Any]:
    """Active-ask band. Sold PSA10 prices stay out of this quote."""
    if kind == "sealed":
        prices = sealed_ask_prices(apparel or {})
        band = summarize_ask_prices(prices)
        market = sealed_market_jpy(apparel or {})
        if market is None:
            market = band["min"]
        return {
            "market_jpy": market,
            "ask_jpy": None,
            "ask_prices_jpy": band["prices"],
            "ask_min_jpy": band["min"],
            "ask_median_jpy": band["median"],
            "ask_max_jpy": band["max"],
            "error": None,
        }
    rows = used_rows or []
    band = summarize_ask_prices(psa10_active_ask_prices(rows), floor=floor_jpy)
    market = psa10_market_jpy(rows)
    if market is None:
        market = band["min"]
    return {
        "market_jpy": market,
        "ask_jpy": band["min"],
        "ask_prices_jpy": band["prices"],
        "ask_min_jpy": band["min"],
        "ask_median_jpy": band["median"],
        "ask_max_jpy": band["max"],
        "error": None,
    }


def psa10_market_jpy(rows: list[dict]) -> int | None:
    """Median of PSA10 asks. Recent sold PSA10 fills in when fewer than two asks are up."""
    asks: list[float] = []
    sold: list[float] = []
    for row in rows:
        if row.get("wearCount") != PSA10_WEAR:
            continue
        try:
            price = int(row.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if row.get("isDisplaySold"):
            sold.append(price)
        else:
            asks.append(price)
    pool = asks if len(asks) >= 2 else [*asks, *sold]
    if len(pool) < 2:
        return None
    mid = robust_median(pool)
    if mid is None:
        return None
    return int(round(mid))


def sealed_market_jpy(apparel: dict) -> int | None:
    for key in ("minPrice", "usedMinPrice"):
        try:
            price = int(apparel.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if price > 0:
            return price
    return None


def _apparel_json(apparel_id: int, *, min_interval: float) -> dict:
    resp = polite_get(
        APPAREL_JSON_URL.format(apparel_id=apparel_id),
        headers={"Accept": "application/json", "Accept-Language": "ja"},
        min_interval=min_interval,
        timeout=25,
    )
    if resp.status_code != 200:
        return {}
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def _used_rows(
    apparel_id: int,
    *,
    min_interval: float,
    condition_ids: str | None = None,
) -> list[dict]:
    params: dict[str, str] = {"perPage": "30", "page": "1"}
    if condition_ids:
        params["conditionIds"] = condition_ids
    resp = polite_get(
        USED_URL.format(apparel_id=apparel_id),
        params=params,
        headers={"Accept": "application/json", "Accept-Language": "ja"},
        min_interval=min_interval,
        timeout=25,
    )
    if resp.status_code != 200:
        return []
    payload = resp.json()
    rows = payload.get("apparelUsedItems") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def apparel_id_from_url(url: str | None) -> str | None:
    match = re.search(r"/(\d+)\s*$", str(url or ""))
    if not match:
        return None
    return match.group(1)


def market_jpy_for_id(apparel_id: str, *, kind: str, min_interval: float) -> int | None:
    """PSA10 ask median, or the sealed box ask, for an already matched SNKRDUNK id."""
    quote = ask_quote_for_id(apparel_id, kind=kind, min_interval=min_interval)
    market = quote.get("market_jpy")
    return market if isinstance(market, int) else None


def ask_quote_for_id(apparel_id: str, *, kind: str, min_interval: float) -> dict[str, Any]:
    """Live ask band for an apparel id that already passed the catalog match."""
    empty: dict[str, Any] = {
        "market_jpy": None,
        "ask_jpy": None,
        "ask_prices_jpy": [],
        "ask_min_jpy": None,
        "ask_median_jpy": None,
        "ask_max_jpy": None,
        "error": None,
    }
    try:
        numeric = int(apparel_id)
    except (TypeError, ValueError):
        empty["error"] = "bad apparel id"
        return empty
    try:
        if kind == "sealed":
            apparel = _apparel_json(numeric, min_interval=min_interval)
            if not apparel:
                empty["error"] = "apparel empty"
                return empty
            return build_ask_quote(
                kind="sealed",
                floor_jpy=None,
                used_rows=None,
                apparel=apparel,
            )
        page_html = ""
        page = polite_get(
            APPAREL_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=25,
            headers={"Accept-Language": "ja,en;q=0.8"},
        )
        if page.status_code == 200:
            page_html = page.text
        asks = parse_condition_asks(page_html)
        floor = asks.get("PSA10")
        rows = _used_rows(
            numeric,
            min_interval=min_interval,
            condition_ids=PSA10_CONDITION_IDS,
        )
        if not has_psa10_quote(rows, floor_jpy=floor, last_sale_jpy=psa10_last_sale_jpy(rows)):
            raw_rows = _used_rows(
                numeric,
                min_interval=min_interval,
                condition_ids=RAW_A_CONDITION_IDS,
            )
            quote = raw_a_ask_quote(raw_rows, floor_jpy=asks.get("A"))
            if quote.get("ask_min_jpy") is None:
                empty["error"] = "no ask page"
                return empty
            return quote
        if floor is None and not rows:
            empty["error"] = "no ask page"
            return empty
        return build_ask_quote(
            kind="psa10",
            floor_jpy=floor,
            used_rows=rows,
            apparel=None,
        )
    except (TypeError, ValueError, Exception) as exc:
        empty["error"] = type(exc).__name__
        return empty

