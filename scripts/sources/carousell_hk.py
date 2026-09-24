"""Carousell HK listingCards (title + HK$) and HKCardLink public JSON.

Carousell search HTML on a residential IP includes a listingCards JSON array.
Asks are kept only when the title matches the watchlist item. A page-wide
price scrape is not used. If Carousell is blocked, HKCardLink still runs.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from ._http import BROWSER_UA, is_cloudflare_block, polite_get
from .hk_match import match_item
from .reference_links import hkcardlink_listing_url, is_wtb

HKCARDLINK_JS = "https://hkcardlink.com/assets/index-WOdeJcRN.js"
HKCARDLINK_HOME = "https://hkcardlink.com/"
SUPABASE_BASE = "https://nhkbjdeidlavovimjueh.supabase.co"

_anon_cache: str | None = None
_js_asset_cache: str | None = None
_catalog_cache: list[dict] | None = None
_wtb_cache: list[dict] | None = None
_search_cache: dict[str, dict[str, Any]] = {}
_HKCARDLINK_LISTING_SELECT = (
    "id,card_name,price,grade_company,grade_score,status,listing_type,created_at"
)


def _parse_hkd(raw: str) -> float | None:
    m = re.search(r"([\d,]+(?:\.\d+)?)", raw or "")
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _tag_hkcardlink(row: dict) -> dict:
    tagged = dict(row)
    tagged["source"] = "hkcardlink"
    url = hkcardlink_listing_url(row.get("card_name"), row.get("id"))
    if url:
        tagged["url"] = url
    return tagged


def _sell_hits(hits: list[dict]) -> list[dict]:
    return [hit for hit in hits if not is_wtb(hit)]


def parse_listing_cards(html: str) -> list[dict]:
    """Pull title + price from the embedded listingCards array."""
    key = '"listingCards":'
    start = html.find(key)
    if start < 0:
        return []
    i = start + len(key)
    while i < len(html) and html[i] in " \n\r\t":
        i += 1
    if i >= len(html) or html[i] != "[":
        return []
    depth = 0
    in_str = False
    esc = False
    end = None
    for j in range(i, len(html)):
        ch = html[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        return []
    try:
        data = json.loads(html[i:end])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict] = []
    for card in data:
        if not isinstance(card, dict):
            continue
        title = str(card.get("title") or "").strip()
        price = _parse_hkd(str(card.get("price") or ""))
        listing_id = card.get("listingID") or card.get("id")
        if not title or price is None or listing_id in (0, "0", None, ""):
            continue
        rows.append(
            {
                "card_name": title,
                "price": price,
                "id": listing_id,
                "source": "carousell_hk",
            }
        )
    return rows


def _fetch_search_html(keyword: str, *, min_interval: float) -> dict[str, Any]:
    cached = _search_cache.get(keyword)
    if cached is not None:
        return cached
    out: dict[str, Any] = {
        "ok": False,
        "rows": [],
        "status": "ok",
        "error": None,
    }
    try:
        url = f"https://www.carousell.com.hk/search/{requests.utils.quote(keyword)}/"
        resp = polite_get(
            url,
            params={"addRecent": "false", "canChangeKeyword": "false", "sort_by": "3"},
            headers={"Accept-Language": "zh-HK,en;q=0.8"},
            min_interval=min_interval,
            timeout=25,
        )
        if is_cloudflare_block(resp) or resp.status_code == 403:
            out["status"] = "blocked"
            out["error"] = f"Cloudflare/HTTP {resp.status_code}"
        elif resp.status_code != 200:
            out["status"] = "error"
            out["error"] = f"HTTP {resp.status_code}"
        else:
            rows = parse_listing_cards(resp.text)
            out["ok"] = True
            out["rows"] = rows
            out["status"] = "ok" if rows else "empty"
            if not rows:
                out["error"] = "no listingCards parsed"
    except Exception as e:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"{type(e).__name__}: {e}"
    _search_cache[keyword] = out
    return out


def prefetch_carousell_status(*, min_interval: float = 1.6) -> dict[str, Any]:
    """Reachability only. Matching happens per watchlist item."""
    probed = _fetch_search_html("PSA10", min_interval=min_interval)
    return {
        "ok": probed.get("status") not in ("blocked", "error"),
        "status": probed.get("status"),
        "error": probed.get("error"),
        "listing_count": len(probed.get("rows") or []),
    }


def search_carousell_item(
    item: dict,
    *,
    min_interval: float,
    queries: list[str],
) -> dict[str, Any]:
    status = "empty"
    error = None
    seen: set[str] = set()
    hits: list[dict] = []
    for query in queries:
        if not query or query in seen:
            continue
        seen.add(query)
        fetched = _fetch_search_html(query, min_interval=min_interval)
        status = fetched.get("status") or status
        error = fetched.get("error")
        if fetched.get("status") == "blocked":
            break
        hits = match_item(list(fetched.get("rows") or []), item)
        if hits:
            break
    return {
        "ok": bool(hits),
        "asks_hkd": [h["price_hkd"] for h in hits],
        "listings": hits[:12],
        "error": None if hits else error,
        "status": "ok" if hits else ("blocked" if status == "blocked" else "empty"),
        "searched": len(seen),
    }


def _discover_hkcardlink_asset() -> str | None:
    global _js_asset_cache
    if _js_asset_cache:
        return _js_asset_cache
    try:
        resp = polite_get(HKCARDLINK_HOME, min_interval=1.2, timeout=20)
        m = re.search(r'src="(/assets/index-[^"]+\.js)"', resp.text)
        if m:
            _js_asset_cache = "https://hkcardlink.com" + m.group(1)
            return _js_asset_cache
    except Exception:
        pass
    return HKCARDLINK_JS


def _hkcardlink_anon_key(*, min_interval: float) -> str | None:
    global _anon_cache
    if _anon_cache:
        return _anon_cache
    asset = _discover_hkcardlink_asset() or HKCARDLINK_JS
    try:
        resp = polite_get(asset, min_interval=min_interval, timeout=35)
        keys = re.findall(
            r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
            resp.text,
        )
        if keys:
            _anon_cache = keys[0]
            return _anon_cache
    except Exception:
        return None
    return None


def fetch_hkcardlink_catalog(*, min_interval: float) -> tuple[list[dict], str | None]:
    """Pull a broad recent catalog (few queries). Cached for process lifetime."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache, None

    anon = _hkcardlink_anon_key(min_interval=min_interval)
    if not anon:
        return [], "could not load HKCardLink anon key"

    headers = {
        "User-Agent": BROWSER_UA,
        "apikey": anon,
        "Authorization": f"Bearer {anon}",
        "Accept": "application/json",
    }
    rows: list[dict] = []
    queries = [
        {
            "select": _HKCARDLINK_LISTING_SELECT,
            "or": "(card_name.ilike.%PSA 10%,card_name.ilike.%PSA10%)",
            "status": "eq.active",
            "listing_type": "neq.wtb",
            "limit": "120",
            "order": "created_at.desc",
        },
        {
            "select": _HKCARDLINK_LISTING_SELECT,
            "grade_company": "eq.PSA",
            "grade_score": "eq.10",
            "status": "eq.active",
            "listing_type": "neq.wtb",
            "limit": "120",
            "order": "created_at.desc",
        },
        {
            "select": _HKCARDLINK_LISTING_SELECT,
            "status": "eq.active",
            "under_review": "eq.false",
            "listing_type": "neq.wtb",
            "limit": "150",
            "order": "created_at.desc",
        },
        {
            "select": _HKCARDLINK_LISTING_SELECT,
            "or": "(card_name.ilike.%BOX%,card_name.ilike.%未開封%,card_name.ilike.%原盒%)",
            "status": "eq.active",
            "listing_type": "neq.wtb",
            "limit": "80",
            "order": "created_at.desc",
        },
    ]
    err = None
    for params in queries:
        try:
            resp = polite_get(
                f"{SUPABASE_BASE}/rest/v1/listings",
                params=params,
                headers=headers,
                min_interval=min_interval,
                timeout=40,
            )
            if resp.status_code != 200:
                err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                continue
            batch = resp.json()
            if isinstance(batch, list):
                rows.extend(batch)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"

    by_id: dict[str, dict] = {}
    for row in rows:
        rid = row.get("id")
        if rid and rid not in by_id:
            by_id[str(rid)] = row
    _catalog_cache = list(by_id.values())
    return _catalog_cache, err


