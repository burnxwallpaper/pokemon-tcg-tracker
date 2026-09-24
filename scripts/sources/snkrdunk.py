"""SNKRDUNK public catalog: identity + JP market for one watchlist card.

Search: https://snkrdunk.com/en/v1/search
Product: https://snkrdunk.com/v1/apparels/{id}
Used asks: https://snkrdunk.com/v1/apparels/{id}/used

The English search hit name carries the Japanese set and collector number
(`[SV2a 173/165]`). PSA10 asks are the used rows whose wearCount is PSA10.
That yen figure is the market check for Hong Kong sell asks.
"""
from __future__ import annotations

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

SEARCH_URL = "https://snkrdunk.com/en/v1/search"
APPAREL_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}"
USED_URL = "https://snkrdunk.com/v1/apparels/{apparel_id}/used"
PSA10_WEAR = "tradingCardSingleConditionPSA10"
_BRACKET = re.compile(
    r"\[([A-Za-z]+\d+[A-Za-z]*)\s+(\d{2,3})(?:\s*/\s*\d{2,3})?\]"
)
_SEALED_SKIP = re.compile(r"no shrink|シュリンクなし|抽選|開封済|campaign ended", re.I)
_SEALED_NOISE = re.compile(r"未開封|シュリンク付き|シュリンク|shrink", re.I)
_MULTI_BOX = re.compile(r"(?<!\d)(\d{1,2})\s*(?:box|ボックス|箱|盒)", re.I)


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
    # The parenthetical is the product ("Violet ex", "VSTAR Universe"), not the card's stage.
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
    """Catalog box title, including the English 'Scarlet & Violet … 151 Box' form."""
    if _sealed_side_product(name) or not _is_box(name) or _non_jp(name):
        return False
    if re.search(r"\bEN\b|\[EN", name, re.I):
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


def product_url(apparel_id: int, *, is_card: bool) -> str:
    if is_card:
        return f"https://snkrdunk.com/en/trading-cards/{apparel_id}"
    return f"https://snkrdunk.com/en/apparels/{apparel_id}"


def _search(keyword: str, *, min_interval: float) -> list[dict]:
    resp = polite_get(
        SEARCH_URL,
        params={"keyword": keyword, "perPage": 8, "page": 1},
        headers={"Accept": "application/json"},
        min_interval=min_interval,
        timeout=25,
    )
    if resp.status_code != 200:
        return []
    payload = resp.json()
    rows = payload.get("streetwears") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _apparel(apparel_id: int, *, min_interval: float) -> dict:
    resp = polite_get(
        APPAREL_URL.format(apparel_id=apparel_id),
        headers={"Accept": "application/json", "Accept-Language": "ja"},
        min_interval=min_interval,
        timeout=25,
    )
    if resp.status_code != 200:
        return {}
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def _used(apparel_id: int, *, min_interval: float) -> list[dict]:
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


def lookup_item(item: dict, *, min_interval: float = 1.6) -> dict[str, Any]:
    """One watchlist row → SNKRDUNK card, link, and yen market (or an empty miss)."""
    keywords = search_keywords(item)
    keyword = keywords[0] if keywords else ""
    empty: dict[str, Any] = {
        "ok": False,
        "keyword": keyword,
        "id": None,
        "name": None,
        "url": None,
        "market_jpy": None,
    }
    if not keywords:
        return empty
    hit: dict | None = None
    try:
        for keyword in keywords:
            rows = _search(keyword, min_interval=min_interval)
            hit = choose_hit(item, rows)
            if hit:
                break
    except Exception as exc:  # noqa: BLE001
        empty["error"] = f"{type(exc).__name__}: {exc}"
        empty["keyword"] = keyword
        return empty
    empty["keyword"] = keyword
    if not hit or not hit.get("id"):
        return empty
    apparel_id = int(hit["id"])
    kind = item.get("kind") or "psa10"
    try:
        apparel = _apparel(apparel_id, min_interval=min_interval)
        used_rows = _used(apparel_id, min_interval=min_interval) if kind != "sealed" else []
    except Exception as exc:  # noqa: BLE001
        empty["error"] = f"{type(exc).__name__}: {exc}"
        return empty
    info = apparel.get("apparelInfo") if isinstance(apparel.get("apparelInfo"), dict) else {}
    is_card = bool(info.get("isTradingCard")) or bool(hit.get("isTradingCard")) or kind != "sealed"
    market = sealed_market_jpy(apparel) if kind == "sealed" else psa10_market_jpy(used_rows)
    name = str(apparel.get("localizedName") or hit.get("name") or "")
    return {
        "ok": True,
        "keyword": keyword,
        "id": apparel_id,
        "name": name,
        "url": product_url(apparel_id, is_card=is_card),
        "market_jpy": market,
        "product_number": apparel.get("productNumber") or None,
    }


def collect(watchlist: list[dict], *, min_interval: float = 1.6) -> tuple[dict[str, dict], dict[str, Any]]:
    by_id: dict[str, dict] = {}
    errors: list[str] = []
    linked = 0
    for index, item in enumerate(watchlist, 1):
        print(f"  SNKRDUNK {index}/{len(watchlist)} {item.get('id')} …", flush=True)
        row = lookup_item(item, min_interval=min_interval)
        by_id[str(item.get("id"))] = row
        if row.get("ok"):
            linked += 1
        elif row.get("error"):
            errors.append(f"{item.get('id')}: {row.get('error')}")
    status = {
        "enabled": True,
        "status": "ok" if linked else "empty",
        "ok_items": linked,
        "errors": errors[:8],
        "note": "SNKRDUNK catalog identity + PSA10/BOX ask in JPY. HK asks outside 10–300% of this market are dropped.",
    }
    return by_id, status
