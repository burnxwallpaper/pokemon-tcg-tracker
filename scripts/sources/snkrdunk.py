"""SNKRDUNK public catalog: identity match and JP market check.

Search HTML and apparel pages are readable without a login. PSA10 slabs
expose a lowest ask per grade. Sealed products expose sales-history.
Those figures validate Yahoo sold medians. A last sale replaces Yahoo.
An ask that is far from Yahoo blanks the Yahoo figure.
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
EN_URL = "https://snkrdunk.com/en/trading-cards/{apparel_id}"
APPAREL_JSON_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}"
USED_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/used"
PSA10_WEAR = "tradingCardSingleConditionPSA10"
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
    r'href="https://snkrdunk.com/apparels/(\d+)"[^>]*aria-label="([^"]+)"'
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


def parse_sales_history(payload: dict) -> int | None:
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return None
    prices: list[int] = []
    for row in history[:12]:
        if not isinstance(row, dict):
            continue
        try:
            price = int(row.get("price"))
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
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


def fetch_watchlist_item(item: dict, *, min_interval: float = 1.6) -> dict[str, Any]:
    """One catalog match. Empty when the public page does not identify the SKU."""
    empty: dict[str, Any] = {
        "ok": False,
        "apparel_id": None,
        "url": None,
        "name": None,
        "ask_jpy": None,
        "last_sale_jpy": None,
        "image_url": None,
        "error": None,
    }
    if item.get("identity_review"):
        empty["error"] = "identity_review"
        return empty
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
    asks = parse_condition_asks(page.text)
    ask = asks.get("PSA10") if str(item.get("kind") or "") != "sealed" else None
    last_sale = None
    try:
        hist = polite_get(
            SALES_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if hist.status_code == 200:
            last_sale = parse_sales_history(hist.json())
    except (json.JSONDecodeError, Exception):
        last_sale = None
    market = None
    try:
        if str(item.get("kind") or "") == "sealed":
            market = sealed_market_jpy(
                _apparel_json(int(apparel_id), min_interval=min_interval)
            )
        else:
            market = psa10_market_jpy(
                _used_rows(int(apparel_id), min_interval=min_interval)
            )
    except (TypeError, ValueError, Exception):
        market = None
    if market is None and isinstance(ask, int) and ask > 0:
        market = ask
    return {
        "ok": True,
        "apparel_id": apparel_id,
        "url": en_product_url(apparel_id),
        "name": chosen.get("label"),
        "ask_jpy": ask,
        "market_jpy": market,
        "last_sale_jpy": last_sale,
        "image_url": _product_image(page.text),
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
    if number != printed[0]:
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


def _used_rows(apparel_id: int, *, min_interval: float) -> list[dict]:
    resp = polite_get(
        USED_URL.format(apparel_id=apparel_id),
        params={"perPage": 30, "page": 1},
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
    try:
        numeric = int(apparel_id)
    except (TypeError, ValueError):
        return None
    if kind == "sealed":
        return sealed_market_jpy(_apparel_json(numeric, min_interval=min_interval))
    return psa10_market_jpy(_used_rows(numeric, min_interval=min_interval))

