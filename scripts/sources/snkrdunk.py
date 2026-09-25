"""SNKRDUNK public catalog: identity match and JP market check.

Search HTML and apparel pages are readable without a login. PSA10 asks and
recent sales come from the used feed filtered to condition 22 (PSA10). When
that feed and the PSA10 chart are both empty, last sale and asks stay empty.
Condition A/B/C/D never fills a PSA10 card. The apparel sales-history feed is
for sealed boxes and is empty for slabs.
A last sale replaces Yahoo. An ask that is far from Yahoo blanks the Yahoo figure.
Multi-box lot sizes (2個 and up) and multi-copy lots (2枚 and up) are not this SKU.
"""
from __future__ import annotations

import html
import json
import math
import re
from datetime import datetime, timedelta, timezone
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
SALES_CHART_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/sales-chart"
EN_URL = "https://snkrdunk.com/en/trading-cards/{apparel_id}"
APPAREL_JSON_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}"
# Product-page "Hottest Items" (TradingCardDetailHottestBrandItem).
HOTTEST_BRAND_URL = "https://snkrdunk.com/en/v1/brands/{brand_id}/streetwears"
HOTTEST_HUB = "https://snkrdunk.com/en/trading-cards/704407?slide=right"
USED_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/used"
PSA10_WEAR = "tradingCardSingleConditionPSA10"
PSA10_CONDITION_IDS = "22"
HKT = timezone(timedelta(hours=8))
# Public chart ranges: all, oneWeek, oneMonth, threeMonths.
# threeMonths is the ~90-day window. A disabled range returns no points;
# all still carries the daily series, which we then cut to 90 days.
CHART_RANGE_90D = "threeMonths"
CHART_RANGE_ALL = "all"
_UNIT_COUNT = re.compile(r"(\d+)\s*(?:個|箱|ボックス|boxes|box)", re.I)
_SET_CODE = r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*"
_BRACKET = re.compile(
    rf"\[({_SET_CODE})\s+(\d{{2,3}})(?:\s*/\s*\d{{2,3}})?\]"
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
    rf"\[({_SET_CODE})\s+(\d{{2,3}})(?:\s*/\s*(\d{{2,3}}))?\]"
)
_JP_SCRIPT = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_NO_SHRINK = re.compile(r"シュリンクなし|シュリンク無|no\s*shrink", re.I)
_OPENED = re.compile(r"開封済|開封済み|\bopened\b", re.I)
_DECK_SET = re.compile(r"構築デッキ|プレミアムデッキ|deck\s*set|constructed\s*deck", re.I)
_REL_SALE = re.compile(r"(\d+)\s*(分|時間|日|週間|週|か月|ヶ月|ヵ月)")
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
    """A loose pack, not a box or deck that happens to say 拡張パック / Expansion Pack."""
    folded = label.lower()
    is_pack = "パック" in label or bool(re.search(r"\bpacks?\b", folded))
    if not is_pack:
        return False
    if "ボックス" in label or "デッキ" in label or "box" in folded or "deck" in folded:
        return False
    return True


def _is_pokemon(label: str) -> bool:
    return bool(re.search(r"ポケモン|pokemon|pokémon", label, re.I))


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
    """Hottest hit we track. None drops jewelry, EN, packs, no-shrink, and opened stock."""
    label = str(tile.get("label") or "")
    if not label or _CATALOG_SKIP.search(label) or _EN_REPRINT.search(label):
        return None
    if _NO_SHRINK.search(label) or _OPENED.search(label):
        return None
    if str(tile.get("set_code") or "") and str(tile.get("number") or ""):
        return "psa10"
    if not _is_pokemon(label) or _pack_only(label):
        return None
    if re.search(r"カートン|\bcase\b", label, re.I):
        return None
    multi = _MULTI_BOX.search(label)
    if multi and int(multi.group(1)) >= 2:
        return None
    if _is_box(label) or _DECK_SET.search(label):
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


def _tile_from_parts(apparel_id: str, label: str, *, price_jpy: int | None = None, price_hkd: int | None = None) -> dict[str, Any]:
    number = _CARD_NO.search(label)
    return {
        "apparel_id": str(apparel_id),
        "label": label,
        "tile_price_jpy": price_jpy,
        "tile_price_hkd": price_hkd,
        "set_code": number.group(1) if number else None,
        "number": number.group(2) if number else None,
        "denom": number.group(3) if number else None,
    }


