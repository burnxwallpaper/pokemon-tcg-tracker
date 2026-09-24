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
from .hk_match import match_item, robust_median

JST = timezone(timedelta(hours=9))
HKT = timezone(timedelta(hours=8))
CLOSED_URL = "https://auctions.yahoo.co.jp/closedsearch/closedsearch"
AUCTION_URL = "https://auctions.yahoo.co.jp/jp/auction/{auction_id}"
# Fewer than this many title-matched comps → do not publish a sold price.
MIN_SOLD_COMPS = 3


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
    auction_id = it.get("auctionId")
    return {
        "auction_id": auction_id,
        "title": title,
        "price_jpy": price_i,
        "bid_count": it.get("bidCount"),
        "end_time": it.get("endTime"),
        "image_url": it.get("imageUrl"),
        "is_fixed": bool(it.get("isFixedPrice")),
        "url": AUCTION_URL.format(auction_id=auction_id) if auction_id else None,
    }


def _fetch_page(
    keyword: str,
    *,
    start: int,
    per_page: int,
    min_interval: float,
) -> tuple[list[dict], int, str | None, str]:
    """One closedsearch page. Returns (raw items, total, error, status)."""
    try:
        resp = polite_get(
            CLOSED_URL,
            params={
                "p": keyword,
                "b": start,
                "n": min(per_page, 100),
                "ei": "UTF-8",
                # recent end order (works for closedsearch Next.js)
                "select": "22",
            },
            headers={"Accept-Language": "ja,en;q=0.8"},
            min_interval=min_interval,
            timeout=35,
        )
        if resp.status_code != 200:
            status = "blocked" if resp.status_code in (403, 429) else "error"
            return [], 0, f"HTTP {resp.status_code}", status
        next_data = _parse_next_data(resp.text)
        if not next_data:
            return [], 0, "no __NEXT_DATA__", "parse_error"
        items, total = _extract_listing(next_data)
        return items, total, None, "ok"
    except Exception as e:  # noqa: BLE001
        return [], 0, f"{type(e).__name__}: {e}", "error"


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
    items, total, err, status = _fetch_page(
        keyword, start=1, per_page=per_page, min_interval=min_interval
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
        items, total, err, status = _fetch_page(
            keyword, start=1, per_page=min(limit, 100), min_interval=min_interval
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
        items, total, err, status = _fetch_page(
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
        med = median(prices)
        price_hkd = round(float(med) * fx, 2) if med is not None else None
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


def _match_sold_comps(comps: list[dict], item: dict) -> list[dict]:
    """PSA10 needs the grade. Sealed needs a box. Set code or card number must agree."""
    rows = [
        {
            "card_name": comp.get("title") or "",
            "price": comp.get("price_jpy"),
            "id": comp.get("auction_id"),
            "url": comp.get("url"),
            "source": "yahoo_auctions_jp",
        }
        for comp in comps
    ]
    hits = match_item(
        rows,
        item,
        apply_price_band=False,
        require_print=item.get("kind") != "sealed",
        extra_query=str(item.get("search_jp") or item.get("name_jp") or ""),
    )
    allowed = {str(hit.get("id")) for hit in hits if hit.get("id")}
    return [comp for comp in comps if str(comp.get("auction_id") or "") in allowed]


def _samples_near(comps: list[dict], median_jpy: float | None, limit: int = 3) -> list[dict]:
    if median_jpy is None:
        picked = comps[:limit]
    else:
        picked = sorted(comps, key=lambda comp: abs(int(comp["price_jpy"]) - median_jpy))[:limit]
    return [
        {
            "title": comp.get("title"),
            "price_jpy": comp.get("price_jpy"),
            "url": comp.get("url"),
        }
        for comp in picked
    ]


def publish_sold_median(prices: list[float], *, minimum: int = MIN_SOLD_COMPS) -> float | None:
    """Robust median once enough comps agree. Too few matches publish nothing."""
    if len(prices) < minimum:
        return None
    return robust_median(prices)


def fetch_watchlist_item(
    item: dict,
    *,
    min_interval: float = 1.6,
    days: int | None = None,
    max_pages: int = 8,
) -> dict[str, Any]:
    """Fetch JP sold summary for one watchlist entry."""
    kw = item.get("search_jp") or item.get("name_jp") or ""
    out = search_sold(
        kw, min_interval=min_interval, days=days, max_pages=max_pages
    )
    raw_n = len(out.get("comps") or [])
    matched = _match_sold_comps(list(out.get("comps") or []), item)
    prices = [int(comp["price_jpy"]) for comp in matched]
    mid = publish_sold_median(prices)
    now = datetime.now(JST)
    vol_24 = 0
    vol_7d = 0
    for comp in matched:
        end = _parse_end_time(comp.get("end_time"))
        if not end:
            continue
        age = now - end
        if age <= timedelta(hours=24):
            vol_24 += 1
        if age <= timedelta(days=7):
            vol_7d += 1
    out["item_id"] = item.get("id")
    out["raw_comps_n"] = raw_n
    out["matched_n"] = len(matched)
    out["comps"] = matched
    out["median_jpy"] = int(round(mid)) if mid is not None else None
    out["sold_samples"] = _samples_near(matched, mid)
    out["volume_24h"] = vol_24
    out["volume_7d_est"] = round(vol_7d / 7.0, 2) if vol_7d else 0
    fetch_error = out.get("error") if out.get("status") in ("blocked", "error", "parse_error") else None
    out["ok"] = mid is not None
    if mid is not None:
        out["status"] = "ok"
        out["error"] = None
    elif fetch_error:
        out["error"] = fetch_error
    else:
        out["status"] = "thin" if matched else "empty"
        out["error"] = None
    return out