def fetch_hkcardlink_wtb(*, min_interval: float) -> tuple[list[dict], str | None]:
    """Public HKCardLink 徵收 rows only. Cached for the process."""
    global _wtb_cache
    if _wtb_cache is not None:
        return _wtb_cache, None
    anon = _hkcardlink_anon_key(min_interval=min_interval)
    if not anon:
        return [], "could not load HKCardLink anon key"
    headers = {
        "User-Agent": BROWSER_UA,
        "apikey": anon,
        "Authorization": f"Bearer {anon}",
        "Accept": "application/json",
    }
    rows: list[dict] = []
    err = None
    for offset in (0, 200):
        try:
            resp = polite_get(
                f"{SUPABASE_BASE}/rest/v1/listings",
                params={
                    "select": _HKCARDLINK_LISTING_SELECT,
                    "listing_type": "eq.wtb",
                    "status": "eq.active",
                    "limit": "200",
                    "offset": str(offset),
                    "order": "created_at.desc",
                },
                headers=headers,
                min_interval=min_interval,
                timeout=40,
            )
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            break
        if resp.status_code != 200:
            err = f"HTTP {resp.status_code}: {resp.text[:120]}"
            break
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 200:
            break
    if err and not rows:
        return [], err
    by_id: dict[str, dict] = {}
    for row in rows:
        rid = row.get("id")
        if rid and rid not in by_id:
            by_id[str(rid)] = row
    _wtb_cache = list(by_id.values())
    return _wtb_cache, None


def search_hkcardlink_wtb(item: dict, *, min_interval: float) -> dict[str, Any]:
    catalog, err = fetch_hkcardlink_wtb(min_interval=min_interval)
    tagged = [_tag_hkcardlink(row) for row in catalog]
    hits = [hit for hit in match_item(tagged, item) if is_wtb(hit)]
    return {
        "ok": bool(hits),
        "listings": hits[:12],
        "error": None if hits else err,
        "status": "ok" if hits else ("empty" if catalog else "error"),
        "catalog_size": len(catalog),
    }


def search_hkcardlink_item(item: dict, *, min_interval: float) -> dict[str, Any]:
    catalog, err = fetch_hkcardlink_catalog(min_interval=min_interval)
    tagged = [_tag_hkcardlink(row) for row in catalog]
    hits = _sell_hits(match_item(tagged, item))
    return {
        "ok": bool(hits),
        "asks_hkd": [h["price_hkd"] for h in hits],
        "listings": hits[:12],
        "error": None if hits else err,
        "status": "ok" if hits else ("empty" if catalog else "error"),
        "catalog_size": len(catalog),
    }