def tile_from_hottest_row(row: dict) -> dict[str, Any] | None:
    """One Hottest Items row. ``minPrice`` on the EN brand API is already HKD."""
    if not isinstance(row, dict) or row.get("id") is None:
        return None
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    price = row.get("minPrice")
    price_hkd = None
    if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
        price_hkd = int(price)
    return _tile_from_parts(str(row["id"]), name, price_hkd=price_hkd)


def collect_brand_hottest(
    *,
    pages: int,
    min_interval: float,
    per_page: int = 48,
    brand_id: str = "pokemon",
) -> list[dict]:
    """Product-page Hottest Items, first page first, one row per apparel id.

    The EN widget loads ``/en/v1/brands/{brand}/streetwears?department=tradingCard``.
    """
    seen: set[str] = set()
    tiles: list[dict] = []
    for page in range(1, max(1, pages) + 1):
        try:
            resp = polite_get(
                HOTTEST_BRAND_URL.format(brand_id=brand_id),
                params={
                    "perPage": str(max(1, per_page)),
                    "page": str(page),
                    "department": "tradingCard",
                },
                min_interval=min_interval,
                timeout=25,
                headers={"Accept": "application/json", "Accept-Language": "en"},
            )
        except Exception:
            break
        if resp.status_code != 200:
            break
        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError):
            break
        rows = payload.get("streetwears") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        fresh = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            tile = tile_from_hottest_row(row)
            if tile is None:
                continue
            apparel_id = str(tile["apparel_id"])
            if apparel_id in seen:
                continue
            seen.add(apparel_id)
            tiles.append(tile)
            fresh += 1
        if fresh == 0 or len(rows) < per_page:
            break
    return tiles


