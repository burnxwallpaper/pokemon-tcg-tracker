"""Yahoo Auctions JP — closed/sold comps (mild HTML + __NEXT_DATA__ JSON).

PRIMARY JP reference: ended auction sold prices → price_jpy / price_hkd.
No paid Apify. ≥1.5s between requests. Graceful on failure.
Supports pagination for ~90d history backfill (Yahoo closedsearch ~120d window).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ._http import median, polite_get
from .jp_match import (
    build_queries,
    debug_from_comps,
    filter_comps,
    is_fuzzy_closedsearch,
    quote_comps,
    robust_median_jpy,
)

JST = timezone(timedelta(hours=9))
HKT = timezone(timedelta(hours=8))
CLOSED_URL = "https://auctions.yahoo.co.jp/closedsearch/closedsearch"


def _parse_next_data(html: str) -> dict | None:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_listing(next_data: dict) -> tuple[list[dict], int]:
    try:
        listing = (
            next_data["props"]["pageProps"]["initialState"]["search"]["items"]["listing"]
        )
    except (KeyError, TypeError):
        return [], 0
    items = listing.get("items") or []
    total = int(listing.get("totalResultsAvailable") or len(items) or 0)
    return items, total


def _parse_end_time(et: str | None) -> datetime | None:
    if not et:
        return None
    try:
        dt = datetime.fromisoformat(et)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
    except ValueError:
        return None


def _ended_within(item: dict, hours: float) -> bool:
    dt = _parse_end_time(item.get("endTime"))
    if not dt:
        return False
    now = datetime.now(JST)
    return (now - dt) <= timedelta(hours=hours)


def _item_to_comp(it: dict) -> dict | None:
    price = it.get("price")
    title = it.get("title") or ""
    if price is None:
        return None
    try:
        price_i = int(price)
    except (TypeError, ValueError):
        return None
    if price_i <= 0:
        return None
    return {
        "auction_id": it.get("auctionId"),
        "title": title,
        "price_jpy": price_i,
        "bid_count": it.get("bidCount"),
        "end_time": it.get("endTime"),
        "image_url": it.get("imageUrl"),
        "is_fixed": bool(it.get("isFixedPrice")),
    }


def _fetch_page(
    keyword: str,
    *,
    start: int,
    per_page: int,
    min_interval: float,
    select: str = "01",
) -> tuple[list[dict], int, str | None, str, str]:
    """One closedsearch page.

    Returns (raw items, total, error, status, wand query).
    ``select=01`` is end-time descending. ``select=22`` is start-time on
    WAND-expanded queries and must not be used for sold prices.
    """
    try:
        resp = polite_get(
            CLOSED_URL,
            params={
                "p": keyword,
                "b": start,
                "n": min(per_page, 50),
                "ei": "UTF-8",
                "select": select,
            },
            headers={"Accept-Language": "ja,en;q=0.8"},
            min_interval=min_interval,
            timeout=35,
        )
        if resp.status_code != 200:
            status = "blocked" if resp.status_code in (403, 429) else "error"
            return [], 0, f"HTTP {resp.status_code}", status, ""
        next_data = _parse_next_data(resp.text)
        if not next_data:
            return [], 0, "no __NEXT_DATA__", "parse_error", ""
        items, total = _extract_listing(next_data)
        wand = ""
        try:
            listing = next_data["props"]["pageProps"]["initialState"]["search"]["items"]["listing"]
            meta = listing.get("metadata") if isinstance(listing, dict) else None
            if isinstance(meta, dict):
                wand = str(meta.get("wandQuery") or "")
        except (KeyError, TypeError):
            wand = ""
        return items, total, None, "ok", wand
    except Exception as e:  # noqa: BLE001
        return [], 0, f"{type(e).__name__}: {e}", "error", ""


def probe_closed_count(
    keyword: str,
    *,
    min_interval: float = 1.6,
    window_days: int = 14,
    per_page: int = 20,
) -> dict[str, Any]:
    """One closedsearch page: indexed comps count + recent-window sample.

    ``total_available`` is Yahoo's ``totalResultsAvailable`` for this keyword
    (closed lots still in the index, typically about 120 days). It does not
    saturate with page size, so it is the v1 liquidity rank key.

    ``window_count`` is how many lots on this first page ended within
    ``window_days``. It caps at ``per_page`` and is only a tie-break.
    """
    items, total, err, status, _wand = _fetch_page(
        keyword,
        start=1,
        per_page=per_page,
        min_interval=min_interval,
        select="22",
    )
    now = datetime.now(JST)
    window = 0
    if not err:
        for it in items:
            dt = _parse_end_time(it.get("endTime"))
            if dt and (now - dt) <= timedelta(days=window_days):
                window += 1
    return {
        "ok": err is None and status == "ok",
        "keyword": keyword,
        "total_available": int(total or 0),
        "window_count": window,
        "sample_n": len(items),
        "error": err,
        "status": status if err else "ok",
    }


def search_sold(
    keyword: str,
    *,
    limit: int = 40,
    min_interval: float = 1.6,
    days: int | None = None,
    max_pages: int = 8,
    per_page: int = 100,
) -> dict[str, Any]:
    """Search closed auctions for keyword. Returns summary + raw comps.

    If ``days`` is set, paginate (select=22) until coverage reaches that many
    calendar days of ended auctions, ``max_pages``, or Yahoo runs out.
    Yahoo closedsearch typically retains ~120 days of ended lots.
    """
    result: dict[str, Any] = {
        "ok": False,
        "source": "yahoo_auctions_jp",
        "keyword": keyword,
        "comps": [],
        "median_jpy": None,
        "volume_24h": 0,
        "volume_7d_est": 0,
        "total_available": 0,
        "image_url": None,
        "error": None,
        "status": "ok",
        "pages_fetched": 0,
        "days_requested": days,
        "oldest_end": None,
        "newest_end": None,
    }

    cutoff = None
    if days is not None and days > 0:
        cutoff = datetime.now(HKT) - timedelta(days=days)

    # Single-page path (daily update default)
    if days is None:
        items, total, err, status, _wand = _fetch_page(
            keyword, start=1, per_page=min(limit, 50), min_interval=min_interval
        )
        result["pages_fetched"] = 1
        if err:
            result["error"] = err
            result["status"] = status
            return result
        return _finalize_search(result, items, total, limit=limit, cutoff=None)

    # Paginated history path
    seen: set[str] = set()
    all_items: list[dict] = []
    total = 0
    pages = 0
    chronological_stops = 0

    for page in range(max_pages):
        start = 1 + page * per_page
        items, total, err, status, _wand = _fetch_page(
            keyword, start=start, per_page=per_page, min_interval=min_interval
        )
        pages += 1
        result["pages_fetched"] = pages
        if err and not all_items:
            result["error"] = err
            result["status"] = status
            return result
        if err:
            # Partial success — keep what we have
            result["error"] = err
            break
        if not items:
            break

        page_ends: list[datetime] = []
        for it in items:
            aid = str(it.get("auctionId") or "")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            all_items.append(it)
            dt = _parse_end_time(it.get("endTime"))
            if dt:
                page_ends.append(dt)

        # Stop early when page is clearly past cutoff (sorted recent→old)
        if cutoff and page_ends:
            newest_on_page = max(page_ends)
            oldest_on_page = min(page_ends)
            # Heuristic: mostly chronological if span is wide and oldest < newest
            if oldest_on_page < cutoff and newest_on_page >= cutoff:
                chronological_stops += 1
                # Still keep this page (filter later); next page likely older
            if oldest_on_page < cutoff and newest_on_page < cutoff:
                chronological_stops += 1
                break

        if total and start + len(items) > total:
            break

    result["chronological_early_stop"] = chronological_stops > 0
    return _finalize_search(result, all_items, total, limit=None, cutoff=cutoff)


def _finalize_search(
    result: dict[str, Any],
    items: list[dict],
    total: int,
    *,
    limit: int | None,
    cutoff: datetime | None,
) -> dict[str, Any]:
    comps: list[dict] = []
    for it in items:
        if cutoff:
            dt = _parse_end_time(it.get("endTime"))
            if dt is None:
                continue
            if dt.astimezone(HKT) < cutoff:
                continue
        comp = _item_to_comp(it)
        if comp:
            comps.append(comp)
        if limit is not None and len(comps) >= limit:
            break

    prices = [c["price_jpy"] for c in comps]
    vol_24 = sum(1 for it in items if _ended_within(it, 24))
    vol_7d_sample = sum(1 for it in items if _ended_within(it, 24 * 7))
    daily_est = (total / 180.0) if total else (vol_7d_sample / 7.0)

    ends = [_parse_end_time(c.get("end_time")) for c in comps]
    ends_ok = [e for e in ends if e is not None]

    result.update(
        {
            "ok": bool(comps),
            "comps": comps,
            "median_jpy": int(round(median(prices))) if prices else None,
            "volume_24h": vol_24 or (1 if comps else 0),
            "volume_7d_est": round(max(daily_est, vol_7d_sample / 7.0), 2),
            "total_available": total,
            "image_url": next(
                (c["image_url"] for c in comps if c.get("image_url")), None
            ),
            "status": "ok" if comps else "empty",
            "oldest_end": min(ends_ok).isoformat() if ends_ok else None,
            "newest_end": max(ends_ok).isoformat() if ends_ok else None,
        }
    )
    return result


def comps_to_daily_history(
    comps: list[dict],
    *,
    fx: float,
    days: int = 90,
    today_hk_ask: float | None = None,
) -> list[dict]:
    """Group sold comps by Asia/Hong_Kong calendar date → daily median + volume.

    ``hk_ask_hkd`` is null historically; only today's point may carry an HK ask.
    """
    now_hkt = datetime.now(HKT)
    today = now_hkt.date().isoformat()
    cutoff_date = (now_hkt.date() - timedelta(days=days - 1)).isoformat()

    by_date: dict[str, list[int]] = defaultdict(list)
    for c in comps:
        dt = _parse_end_time(c.get("end_time"))
        if not dt:
            continue
        d = dt.astimezone(HKT).date().isoformat()
        if d < cutoff_date or d > today:
            continue
        by_date[d].append(int(c["price_jpy"]))

    history: list[dict] = []
    for d in sorted(by_date.keys()):
        prices = by_date[d]
        med = robust_median_jpy(prices)
        if med is None:
            continue
        price_hkd = round(float(med) * fx, 2)
        point = {
            "date": d,
            "price_hkd": price_hkd,
            "hk_ask_hkd": (
                round(float(today_hk_ask), 2)
                if d == today and today_hk_ask is not None
                else None
            ),
            "volume": float(len(prices)),
        }
        history.append(point)
    return history


def _empty_sold(item: dict, query: str, *, error: str | None, status: str) -> dict[str, Any]:
    return {
        "ok": False,
        "source": "yahoo_auctions_jp",
        "keyword": query,
        "query": query,
        "item_id": item.get("id"),
        "comps": [],
        "median_jpy": None,
        "volume_24h": 0,
        "volume_7d_est": 0,
        "total_available": 0,
        "image_url": None,
        "error": error,
        "status": status,
        "pages_fetched": 0,
        "days_requested": None,
        "fuzzy": status == "fuzzy",
        "jp_debug": debug_from_comps([], query=query),
    }


def fetch_watchlist_item(
    item: dict,
    *,
    min_interval: float = 1.6,
    days: int | None = None,
    max_pages: int = 8,
) -> dict[str, Any]:
    """Closedsearch sold quote for one watchlist SKU.

    Refuses WAND-expanded result sets. Title filter drops raw, other grades,
    other sets, other card numbers, and multi-box lots. Median uses the
    matched comps only; no match leaves the price empty.
    """
    queries = build_queries(item)
    if not queries:
        return _empty_sold(item, "", error="no query", status="empty")

    page_cap = max_pages if days else 3
    per_page = 50
    chosen_query = queries[0]
    raw_items: list[dict] = []
    total = 0
    pages = 0
    fuzzy = False
    last_err: str | None = None
    last_status = "empty"

    for query in queries:
        items, total, err, status, wand = _fetch_page(
            query, start=1, per_page=per_page, min_interval=min_interval
        )
        pages = 1
        chosen_query = query
        if err:
            last_err = err
            last_status = status
            if status == "blocked":
                out = _empty_sold(item, query, error=err, status="blocked")
                out["pages_fetched"] = pages
                return out
            continue
        fuzzy = is_fuzzy_closedsearch(total, wand)
        if fuzzy or not items:
            last_status = "fuzzy" if fuzzy else "empty"
            continue
        raw_items = list(items)
        last_err = None
        last_status = "ok"
        break

    if not raw_items:
        status = "fuzzy" if fuzzy and not last_err else last_status
        note = "fuzzy closedsearch refused" if status == "fuzzy" else last_err
        out = _empty_sold(item, chosen_query, error=note, status=status if status != "ok" else "empty")
        out["pages_fetched"] = pages
        out["total_available"] = total
        out["fuzzy"] = fuzzy
        return out

    while pages < page_cap:
        matched_now = filter_comps(
            [c for it in raw_items if (c := _item_to_comp(it))],
            item,
        )
        if len(matched_now) >= 3:
            break
        if total and (1 + (pages - 1) * per_page + len(raw_items)) > total and pages == 1:
            # first page already covered the index
            if len(raw_items) >= total:
                break
        if total and pages * per_page >= total:
            break
        start = 1 + pages * per_page
        more, total, err, status, wand = _fetch_page(
            chosen_query, start=start, per_page=per_page, min_interval=min_interval
        )
        pages += 1
        if err or not more or is_fuzzy_closedsearch(total, wand):
            break
        raw_items.extend(more)

    comps_all: list[dict] = []
    seen: set[str] = set()
    for it in raw_items:
        comp = _item_to_comp(it)
        if not comp:
            continue
        aid = str(comp.get("auction_id") or "")
        if aid and aid in seen:
            continue
        if aid:
            seen.add(aid)
        comps_all.append(comp)

    matched = filter_comps(comps_all, item)
    if days is not None and days > 0:
        cutoff = datetime.now(HKT) - timedelta(days=days)
        windowed: list[dict] = []
        for comp in matched:
            dt = _parse_end_time(comp.get("end_time"))
            if dt is None or dt.astimezone(HKT) < cutoff:
                continue
            windowed.append(comp)
        matched = windowed

    median_jpy, used = quote_comps(matched)
    vol_24 = 0
    vol_7 = 0
    now = datetime.now(JST)
    for comp in matched:
        dt = _parse_end_time(comp.get("end_time"))
        if not dt:
            continue
        age = now - dt
        if age <= timedelta(hours=24):
            vol_24 += 1
        if age <= timedelta(days=7):
            vol_7 += 1

    debug = debug_from_comps(used, query=chosen_query)
    return {
        "ok": median_jpy is not None,
        "source": "yahoo_auctions_jp",
        "keyword": chosen_query,
        "query": chosen_query,
        "item_id": item.get("id"),
        "comps": matched,
        "median_jpy": median_jpy,
        "volume_24h": vol_24,
        "volume_7d_est": round(vol_7 / 7.0, 2) if vol_7 else 0,
        "total_available": total,
        "image_url": None,
        "error": None,
        "status": "ok" if median_jpy is not None else "empty",
        "pages_fetched": pages,
        "days_requested": days,
        "fuzzy": False,
        "jp_debug": debug,
        "oldest_end": None,
        "newest_end": None,
    }
