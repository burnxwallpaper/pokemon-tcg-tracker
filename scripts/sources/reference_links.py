"""Public quote labels and reference URLs. No invented buy bids.

最近成交價 = price_hkd (SNKRDUNK last sale, else a close Yahoo sold, shown in HKD)
最新賣出價 = hk_ask_hkd (robust median of one HKD pool: local asks + SNKRDUNK asks × fx)
最低賣出價 = hk_ask_low_hkd (lowest price in that pool; equals the ask when only one)
買入價／徵求 = hk_bid_hkd only from HKCardLink listing_type=wtb with a positive price.
Carousell, LONO, and Zenox do not expose structured buy bids.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode

YAHOO_CLOSED = "https://auctions.yahoo.co.jp/closedsearch/closedsearch"
HKCARDLINK_HOME = "https://www.hkcardlink.com"
LONO_BY_KIND = {
    "psa10": "https://www.lono.com.hk/categories/psa-ptcg",
    "sealed": "https://www.lono.com.hk/categories/pokemon-tcg",
}
ZENOX_COLLECTION = "https://www.zenoxstore.com/collections/booster-packs-collection-box-jp"

PRICE_LABELS = {
    "price_hkd": "最近成交價",
    "hk_ask_hkd": "最新賣出價",
    "hk_ask_low_hkd": "最低賣出價",
    "hk_bid_hkd": "買入價／徵求",
}

HK_ASK_NOTE = (
    "最新賣出價係已核對賣盤的穩健中位數，池內包括本地賣盤，以及 SNKRDUNK 現時放售"
    "（日圓按 fx_jpy_to_hkd 換成港元）。最低賣出價係呢個池入面最低；只有一筆時兩者相同。"
    "對不上可靠賣盤就留空，不會估算。"
)

HK_BID_NOTE = (
    "買入價／徵求只採用 HKCardLink 公開徵收（listing_type=wtb）而且有正數預算的刊登。"
    "Carousell、LONO、Zenox 公開頁沒有結構化徵求價，對不到就保持 null，畫面顯示暫無，不會估算。"
)


def is_wtb(listing: dict) -> bool:
    return str(listing.get("listing_type") or "").strip().lower() == "wtb"


def hkcardlink_listing_url(card_name: str | None, listing_id: str | None) -> str | None:
    """Public listing path used by HKCardLink: slug(name)-first8(id)."""
    name = str(card_name or "").strip().lower()
    lid = str(listing_id or "").strip()
    if not name or not lid:
        return None
    slug_name = re.sub(r"[^a-z0-9\u4e00-\u9fff\u3400-\u4dbf]+", "-", name).strip("-")
    short = lid.replace("-", "")[:8]
    if not slug_name or len(short) < 8:
        return None
    return f"{HKCARDLINK_HOME}/listing/{quote(slug_name + '-' + short, safe='')}"


def best_bid(listings: list[dict]) -> tuple[float | None, dict | None]:
    """Highest positive HKCardLink WTB budget. Other sources are ignored."""
    best_price: float | None = None
    best_row: dict | None = None
    for listing in listings:
        if not is_wtb(listing):
            continue
        try:
            price = float(listing.get("price_hkd"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if best_price is None or price > best_price:
            best_price = price
            best_row = listing
    if best_price is None:
        return None, None
    return round(best_price, 2), best_row


def _q(text: str) -> str:
    return quote(text.strip(), safe="")


def _add(links: list[dict[str, str]], seen: set[str], label: str, href: str | None) -> None:
    if not href or href in seen:
        return
    seen.add(href)
    links.append({"label": label, "href": href})


def _listing_label(listing: dict) -> str:
    source = str(listing.get("source") or "")
    if is_wtb(listing):
        return "HKCardLink 徵求"
    if source == "hkcardlink":
        return "HKCardLink 刊登"
    if source == "carousell_hk":
        return "Carousell 刊登"
    if source == "lono":
        return "LONO"
    if source == "zenox":
        return "Zenox"
    if source == "shipmytoy":
        return "ShipMyToy"
    if source == "yahoo_auctions_jp":
        return "Yahoo 拍賣"
    return "來源刊登"


def build_reference_links(
    item: dict,
    *,
    watch: dict | None = None,
    listings: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Search URLs from the card keyword, plus a real listing URL when the scraper stored one."""
    watch = watch or {}
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    snkr_url = str(item.get("snkrdunk_url") or watch.get("snkrdunk_url") or "").strip()
    if snkr_url.startswith("https://snkrdunk.com/"):
        _add(links, seen, "SNKRDUNK", snkr_url)
    sources = set(item.get("sources") or [])
    kind = str(item.get("kind") or watch.get("kind") or "psa10")

    concrete = [row for row in (listings or []) if row.get("url")]
    concrete.sort(key=lambda row: (0 if is_wtb(row) else 1, float(row.get("price_hkd") or 0)))
    for row in concrete[:4]:
        _add(links, seen, _listing_label(row), str(row.get("url")))

    jp = str(
        item.get("jp_query")
        or watch.get("search_jp")
        or item.get("search_jp")
        or item.get("name_jp")
        or item.get("name_zh")
        or ""
    ).strip()
    hk = str(
        watch.get("search_hk") or item.get("search_hk") or item.get("name_zh") or item.get("name_jp") or ""
    ).strip()
    if jp:
        _add(
            links,
            seen,
            "Yahoo 已結束拍賣",
            f"{YAHOO_CLOSED}?{urlencode({'p': jp, 'ei': 'UTF-8'})}",
        )
    if hk:
        _add(links, seen, "Carousell 搜尋", f"https://www.carousell.com.hk/search/{_q(hk)}/")
        _add(
            links,
            seen,
            "HKCardLink 搜尋",
            f"{HKCARDLINK_HOME}/marketplace?q={_q(hk)}",
        )
        if not any(link["label"] == "HKCardLink 徵求" for link in links):
            _add(
                links,
                seen,
                "HKCardLink 徵求",
                f"{HKCARDLINK_HOME}/marketplace?mode=wtb&q={_q(hk)}",
            )
    if "lono" in sources and not any(link["label"] == "LONO" for link in links):
        _add(links, seen, "LONO", LONO_BY_KIND.get(kind, LONO_BY_KIND["sealed"]))
    if "zenox" in sources and not any(link["label"] == "Zenox" for link in links):
        _add(links, seen, "Zenox", ZENOX_COLLECTION)
    return links