def collect_brand_search_labels(
    *,
    pages: int,
    min_interval: float,
    brand_id: str = "pokemon",
) -> dict[str, dict]:
    """Japanese titles from the brand hottest search, keyed by apparel id."""
    index: dict[str, dict] = {}
    for page in range(1, max(1, pages) + 1):
        try:
            resp = polite_get(
                SEARCH_URL,
                params={"brandIds": brand_id, "sort": "hottest", "page": str(page)},
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
            if not apparel_id or apparel_id in index:
                continue
            index[apparel_id] = tile
            fresh += 1
        if fresh == 0:
            break
    return index


def _apply_japanese_label(tile: dict, jp: dict) -> None:
    label = str(jp.get("label") or "").strip()
    if not label or not _JP_SCRIPT.search(label):
        return
    parsed = _tile_from_parts(
        str(tile.get("apparel_id") or jp.get("apparel_id") or ""),
        label,
        price_jpy=tile.get("tile_price_jpy") if isinstance(tile.get("tile_price_jpy"), int) else None,
        price_hkd=tile.get("tile_price_hkd") if isinstance(tile.get("tile_price_hkd"), int) else None,
    )
    tile["label"] = parsed["label"]
    for key in ("set_code", "number", "denom"):
        if parsed.get(key):
            tile[key] = parsed[key]


def _localize_from_apparel(tile: dict, *, min_interval: float) -> None:
    if _JP_SCRIPT.search(str(tile.get("label") or "")):
        return
    try:
        apparel_id = int(tile.get("apparel_id") or 0)
    except (TypeError, ValueError):
        return
    if apparel_id <= 0:
        return
    try:
        apparel = _apparel_json(apparel_id, min_interval=min_interval)
    except Exception:
        return
    local = apparel.get("localizedName")
    if not isinstance(local, str) or not local.strip():
        return
    _apply_japanese_label(tile, {"label": local.strip(), "apparel_id": str(apparel_id)})


def prepare_brand_hottest(
    tiles: list[dict],
    jp_by_id: dict[str, dict],
    *,
    fx: float,
    minimum: float,
    min_interval: float,
    localize_cap: int,
) -> tuple[list[dict], int]:
    """Keep Hottest Items that clear the HKD floor and catalog rules.

    Japanese search titles fill names first. Apparel JSON fills the rest, up to
    ``localize_cap``, so the head of the section is not left in English.
    """
    kept: list[dict] = []
    localized = 0
    for tile in tiles:
        aid = str(tile.get("apparel_id") or "")
        jp = jp_by_id.get(aid)
        if jp:
            _apply_japanese_label(tile, jp)
        if headline_under_min(tile, fx=fx, minimum=minimum):
            continue
        if not _JP_SCRIPT.search(str(tile.get("label") or "")) and localized < localize_cap:
            _localize_from_apparel(tile, min_interval=min_interval)
            localized += 1
        if headline_under_min(tile, fx=fx, minimum=minimum):
            continue
        if catalog_kind(tile) is None:
            continue
        kept.append(tile)
    return kept, localized


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
        if sealed_same(item, name) or _tracked_deck_set(item, name):
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


def psa10_quote_present(snkr: dict | None) -> bool:
    """True when a fetched book already has a PSA10 sale or a PSA10 ask."""
    book = snkr or {}
    if _pos_int(book.get("last_sale_jpy")) is not None:
        return True
    if _pos_int(book.get("ask_jpy")) is not None:
        return True
    if _pos_int(book.get("market_jpy")) is not None:
        return True
    listed = book.get("ask_prices_jpy")
    if isinstance(listed, list):
        return any(_pos_int(price) is not None for price in listed)
    return False


def read_psa10_market(apparel_id: str, *, min_interval: float) -> bool | None:
    """True when this catalog id has a PSA10 last sale or a PSA10 ask.

    None when the product page cannot be read. Does not use condition A.
    """
    try:
        page = polite_get(
            APPAREL_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=25,
            headers={"Accept-Language": "ja,en;q=0.8"},
        )
    except Exception:
        return None
    if page.status_code != 200:
        return None
    try:
        asks = parse_condition_asks(page.text)
        rows = _psa10_used_rows(apparel_id, min_interval=min_interval)
        last_sale = psa10_last_sale_jpy(rows)
        if last_sale is None:
            last_sale = _chart_last_sale(apparel_id, min_interval=min_interval)
        return has_psa10_quote(rows, floor_jpy=asks.get("PSA10"), last_sale_jpy=last_sale)
    except Exception:
        return None


def chart_last_sale_jpy(payload: dict) -> int | None:
    """Latest point on the PSA10 used sales chart. Points are ``[epoch_ms, yen]``."""
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list) or not points:
        return None
    last = points[-1]
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        return _pos_int(last[1])
    return None


def parse_chart_points(payload: dict) -> list[tuple[int, int]]:
    """Chart rows as ``(epoch_ms, yen)``. Non-positive prices are dropped."""
    raw = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    points: list[tuple[int, int]] = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        epoch = row[0]
        yen = _pos_int(row[1])
        if yen is None or isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
            continue
        points.append((int(epoch), yen))
    return points


def chart_range_enabled(payload: dict, key: str) -> bool | None:
    """True/False from ``rangeKeys``. None when the payload has no such key."""
    keys = payload.get("rangeKeys") if isinstance(payload, dict) else None
    if not isinstance(keys, list):
        return None
    for row in keys:
        if not isinstance(row, dict) or row.get("key") != key:
            continue
        enabled = row.get("enabled")
        if isinstance(enabled, bool):
            return enabled
    return None


def single_unit_option_id(payload: dict) -> str | None:
    """Sealed chart option for a single box (``1個``). Multi-box sizes stay out."""
    options = payload.get("salesChartOption") if isinstance(payload, dict) else None
    if not isinstance(options, list):
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("localizedName") or "") != "1個":
            continue
        oid = opt.get("id")
        if isinstance(oid, bool) or not isinstance(oid, int):
            continue
        return str(oid)
    return None


def _point_date(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, HKT).date().isoformat()


def filter_points_to_window(
    points: list[tuple[int, int]],
    *,
    days: int,
    now: datetime,
) -> list[tuple[int, int]]:
    """Keep points whose HKT calendar date falls in the last ``days`` days."""
    today = now.astimezone(HKT).date()
    span = max(int(days), 1)
    cutoff = (today - timedelta(days=span - 1)).isoformat()
    today_s = today.isoformat()
    kept: list[tuple[int, int]] = []
    for epoch_ms, yen in points:
        if yen <= 0:
            continue
        day = _point_date(epoch_ms)
        if cutoff <= day <= today_s:
            kept.append((epoch_ms, yen))
    return kept


def choose_90d_points(
    three_month_points: list[tuple[int, int]],
    all_points: list[tuple[int, int]],
    *,
    days: int,
    now: datetime,
) -> list[tuple[int, int]]:
    """Prefer the threeMonths series. If it is empty, use ``all`` inside the window."""
    windowed = filter_points_to_window(three_month_points, days=days, now=now)
    if windowed:
        return windowed
    return filter_points_to_window(all_points, days=days, now=now)


def bucket_chart_points(
    points: list[tuple[int, int]],
    *,
    fx: float,
    days: int = 90,
    now: datetime | None = None,
) -> list[dict]:
    """Group ``[epoch_ms, yen]`` into HKT days.

    Price is the robust median (one point that day means last and median match).
    Volume is how many chart points landed that day. The 3-month and all-range
    charts publish one price per day, so that volume is usually 1.
    """
    now_dt = now or datetime.now(HKT)
    kept = filter_points_to_window(points, days=days, now=now_dt)
    by_date: dict[str, list[int]] = {}
    for epoch_ms, yen in kept:
        by_date.setdefault(_point_date(epoch_ms), []).append(yen)
    history: list[dict] = []
    for day in sorted(by_date):
        med = robust_median_jpy(by_date[day])
        if med is None:
            continue
        history.append({
            "date": day,
            "price_hkd": round(float(med) * float(fx), 2),
            "hk_ask_hkd": None,
            "volume": float(len(by_date[day])),
        })
    return history


def relative_sale_datetime(label: str, *, now: datetime) -> datetime | None:
    """Turn a SNKRDUNK relative sale label (``4分前``, ``2日前``) into an instant."""
    text = str(label or "").strip()
    if not text:
        return None
    base = now.astimezone(HKT)
    if "今日" in text:
        return base
    if "昨日" in text:
        return base - timedelta(days=1)
    match = _REL_SALE.search(text)
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2)
    if unit == "分":
        return base - timedelta(minutes=count)
    if unit == "時間":
        return base - timedelta(hours=count)
    if unit == "日":
        return base - timedelta(days=count)
    if unit in ("週間", "週"):
        return base - timedelta(days=count * 7)
    if unit in ("か月", "ヶ月", "ヵ月"):
        return base - timedelta(days=count * 30)
    return None


def sales_history_chart_points(payload: dict, *, now: datetime) -> list[tuple[int, int]]:
    """Single-SKU sales-history rows as chart points. Multi-box lots are skipped."""
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return []
    points: list[tuple[int, int]] = []
    for row in history:
        if not isinstance(row, dict) or not single_sku_sale(row):
            continue
        yen = _pos_int(row.get("price"))
        if yen is None:
            continue
        stamped = relative_sale_datetime(str(row.get("date") or ""), now=now)
        if stamped is None:
            continue
        points.append((int(stamped.timestamp() * 1000), yen))
    return points