def attach_public_quotes(
    item: dict,
    *,
    watch: dict | None = None,
    listings: list[dict] | None = None,
    lowest_hkd: float | None = None,
    bid_hkd: float | None = None,
) -> dict:
    """Fill hk_ask_low_hkd, hk_bid_hkd, and links. Bid stays null unless passed in."""
    if lowest_hkd is not None:
        item["hk_ask_low_hkd"] = round(float(lowest_hkd), 2)
    elif item.get("hk_listings_n") == 1 and item.get("hk_ask_hkd") is not None:
        item["hk_ask_low_hkd"] = item["hk_ask_hkd"]
    else:
        item["hk_ask_low_hkd"] = None
    item["hk_bid_hkd"] = round(float(bid_hkd), 2) if bid_hkd is not None else None
    item["links"] = build_reference_links(item, watch=watch, listings=listings)
    return item


def annotate_payload(
    payload: dict,
    watch_by_id: dict[str, dict],
    bids_by_id: dict[str, dict] | None = None,
) -> dict:
    """Patch an existing latest.json. Does not invent bids or multi-listing lows."""
    bids_by_id = bids_by_id or {}

    def touch(item: dict) -> None:
        if not isinstance(item, dict) or not item.get("id"):
            return
        watch = watch_by_id.get(item["id"]) or {}
        packed = bids_by_id.get(item["id"]) or {}
        attach_public_quotes(
            item,
            watch=watch,
            listings=packed.get("listings") or [],
            lowest_hkd=packed.get("lowest_hkd"),
            bid_hkd=packed.get("bid_hkd"),
        )

    for item in payload.get("items") or []:
        touch(item)
    sections: dict[str, Any] = payload.get("sections") or {}
    for rows in sections.values():
        if isinstance(rows, list):
            for item in rows:
                touch(item)
    meta = payload.setdefault("meta", {})
    meta["display"] = {
        "currency": "HKD",
        "primary_view": "流動性",
        "labels": PRICE_LABELS,
        "hk_ask_note": HK_ASK_NOTE,
        "hk_bid_note": HK_BID_NOTE,
    }
    return payload