def _fetch_chart_payload(
    url: str,
    *,
    range_key: str,
    option_id: str | None,
    min_interval: float,
) -> dict:
    params: dict[str, str] = {"range": range_key}
    if option_id:
        params["salesChartOptionId"] = option_id
    try:
        resp = polite_get(
            url,
            params=params,
            min_interval=min_interval,
            timeout=25,
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return {}
        payload = resp.json()
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_psa10_90d_points(
    apparel_id: str,
    *,
    min_interval: float,
    days: int = 90,
    now: datetime | None = None,
) -> list[tuple[int, int]]:
    """PSA10 used sales-chart points for the 90-day window. Option 22 only."""
    now_dt = now or datetime.now(HKT)
    url = SALES_CHART_USED_URL.format(apparel_id=apparel_id)
    three = parse_chart_points(
        _fetch_chart_payload(
            url,
            range_key=CHART_RANGE_90D,
            option_id=PSA10_CONDITION_IDS,
            min_interval=min_interval,
        )
    )
    chosen = choose_90d_points(three, [], days=days, now=now_dt)
    if chosen:
        return chosen
    all_pts = parse_chart_points(
        _fetch_chart_payload(
            url,
            range_key=CHART_RANGE_ALL,
            option_id=PSA10_CONDITION_IDS,
            min_interval=min_interval,
        )
    )
    return choose_90d_points([], all_pts, days=days, now=now_dt)


def fetch_sealed_90d_points(
    apparel_id: str,
    *,
    min_interval: float,
    days: int = 90,
    now: datetime | None = None,
) -> list[tuple[int, int]]:
    """New-product sales chart for ``1個``. Sales-history dates if that chart is empty."""
    now_dt = now or datetime.now(HKT)
    url = SALES_CHART_URL.format(apparel_id=apparel_id)
    probe = _fetch_chart_payload(
        url,
        range_key=CHART_RANGE_90D,
        option_id=None,
        min_interval=min_interval,
    )
    option_id = single_unit_option_id(probe)
    if option_id:
        range_key = CHART_RANGE_90D
        if chart_range_enabled(probe, CHART_RANGE_90D) is False:
            range_key = CHART_RANGE_ALL
        primary = parse_chart_points(
            _fetch_chart_payload(
                url,
                range_key=range_key,
                option_id=option_id,
                min_interval=min_interval,
            )
        )
        chosen = choose_90d_points(primary, [], days=days, now=now_dt)
        if not chosen and range_key != CHART_RANGE_ALL:
            all_pts = parse_chart_points(
                _fetch_chart_payload(
                    url,
                    range_key=CHART_RANGE_ALL,
                    option_id=option_id,
                    min_interval=min_interval,
                )
            )
            chosen = choose_90d_points([], all_pts, days=days, now=now_dt)
        if chosen:
            return chosen
    hist = sales_history_chart_points(
        _sales_payload(apparel_id, min_interval=min_interval),
        now=now_dt,
    )
    return filter_points_to_window(hist, days=days, now=now_dt)


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


def _sales_payload(apparel_id: str, *, min_interval: float) -> dict:
    try:
        hist = polite_get(
            SALES_URL.format(apparel_id=apparel_id),
            min_interval=min_interval,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if hist.status_code != 200:
            return {}
        payload = hist.json()
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sealed_last_sale(apparel_id: str, *, min_interval: float) -> int | None:
    return parse_sales_history(_sales_payload(apparel_id, min_interval=min_interval))


def sale_within_days(label: str, *, days: int = 7) -> bool:
    """True for a SNKRDUNK relative sale date inside ``days`` (分前 / N日前)."""
    text = str(label or "").strip()
    if not text:
        return False
    if "今日" in text or "昨日" in text:
        return True
    match = _REL_SALE.search(text)
    if not match:
        return False
    count = int(match.group(1))
    unit = match.group(2)
    if unit in ("分", "時間"):
        return True
    if unit == "日":
        return count <= days
    if unit in ("週間", "週"):
        return count * 7 <= days
    return False


def recent_history_count(payload: dict, *, days: int = 7) -> int:
    """Sealed sales-history rows whose relative date is inside the window."""
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return 0
    sold = 0
    for row in history:
        if not isinstance(row, dict) or not single_sku_sale(row):
            continue
        if sale_within_days(str(row.get("date") or ""), days=days):
            sold += 1
    return sold


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recent_used_sold_count(rows: list[dict], *, wear: str, days: int = 7) -> int:
    """Sold rows on the used feed whose update time is inside the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sold = 0
    for row in rows:
        if row.get("wearCount") != wear or not row.get("isDisplaySold"):
            continue
        stamped = _parse_iso(row.get("updatedAt")) or _parse_iso(row.get("createdAt"))
        if stamped is not None and stamped >= cutoff:
            sold += 1
    return sold


def _week_sold_count(apparel_id: str, *, min_interval: float, option_id: str) -> int:
    """Points on the one-week used sales chart for one condition."""
    try:
        chart = polite_get(
            SALES_CHART_USED_URL.format(apparel_id=apparel_id),
            params={"salesChartOptionId": option_id, "range": "oneWeek"},
            min_interval=min_interval,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if chart.status_code != 200:
            return 0
        payload = chart.json()
    except (json.JSONDecodeError, TypeError, ValueError, Exception):
        return 0
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list):
        return 0
    return sum(
        1
        for point in points
        if isinstance(point, (list, tuple)) and len(point) >= 2 and _pos_int(point[1])
    )


def _count_field(data: dict, key: str) -> int:
    raw = data.get(key)
    if isinstance(raw, str):
        cleaned = raw.replace("+", "").replace(",", "").strip()
        if cleaned.isdigit():
            return int(cleaned)
        return 0
    parsed = _pos_int(raw)
    return parsed if parsed is not None else 0


def sell_listing_count(apparel: dict | None, *, kind: str) -> int:
    """Current SNKRDUNK sell listings. Slabs use used listings; boxes use new listings."""
    data = apparel or {}
    if kind == "sealed":
        return _count_field(data, "listingCount") or _count_field(data, "totalListingCount")
    return _count_field(data, "usedListingCount") or _count_field(data, "totalListingCount")


# Points on each side of liquidity_score. Caps are the inputs that fill that side.
# log1p keeps the score absolute (same counts → same score tomorrow) and stops
# a Hottest-heavy list from stacking on 99. A within-list percentile would
# force a spread every day, but then 80 would not mean the same book depth.
LIQUIDITY_SOLD_POINTS = 60.0
LIQUIDITY_LIST_POINTS = 39.0
LIQUIDITY_SOLD_CAP = 80.0
LIQUIDITY_LIST_CAP = 800.0


def _liquidity_side(value: float, cap: float, points: float) -> float:
    """Diminishing points. ``cap`` fills the side; larger inputs stay at ``points``."""
    if value <= 0 or cap <= 0:
        return 0.0
    return points * min(1.0, math.log1p(value) / math.log1p(cap))


def liquidity_score(recent_sold: float, listing_count: int, *, yahoo_vol: float = 0) -> int:
    """0–99 from recent sold activity and the current sell-listing count.

    ``recent_sold`` is SNKRDUNK sales over about 7 days. ``yahoo_vol`` (today
    plus the 7-day average) is used only when that count is 0. ``listing_count``
    is the live SNKRDUNK seller book (used listings for a slab, new listings
    for a sealed box).

    Sold side is ``60 * log1p(sales) / log1p(80)``. Book side is
    ``39 * log1p(listings) / log1p(800)``. About 80 sales or about 800 listings
    fill that side. 15 sales and a few hundred listings land in the mid range;
    99 needs both a deep sale week and a deep book.
    """
    sold = float(recent_sold or 0)
    if sold <= 0:
        sold = float(yahoo_vol or 0)
    sold_pts = _liquidity_side(sold, LIQUIDITY_SOLD_CAP, LIQUIDITY_SOLD_POINTS)
    list_pts = _liquidity_side(float(listing_count or 0), LIQUIDITY_LIST_CAP, LIQUIDITY_LIST_POINTS)
    if sold_pts <= 0 and list_pts <= 0:
        return 1
    return int(max(1, min(99, round(sold_pts + list_pts))))


def _load_apparel(apparel_id: str, apparel: dict | None, *, min_interval: float) -> dict:
    if isinstance(apparel, dict) and apparel.get("id"):
        return apparel
    try:
        loaded = _apparel_json(int(apparel_id), min_interval=min_interval)
    except (TypeError, ValueError, Exception):
        return {}
    return loaded if isinstance(loaded, dict) else {}


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
    """True when the tile price converts under the HKD floor.

    ``tile_price_hkd`` is already HKD (Hottest Items brand API).
    ``tile_price_jpy`` is yen from search HTML.
    """
    if minimum <= 0:
        return False
    hkd = tile.get("tile_price_hkd")
    if isinstance(hkd, (int, float)) and not isinstance(hkd, bool) and hkd > 0:
        return float(hkd) < float(minimum)
    if fx <= 0:
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


def _activity_fields(
    *,
    recent_sold_n: int,
    apparel: dict,
    kind: str,
    ask_fallback: int = 0,
) -> dict[str, int]:
    listings = sell_listing_count(apparel, kind="sealed" if kind == "sealed" else "psa10")
    if listings <= 0 and ask_fallback > 0:
        listings = ask_fallback
    return {"recent_sold_n": max(0, int(recent_sold_n)), "listing_count": listings}


def _quote_fields(
    item: dict,
    apparel_id: str,
    *,
    page_html: str,
    min_interval: float,
    apparel: dict | None = None,
) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    asks = parse_condition_asks(page_html)
    image = _product_image(page_html)
    loaded = _load_apparel(apparel_id, apparel, min_interval=min_interval)
    if kind == "sealed":
        payload = _sales_payload(apparel_id, min_interval=min_interval)
        last_sale = parse_sales_history(payload)
        try:
            quote = build_ask_quote(
                kind="sealed",
                floor_jpy=None,
                used_rows=None,
                apparel=loaded,
            )
        except (TypeError, ValueError, Exception):
            quote = _empty_quote()
        return {
            "quote": quote,
            "last_sale": last_sale,
            "image_url": image,
            **_activity_fields(
                recent_sold_n=recent_history_count(payload),
                apparel=loaded,
                kind="sealed",
                ask_fallback=len(quote.get("ask_prices_jpy") or []),
            ),
        }

    ask = asks.get("PSA10")
    used_rows = _psa10_used_rows(apparel_id, min_interval=min_interval)
    last_sale = psa10_last_sale_jpy(used_rows)
    if last_sale is None:
        last_sale = _chart_last_sale(apparel_id, min_interval=min_interval)
    week_sold = _week_sold_count(
        apparel_id, min_interval=min_interval, option_id=PSA10_CONDITION_IDS
    )
    if week_sold <= 0:
        week_sold = recent_used_sold_count(used_rows, wear=PSA10_WEAR)
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
        return {
            "quote": quote,
            "last_sale": last_sale,
            "psa10_market": True,
            "image_url": image,
            **_activity_fields(
                recent_sold_n=week_sold,
                apparel=loaded,
                kind="psa10",
                ask_fallback=len(psa10_active_ask_prices(used_rows)),
            ),
        }

    return {
        "quote": _empty_quote(),
        "last_sale": None,
        "psa10_market": False,
        "image_url": image,
        **_activity_fields(
            recent_sold_n=week_sold,
            apparel=loaded,
            kind="psa10",
            ask_fallback=0,
        ),
    }


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
    packed = _quote_fields(
        item, apparel_id, page_html=page.text, min_interval=min_interval, apparel=apparel
    )
    quote = packed["quote"]
    image = packed.get("image_url") or _media_url(apparel)
    fetched = {
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
        "recent_sold_n": packed.get("recent_sold_n") or 0,
        "listing_count": packed.get("listing_count") or 0,
        "image_url": image,
        "error": None,
    }
    if isinstance(packed.get("psa10_market"), bool):
        fetched["psa10_market"] = packed["psa10_market"]
    return fetched


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
    fetched = {
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
        "recent_sold_n": packed.get("recent_sold_n") or 0,
        "listing_count": packed.get("listing_count") or 0,
        "image_url": packed.get("image_url") or _product_image(page.text),
        "error": None,
    }
    if isinstance(packed.get("psa10_market"), bool):
        fetched["psa10_market"] = packed["psa10_market"]
    return fetched


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


def _catalog_bracket(item: dict) -> tuple[str, str] | None:
    """Bracket printed on the watchlist title. Keeps S8a-P / S8a-G, which set-code scan truncates to S8a."""
    blob = " ".join(
        str(item.get(key) or "")
        for key in ("name_jp", "name_zh", "search_jp", "search_hk")
    )
    return bracket_print(blob)


def _tracked_deck_set(item: dict, name: str) -> bool:
    """A deck set already chosen for the watchlist. Booster-box asks still reject decks."""
    blob = " ".join(
        str(item.get(key) or "")
        for key in ("name_jp", "name_zh", "search_jp", "search_hk")
    )
    if not _DECK_SET.search(blob) or not _DECK_SET.search(name or ""):
        return False
    if _EN_REPRINT.search(name) or _NO_SHRINK.search(name) or _OPENED.search(name):
        return False
    if re.search(r"カートン|\bcase\b", name, re.I):
        return False
    return True


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
    named = _catalog_bracket(item)
    if named:
        if code != named[0].lower():
            return False
    else:
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
            empty["error"] = "no psa10 quote"
            return empty
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

