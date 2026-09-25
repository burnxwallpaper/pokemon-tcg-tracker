#!/usr/bin/env python3
"""
update.py — Pokémon TCG price tracker (REAL mild scrapers)

Pipeline:
  1. fetch   — Yahoo Auctions JP sold + title-matched HK asks
  2. merge   — attach JP/HK prices onto watchlist items
  3. compute — 1日/7日 movers, liquidity, JP↔HK spreads (from history)
  4. write   — data/latest.json + data/history/YYYY-MM-DD.json
               + data/history/series/{id}.json (~90 daily points)

最近成交價 → price_hkd (SNKRDUNK last sale when public, else Yahoo JP sold if it agrees with the SNKRDUNK ask). Shown in HKD.
最新賣出價 → hk_ask_hkd (median of one HKD pool: matched local asks plus SNKRDUNK active asks × fx).
最低賣出價 → hk_ask_low_hkd. 買入價／徵求 → hk_bid_hkd (HKCardLink WTB only; else null).
Mild: ≥1–2s between requests, browser UA, graceful failures.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from sources import hk_asks, snkrdunk, yahoo_auctions_jp  # noqa: E402
from sources.hk_match import unified_sell_asks  # noqa: E402
from sources.reference_links import attach_public_quotes  # noqa: E402
from sources.yahoo_auctions_jp import comps_to_daily_history  # noqa: E402
from zh_names import stamp_display_name  # noqa: E402
from series_io import (  # noqa: E402
    load_series_points,
    merge_history_by_date,
    write_catalog,
    write_series_merged,
)

CONFIG_PATH = ROOT / "config.json"
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_DIR = ROOT / "data" / "history"
SERIES_DIR = HISTORY_DIR / "series"
IMAGES_DIR = ROOT / "data" / "images"

HK_TZ = timezone(timedelta(hours=8))


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def hkd(jpy: float | int | None, fx: float) -> float | None:
    if jpy is None:
        return None
    return round(float(jpy) * fx, 2)


def _listing_prices_hkd(rows: list) -> list[float]:
    prices: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            price = float(row.get("price_hkd"))
        except (TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)
    return prices


def _summary_prices_hkd(*values: object) -> list[float]:
    """Preserved median/low when the listing rows were not stored."""
    prices: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value > 0 and float(value) not in prices:
            prices.append(float(value))
    return prices


def load_series(item_id: str) -> list[dict]:
    """Prior real points from series/{id}.json (sample-only series ignored)."""
    return load_series_points(item_id)


def pct_change(curr: float | None, prev: float | None) -> float:
    if curr is None or prev is None or prev == 0:
        return 0.0
    return round((curr - prev) / prev * 100.0, 2)


def price_on_or_before(history: list[dict], target_date: str, field: str = "price_hkd") -> float | None:
    """Last known value on or before target_date."""
    val = None
    for p in history:
        d = p.get("date")
        if not d or d > target_date:
            break
        if p.get(field) is not None:
            val = float(p[field])
    return val


def avg_volume(history: list[dict], days: int = 7) -> float:
    if not history:
        return 0.0
    tail = history[-days:]
    vols = [float(p.get("volume") or 0) for p in tail]
    return round(sum(vols) / len(vols), 2) if vols else 0.0


def liquidity_score(vol_today: float, vol_7d: float, total_available: int, *, recent_sold: float = 0, listing_count: int = 0) -> int:
    """0–99 from SNKRDUNK recent sales and live sell listings.

    ``total_available`` is unused. Yahoo volume is only the fallback when
    ``recent_sold`` is 0. See ``snkrdunk.liquidity_score``.
    """
    del total_available
    yahoo_vol = float(vol_today or 0) + float(vol_7d or 0)
    return snkrdunk.liquidity_score(recent_sold, listing_count, yahoo_vol=yahoo_vol)


def download_image(url: str | None, item_id: str) -> str | None:
    """Download official art into data/images/; returns relative path.

    Never used for Yahoo/Mercari listing photos — only config image_official_url
    (TCGdex card faces / pokemon-card.com product art / set logos).
    """
    if not url:
        return None
    from sources._http import BROWSER_UA

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path_part = urlparse(url).path.lower()
    ext = ".webp"
    for e in (".webp", ".png", ".jpg", ".jpeg"):
        if path_part.endswith(e) or e in path_part:
            ext = e
            break
    # Prefer webp/png for official; keep jpg only if source is jpg
    dest = IMAGES_DIR / f"{item_id}{ext}"
    try:
        host = (urlparse(url).hostname or "").lower()
        referer = (
            "https://snkrdunk.com/"
            if "snkrdunk.com" in host
            else "https://www.pokemon-card.com/"
        )
        req = Request(
            url,
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": referer,
            },
        )
        with urlopen(req, timeout=30) as resp:  # noqa: S310 — public CDN / official site
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
        if len(data) < 500:
            return None
        # Correct extension from content-type when URL had no clear ext
        if "png" in ctype:
            ext = ".png"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = ".jpg"
        elif "webp" in ctype:
            ext = ".webp"
        dest = IMAGES_DIR / f"{item_id}{ext}"
        # Drop other extensions for this id so dashboard never keeps auction leftovers
        for other in (".webp", ".png", ".jpg", ".jpeg"):
            p = IMAGES_DIR / f"{item_id}{other}"
            if p != dest and p.exists():
                p.unlink()
        dest.write_bytes(data)
        return f"images/{item_id}{ext}"
    except Exception:
        return None


def _local_official_image(item_id: str) -> str | None:
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        path = IMAGES_DIR / f"{item_id}{ext}"
        if path.exists() and path.stat().st_size >= 500:
            return f"images/{item_id}{ext}"
    return None


def _clear_local_images(item_id: str) -> None:
    if not IMAGES_DIR.exists():
        return
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        path = IMAGES_DIR / f"{item_id}{ext}"
        if path.exists():
            path.unlink()


def _face_for_item(wl: dict, snkr: dict) -> dict:
    """Official art only when it is this print. Else the SNKRDUNK SKU photo."""
    from sources.jp_match import _item_fraction, _item_set_code

    face = dict(wl)
    snkr_image = snkr.get("image_url") if isinstance(snkr.get("image_url"), str) else ""
    if str(wl.get("kind") or "") != "sealed":
        code = _item_set_code(wl)
        frac = _item_fraction(wl)
        number = frac[0] if frac else None
        if not number:
            found = re.search(r"-(\d{2,3})$", str(wl.get("tcgdex_id") or ""))
            if found:
                number = found.group(1)
                code = code or found.string.split("-", 1)[0]
        url = str(face.get("image_official_url") or "").strip()
        if url and code and number and not snkrdunk.official_face_matches(url, code, number):
            face["image_official_url"] = None
    if not face.get("image_official_url") and snkr_image.startswith("https://"):
        face["image_official_url"] = snkr_image
    return face


def resolve_official_image(wl: dict) -> str | None:
    """Resolve official thumbnail; never use Yahoo/Mercari listing photos.

    A blank image_official_url deletes any cached face. A changed URL is
    re-downloaded. The previous file is kept only when the catalog URL matches.
    """
    iid = wl["id"]
    url = str(wl.get("image_official_url") or wl.get("official_image") or "").strip()
    if not url:
        _clear_local_images(iid)
        return None
    current = _local_official_image(iid)
    prior_url = ""
    try:
        from series_io import _load_catalog_item

        prior = _load_catalog_item(iid).get("image_official_url")
        if isinstance(prior, str):
            prior_url = prior.strip()
    except Exception:
        prior_url = ""
    if current and prior_url == url:
        return current
    saved = download_image(url, iid)
    if saved:
        return saved
    if prior_url != url:
        _clear_local_images(iid)
        return None
    return current


def fetch_all(cfg: dict) -> tuple[dict[str, dict], dict[str, dict], dict[str, Any]]:
    """Fetch JP + HK for each watchlist item. Returns (jp_by_id, hk_by_id, source_status)."""
    watchlist = cfg.get("watchlist") or []
    interval = float(cfg.get("request_min_interval_sec") or 1.6)
    sources_cfg = cfg.get("sources") or {}
    jp_on = bool(sources_cfg.get("yahoo_auctions_jp", {}).get("enabled"))
    hk_on = bool(sources_cfg.get("carousell_hk", {}).get("enabled"))
    shops_on = bool(sources_cfg.get("hk_card_shops", {}).get("enabled"))
    facebook_on = bool(sources_cfg.get("facebook_hk", {}).get("enabled"))

    jp_by_id: dict[str, dict] = {}
    hk_by_id: dict[str, dict] = {}
    source_status: dict[str, Any] = {
        "yahoo_auctions_jp": {
            "enabled": jp_on,
            "status": "disabled" if not jp_on else "pending",
            "ok_items": 0,
            "errors": [],
            "note": "JP sold closedsearch via __NEXT_DATA__ (reference only)",
        },
    }

    if jp_on:
        print(f"[fetch] Yahoo Auctions JP × {len(watchlist)} (interval≥{interval}s)")
        any_ok = False
        blocked = False
        for i, item in enumerate(watchlist, 1):
            prior_n = len(load_series_points(item["id"]))
            disc = cfg.get("discovery") if isinstance(cfg.get("discovery"), dict) else {}
            shallow_at = int(disc.get("shallow_series_days") or 14)
            backfill_pages = int(disc.get("backfill_max_pages") or 6)
            deep = prior_n < shallow_at
            if item.get("identity_review"):
                print(
                    f"  JP {i}/{len(watchlist)} {item['id']} identity review — skip",
                    flush=True,
                )
                jp_by_id[item["id"]] = {
                    "ok": False,
                    "status": "identity_review",
                    "median_jpy": None,
                    "volume_24h": 0,
                    "volume_7d_est": 0,
                    "comps": [],
                    "total_available": 0,
                    "error": "identity_review",
                    "jp_debug": {
                        "query": None,
                        "matched_titles": [],
                        "matched_prices_jpy": [],
                        "source_urls": [],
                        "matched_n": 0,
                        "note": "identity_review",
                    },
                }
                continue
            if deep:
                print(
                    f"  JP {i}/{len(watchlist)} {item['id']} backfill "
                    f"(series={prior_n}d < {shallow_at}) …",
                    flush=True,
                )
            else:
                print(f"  JP {i}/{len(watchlist)} {item['id']} …", flush=True)
            res = yahoo_auctions_jp.fetch_watchlist_item(
                item,
                min_interval=interval,
                days=(int(cfg.get("history_days") or 90) if deep else None),
                max_pages=backfill_pages,
            )
            jp_by_id[item["id"]] = res
            if res.get("ok"):
                any_ok = True
                source_status["yahoo_auctions_jp"]["ok_items"] += 1
            elif res.get("status") == "blocked":
                blocked = True
                source_status["yahoo_auctions_jp"]["errors"].append(
                    f"{item['id']}: {res.get('error')}"
                )
            elif res.get("error"):
                source_status["yahoo_auctions_jp"]["errors"].append(
                    f"{item['id']}: {res.get('error')}"
                )
        source_status["yahoo_auctions_jp"]["status"] = (
            "ok" if any_ok else ("blocked" if blocked else "empty")
        )

    snkr_on = bool(sources_cfg.get("snkrdunk", {}).get("enabled"))
    source_status["snkrdunk"] = {
        "enabled": snkr_on,
        "status": "disabled" if not snkr_on else "pending",
        "ok_items": 0,
        "errors": [],
        "note": "Catalog match and last sale. Active asks join the HKD sell-ask pool. The PSA10 median still bands local listings.",
    }
    if snkr_on:
        print(f"[fetch] SNKRDUNK × {len(watchlist)} (interval≥{interval}s)")
        for i, item in enumerate(watchlist, 1):
            if item.get("identity_review"):
                print(f"  SNKRDUNK {i}/{len(watchlist)} {item['id']} identity review — skip", flush=True)
                continue
            print(f"  SNKRDUNK {i}/{len(watchlist)} {item['id']} …", flush=True)
            hit = snkrdunk.fetch_watchlist_item(item, min_interval=interval)
            slot = jp_by_id.setdefault(item["id"], {})
            slot["snkrdunk"] = hit
            if hit.get("ok"):
                source_status["snkrdunk"]["ok_items"] += 1
            elif hit.get("error"):
                source_status["snkrdunk"]["errors"].append(f"{item['id']}: {hit.get('error')}")
        source_status["snkrdunk"]["status"] = (
            "ok" if source_status["snkrdunk"]["ok_items"] else "empty"
        )

    if hk_on or shops_on or facebook_on:
        print(
            f"[fetch] HK asks × {len(watchlist)} "
            "(Carousell titles, HKCardLink, LONO, ShipMyToy, Zenox)"
        )
        hk_by_id, hk_status = hk_asks.collect_hk(
            watchlist,
            min_interval=interval,
            carousell_on=hk_on,
            shops_on=shops_on,
            facebook_on=facebook_on,
            jp_hkd_by_id=_band_hkd_map(cfg, jp_by_id),
        )
        source_status.update(hk_status)
        for name, bucket in hk_status.items():
            print(
                f"  {name}: status={bucket.get('status')} "
                f"ok_items={bucket.get('ok_items')} listings={bucket.get('listings')}",
                flush=True,
            )

    return jp_by_id, hk_by_id, source_status


def merge_and_compute(
    cfg: dict,
    jp_by_id: dict[str, dict],
    hk_by_id: dict[str, dict],
    now: datetime,
) -> list[dict]:
    fx = float(cfg["fx_jpy_to_hkd"])
    hist_days = int(cfg.get("history_days", 90))
    today = now.date().isoformat()
    day_1 = (now.date() - timedelta(days=1)).isoformat()
    day_7 = (now.date() - timedelta(days=7)).isoformat()

    from discover_watchlist import pinned_ids

    pins = set(pinned_ids(cfg))
    items: list[dict] = []
    for wl in cfg.get("watchlist") or []:
        iid = wl["id"]
        jp = jp_by_id.get(iid) or {}
        hk = hk_by_id.get(iid) or {}
        if wl.get("identity_review"):
            hk = {
                "median_hkd": None,
                "lowest_hkd": None,
                "bid_hkd": None,
                "listings": [],
                "bid_listings": [],
                "listings_n": 0,
                "backends": [],
            }
        snkr = jp.get("snkrdunk") if isinstance(jp.get("snkrdunk"), dict) else {}
        if jp.get("status") == "preserved":
            raw_price = jp.get("price_jpy")
            price_jpy = int(raw_price) if isinstance(raw_price, (int, float)) and raw_price > 0 else None
            price_source = str(jp.get("price_source") or "preserved")
        else:
            price_jpy, price_source = snkrdunk.choose_jp_price(jp.get("median_jpy"), snkr)
        price = hkd(price_jpy, fx)
        hk_points = _listing_prices_hkd(hk.get("listings") or [])
        if not hk_points:
            hk_points = _summary_prices_hkd(hk.get("median_hkd"), hk.get("lowest_hkd"))
        snkr_points: list[int] = []
        if not wl.get("identity_review"):
            snkr_points = snkrdunk.sell_ask_jpy_points(snkr, kind=str(wl.get("kind") or ""))
        hk_ask, hk_low = unified_sell_asks(hk_points, snkr_points, fx)
        hk_bid = hk.get("bid_hkd")
        quote_listings = list(hk.get("listings") or []) + list(hk.get("bid_listings") or [])

        prev_hist = load_series(iid)
        vol_today = int(jp.get("volume_24h") or 0)
        # Shallow series: merge every sale-day from the paginated closedsearch
        # backfill. Deep series: upsert today only. Never drop other dates.
        if jp.get("days_requested"):
            incoming = comps_to_daily_history(
                jp.get("comps") or [],
                fx=fx,
                days=hist_days,
                today_hk_ask=hk_ask,
            )
            history = merge_history_by_date(
                prev_hist, incoming, prefer_incoming=True, history_days=hist_days
            )
            if hk_ask is not None:
                history = merge_history_by_date(
                    history,
                    [{
                        "date": today,
                        "hk_ask_hkd": hk_ask,
                        "volume": float(vol_today) if vol_today else None,
                    }],
                    prefer_incoming=True,
                    history_days=hist_days,
                )
        else:
            incoming = comps_to_daily_history(
                jp.get("comps") or [],
                fx=fx,
                days=hist_days,
                today_hk_ask=hk_ask,
            )
            incoming.append({
                "date": today,
                "price_hkd": price,
                "hk_ask_hkd": hk_ask,
                "volume": float(vol_today),
            })
            history = merge_history_by_date(
                prev_hist, incoming, prefer_incoming=True, history_days=hist_days
            )

        # Fresh sold quote wins, including null when nothing matched.
        # merge_history_by_date keeps the previous price when incoming is null.
        stamped = False
        for point in history:
            if point.get("date") != today:
                continue
            point["price_hkd"] = price
            point["volume"] = float(vol_today)
            if wl.get("identity_review"):
                point["hk_ask_hkd"] = None
            stamped = True
            break
        if not stamped:
            history.append({
                "date": today,
                "price_hkd": price,
                "hk_ask_hkd": hk_ask,
                "volume": float(vol_today),
            })
            history.sort(key=lambda p: str(p.get("date") or ""))

        prev_1 = price_on_or_before(history[:-1], day_1) if len(history) > 1 else None
        prev_7 = price_on_or_before(history[:-1], day_7) if len(history) > 1 else None
        # If we only have today, changes are 0 (honest — no fake sample drift)
        short_pct = pct_change(price, prev_1) if price is not None else 0.0
        med_pct = pct_change(price, prev_7) if price is not None else 0.0

        vol_7d = avg_volume(history[:-1], 7) if len(history) > 1 else float(
            jp.get("volume_7d_est") or 0
        )
        if vol_7d <= 0:
            vol_7d = float(jp.get("volume_7d_est") or max(vol_today, 1))
        vol_ratio = round(vol_today / vol_7d, 2) if vol_7d else 0.0

        spread_pct = None
        if hk_ask is not None and price and price > 0:
            spread_pct = round((hk_ask - price) / price * 100.0, 2)

        srcs = []
        if price_source == "snkrdunk_last_sale":
            srcs.append("snkrdunk")
        if jp.get("ok") and price_source != "blank_yahoo_vs_snkrdunk":
            srcs.append("yahoo_auctions_jp")
        if snkr.get("url") and "snkrdunk" not in srcs:
            srcs.append("snkrdunk")
        for backend in hk.get("backends") or []:
            if backend not in srcs:
                srcs.append(backend)

        # A single keeps an official URL only when the path encodes this print.
        # Otherwise use the SNKRDUNK catalog photo, or no face.
        face = _face_for_item(wl, snkr)
        image = resolve_official_image(face)
        snkr_image = snkr.get("image_url") if isinstance(snkr.get("image_url"), str) else ""

        recent_sold = snkr.get("recent_sold_n")
        listing_count = snkr.get("listing_count")
        has_snkr_liq = isinstance(recent_sold, int) or isinstance(listing_count, int)
        if jp.get("status") == "preserved" and jp.get("liquidity_score") is not None and not has_snkr_liq:
            liq = int(jp["liquidity_score"])
        else:
            liq = liquidity_score(
                vol_today,
                vol_7d,
                int(jp.get("total_available") or 0),
                recent_sold=float(recent_sold or 0),
                listing_count=int(listing_count or 0),
            )

        row = {
            "id": iid,
            "name_zh": wl.get("name_zh"),
            "name_jp": wl.get("name_jp"),
            "kind": wl.get("kind"),
            "set": wl.get("set"),
            "image": image,
            "tcgdex_id": wl.get("tcgdex_id"),
            "price_hkd": price,
            "price_jpy": price_jpy,
            "short_change_pct": short_pct,
            "medium_change_pct": med_pct,
            "volume_today": vol_today,
            "volume_7d_avg": vol_7d,
            "volume_ratio": vol_ratio,
            "liquidity_score": liq,
            "hk_ask_hkd": hk_ask,
            "spread_jp_hk_pct": spread_pct,
            "sources": srcs,
            "is_sample": False,
            "jp_comps_n": (
                int(jp["jp_debug"]["matched_n"])
                if isinstance(jp.get("jp_debug"), dict) and isinstance(jp["jp_debug"].get("matched_n"), int)
                else len(jp.get("comps") or [])
            ),
            "hk_listings_n": (
                int(hk["listings_n"])
                if hk.get("listings_n") is not None
                else len(hk.get("listings") or [])
            ),
            "hk_backend": hk.get("backend"),
            "history": history,
        }
        if jp.get("query"):
            row["jp_query"] = jp["query"]
        debug = jp.get("jp_debug")
        if isinstance(debug, dict):
            row["jp_debug"] = debug
        if wl.get("name_en"):
            row["name_en"] = wl["name_en"]
        if wl.get("identity_review"):
            row["identity_review"] = True
        if price_source in ("snkrdunk_last_sale", "blank_yahoo_vs_snkrdunk"):
            row["price_source"] = price_source
        if snkr.get("url"):
            row["snkrdunk_url"] = snkr["url"]
        if isinstance(snkr.get("ask_jpy"), int):
            row["snkrdunk_ask_jpy"] = snkr["ask_jpy"]
        for src_key, dest_key in (
            ("ask_min_jpy", "snkrdunk_ask_min_jpy"),
            ("ask_median_jpy", "snkrdunk_ask_median_jpy"),
            ("ask_max_jpy", "snkrdunk_ask_max_jpy"),
        ):
            if isinstance(snkr.get(src_key), int):
                row[dest_key] = snkr[src_key]
        ask_book = snkr.get("ask_prices_jpy")
        if isinstance(ask_book, list):
            book = [price for price in ask_book if isinstance(price, int) and price > 0]
            if book:
                row["snkrdunk_ask_prices_jpy"] = book[:40]
        if isinstance(snkr.get("market_jpy"), int):
            row["snkrdunk_jpy"] = snkr["market_jpy"]
        if isinstance(snkr.get("last_sale_jpy"), int):
            row["snkrdunk_last_sale_jpy"] = snkr["last_sale_jpy"]
        if isinstance(snkr.get("recent_sold_n"), int):
            row["snkrdunk_recent_sold_n"] = snkr["recent_sold_n"]
        if isinstance(snkr.get("listing_count"), int):
            row["snkrdunk_listing_count"] = snkr["listing_count"]
        if snkr_image.startswith("https://") and face.get("image_official_url") == snkr_image:
            row["snkrdunk_image_url"] = snkr_image
        if iid in pins:
            row["pinned"] = True
        attach_public_quotes(
            row,
            watch=wl,
            listings=quote_listings,
            lowest_hkd=hk_low,
            bid_hkd=hk_bid,
        )
        stamp_display_name(row)
        items.append(row)
    return items


def compute_sections(items: list[dict], cfg: dict) -> dict:
    th = cfg["thresholds"]
    short_t = th["short_move_pct"]
    med_t = th["medium_move_pct"]
    vol_t = th["volume_vs_7d_avg"]

    big_moves = []
    for it in items:
        reasons = []
        if abs(it.get("short_change_pct") or 0) >= short_t:
            reasons.append(f"1日 {it['short_change_pct']:+.1f}%")
        if abs(it.get("medium_change_pct") or 0) >= med_t:
            reasons.append(f"7日 {it['medium_change_pct']:+.1f}%")
        if (it.get("volume_ratio") or 0) >= vol_t:
            reasons.append(f"量能 {it['volume_ratio']:.1f}×7日均")
        if reasons:
            big_moves.append({**it, "move_reasons": reasons})
    big_moves.sort(
        key=lambda x: max(abs(x.get("short_change_pct") or 0), abs(x.get("medium_change_pct") or 0)),
        reverse=True,
    )

    from discover_watchlist import include_pinned_rows, pinned_ids

    ranked = sorted(items, key=lambda x: x.get("liquidity_score") or 0, reverse=True)
    liquidity = include_pinned_rows(ranked, pinned_ids(cfg), int(cfg.get("top_n") or 50))

    spreads = [it for it in items if it.get("spread_jp_hk_pct") is not None]
    spreads.sort(key=lambda x: abs(x["spread_jp_hk_pct"]), reverse=True)

    def without_history(it: dict) -> dict:
        return {k: v for k, v in it.items() if k != "history"}

    return {
        "big_moves": [without_history(it) for it in big_moves],
        "liquidity": [without_history(it) for it in liquidity],
        "spreads": [without_history(it) for it in spreads],
    }


def write_series_files(items: list[dict], meta: dict) -> int:
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for it in items:
        doc = {
            "id": it["id"],
            "name_zh": it["name_zh"],
            "name_jp": it.get("name_jp"),
            "kind": it["kind"],
            "set": it.get("set"),
            "is_sample": False,
            "real_points": True,
            "history_days": len(it.get("history") or []),
            "updated_at": meta.get("updated_at"),
            "history": it.get("history") or [],
        }
        path = SERIES_DIR / f"{it['id']}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        written += 1
    return written


def write_outputs(payload: dict) -> None:
    watchlist = payload.pop("_watchlist", None) or []
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    with LATEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    day = payload["meta"]["updated_at"][:10]
    history_doc = {
        "date": day,
        "note": "每日快照：meta + items（真實抓取）。保留約 history_days 天。",
        "meta": {
            "updated_at": payload["meta"]["updated_at"],
            "fx_jpy_to_hkd": payload["meta"]["fx_jpy_to_hkd"],
            "is_sample": payload["meta"]["is_sample"],
            "item_count": payload["meta"]["item_count"],
            "source_status": payload["meta"].get("source_status"),
        },
        "items": [
            {
                "id": it["id"],
                "name_zh": it["name_zh"],
                "kind": it["kind"],
                "price_hkd": it["price_hkd"],
                "price_jpy": it["price_jpy"],
                "volume_today": it["volume_today"],
                "liquidity_score": it["liquidity_score"],
                "hk_ask_hkd": it.get("hk_ask_hkd"),
                "hk_ask_low_hkd": it.get("hk_ask_low_hkd"),
                "hk_bid_hkd": it.get("hk_bid_hkd"),
            }
            for it in payload["items"]
        ],
    }
    hist_path = HISTORY_DIR / f"{day}.json"
    with hist_path.open("w", encoding="utf-8") as f:
        json.dump(history_doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Persist series (merge-by-date) + durable catalog (names / official images / tcgdex)
    n_series = 0
    try:
        from series_io import write_series_merged, write_catalog
        hist_days = int(payload["meta"].get("history_days") or 90)
        for it in payload["items"]:
            write_series_merged(it, payload["meta"], history_days=hist_days)
            n_series += 1
        cat_path = write_catalog(
            watchlist
            or [
                {
                    "id": it["id"],
                    "name_zh": it.get("name_zh"),
                    "name_jp": it.get("name_jp"),
                    "kind": it.get("kind"),
                    "set": it.get("set"),
                    "tcgdex_id": it.get("tcgdex_id"),
                    "image_official_url": None,
                    "image_note": None,
                    "search_jp": None,
                    "search_hk": None,
                }
                for it in payload["items"]
            ],
            payload["items"],
            payload["meta"],
        )
        print(f"Wrote catalog {cat_path.relative_to(ROOT)}")
    except Exception as e:
        # Fallback to legacy series writer
        print(f"[warn] series_io catalog/series failed: {e}; using write_series_files")
        n_series = write_series_files(payload["items"], payload["meta"])

    n_hk = sum(1 for it in payload["items"] if it.get("hk_ask_hkd") is not None)
    n_jp = sum(1 for it in payload["items"] if it.get("price_jpy") is not None)
    print(f"Wrote {LATEST_PATH.relative_to(ROOT)}")
    print(f"Wrote {hist_path.relative_to(ROOT)}")
    print(f"Wrote {n_series} series under data/history/series/")
    print(
        f"REAL items={payload['meta']['item_count']} | "
        f"with_JP={n_jp} | with_HK={n_hk} | "
        f"is_sample={payload['meta']['is_sample']} | "
        f"大異動={len(payload['sections']['大異動'])} | "
        f"流動性={len(payload['sections']['流動性'])} | "
        f"價差={len(payload['sections']['價差'])}"
    )


def _jp_preserved_from_latest() -> dict[str, dict]:
    """Reuse the last JP reference so an HK refresh does not re-hit Yahoo."""
    if not LATEST_PATH.exists():
        return {}
    try:
        prior = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict] = {}
    for it in prior.get("items") or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        out[str(it["id"])] = {
            "ok": it.get("price_jpy") is not None,
            "median_jpy": it.get("price_jpy"),
            "price_jpy": it.get("price_jpy"),
            "price_source": it.get("price_source"),
            "volume_24h": it.get("volume_today") or 0,
            "volume_7d_est": it.get("volume_7d_avg") or 0,
            "total_available": 0,
            "liquidity_score": it.get("liquidity_score"),
            "comps": [],
            "query": it.get("jp_query"),
            "jp_debug": it.get("jp_debug"),
            "status": "preserved",
            "snkrdunk": {
                "ok": bool(it.get("snkrdunk_url")),
                "url": it.get("snkrdunk_url"),
                "name": it.get("snkrdunk_name"),
                "ask_jpy": it.get("snkrdunk_ask_jpy"),
                "ask_min_jpy": it.get("snkrdunk_ask_min_jpy"),
                "ask_median_jpy": it.get("snkrdunk_ask_median_jpy"),
                "ask_max_jpy": it.get("snkrdunk_ask_max_jpy"),
                "ask_prices_jpy": it.get("snkrdunk_ask_prices_jpy"),
                "market_jpy": it.get("snkrdunk_jpy"),
                "last_sale_jpy": it.get("snkrdunk_last_sale_jpy"),
                "recent_sold_n": it.get("snkrdunk_recent_sold_n"),
                "listing_count": it.get("snkrdunk_listing_count"),
                "image_url": it.get("snkrdunk_image_url"),
            },
        }
    return out


def _band_yen(jp: dict) -> int | None:
    """SNKRDUNK PSA10 median (or BOX ask), then the lowest PSA10 ask, then the JP price."""
    snkr = jp.get("snkrdunk") if isinstance(jp.get("snkrdunk"), dict) else {}
    for key in ("market_jpy", "ask_jpy"):
        value = snkr.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value > 0:
            return int(value)
    median = jp.get("median_jpy")
    if isinstance(median, bool) or not isinstance(median, (int, float)):
        return None
    if median <= 0:
        return None
    return int(median)


def _band_hkd_map(cfg: dict, jp_by_id: dict[str, dict]) -> dict[str, float]:
    fx = float(cfg["fx_jpy_to_hkd"])
    out: dict[str, float] = {}
    for iid, jp in jp_by_id.items():
        converted = hkd(_band_yen(jp), fx)
        if converted:
            out[str(iid)] = float(converted)
    return out


def _yahoo_preserved_status() -> dict[str, Any]:
    yahoo: dict[str, Any] = {
        "enabled": True,
        "status": "preserved",
        "ok_items": 0,
        "errors": [],
    }
    if LATEST_PATH.exists():
        try:
            prior = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
            prev = (prior.get("meta") or {}).get("source_status") or {}
            if isinstance(prev.get("yahoo_auctions_jp"), dict):
                yahoo = dict(prev["yahoo_auctions_jp"])
        except (json.JSONDecodeError, OSError):
            pass
    yahoo["note"] = "Preserved JP reference; this run refreshed HK asks only"
    yahoo["status"] = yahoo.get("status") or "preserved"
    return yahoo


def _hk_preserved_from_latest() -> tuple[dict[str, dict], dict[str, Any]]:
    """Reuse the last HK asks so a JP accuracy refresh does not re-hit HK shops."""
    preserved_status: dict[str, Any] = {
        "enabled": True,
        "status": "preserved",
        "ok_items": 0,
        "errors": [],
        "note": "Preserved HK asks; this run refreshed JP sold only",
    }
    if not LATEST_PATH.exists():
        return {}, {"carousell_hk": preserved_status}
    try:
        prior = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, {"carousell_hk": preserved_status}
    out: dict[str, dict] = {}
    for it in prior.get("items") or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        backends = [
            s
            for s in (it.get("sources") or [])
            if s not in ("yahoo_auctions_jp", "snkrdunk")
        ]
        out[str(it["id"])] = {
            "median_hkd": it.get("hk_ask_hkd"),
            "lowest_hkd": it.get("hk_ask_low_hkd"),
            "bid_hkd": it.get("hk_bid_hkd"),
            "listings": [],
            "listings_n": it.get("hk_listings_n") or 0,
            "bid_listings": [],
            "backends": backends,
            "backend": it.get("hk_backend"),
        }
    prev = (prior.get("meta") or {}).get("source_status") or {}
    status: dict[str, Any] = {}
    for key, bucket in prev.items():
        if key in ("yahoo_auctions_jp", "snkrdunk") or not isinstance(bucket, dict):
            continue
        kept = dict(bucket)
        kept["note"] = "Preserved HK asks; this run refreshed JP sold only"
        status[key] = kept
    if "carousell_hk" not in status:
        status["carousell_hk"] = preserved_status
    return out, status


def _snkr_only_books(cfg: dict, jp_fresh: dict[str, dict]) -> dict[str, dict]:
    """Keep a real sold price. An empty PSA10 book does not replay a raw-grade fill."""
    preserved = _jp_preserved_from_latest()
    out: dict[str, dict] = {}
    for item in cfg.get("watchlist") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        iid = str(item["id"])
        fresh = jp_fresh.get(iid) or {}
        prior = preserved.get(iid) or {}
        fresh_snkr = fresh.get("snkrdunk") if isinstance(fresh.get("snkrdunk"), dict) else {}
        prior_snkr = prior.get("snkrdunk") if isinstance(prior.get("snkrdunk"), dict) else {}
        snkr = fresh_snkr if fresh_snkr.get("ok") else prior_snkr
        last = snkr.get("last_sale_jpy") if fresh_snkr.get("ok") else None
        base = {
            "ok": bool(prior.get("ok") or (isinstance(snkr, dict) and snkr.get("ok"))),
            "median_jpy": prior.get("median_jpy"),
            "volume_24h": prior.get("volume_24h") or 0,
            "volume_7d_est": prior.get("volume_7d_est") or 0,
            "total_available": prior.get("total_available") or 0,
            "liquidity_score": prior.get("liquidity_score"),
            "comps": [],
            "query": prior.get("query"),
            "jp_debug": prior.get("jp_debug"),
            "snkrdunk": snkr if isinstance(snkr, dict) else {},
        }
        if fresh_snkr.get("ok") and not snkrdunk.psa10_quote_present(fresh_snkr):
            source = str(prior.get("price_source") or "")
            cleared = {
                **base,
                "price_jpy": None,
                "price_source": "empty",
                "status": "ok",
            }
            if source != "yahoo_auctions_jp":
                cleared["median_jpy"] = None
            else:
                cleared["price_source"] = source
            out[iid] = cleared
            continue
        if isinstance(last, int) and last > 0:
            out[iid] = base
            continue
        out[iid] = {
            **base,
            "price_jpy": prior.get("price_jpy"),
            "price_source": prior.get("price_source"),
            "status": "preserved",
        }
    return out


def _drop_empty_psa10_preserved_asks(jp_by_id: dict[str, dict], hk_by_id: dict[str, dict]) -> None:
    """No local listings means the stored HKD ask was the previous SNKRDUNK pool."""
    for iid, jp in jp_by_id.items():
        snkr = jp.get("snkrdunk") if isinstance(jp.get("snkrdunk"), dict) else {}
        if not snkr.get("ok") or snkrdunk.psa10_quote_present(snkr):
            continue
        hk = hk_by_id.get(iid)
        if not isinstance(hk, dict) or int(hk.get("listings_n") or 0) > 0:
            continue
        hk["median_hkd"] = None
        hk["lowest_hkd"] = None


def build_payload(cfg: dict, *, hk_only: bool = False, jp_only: bool = False, snkr_only: bool = False) -> dict:
    now = datetime.now(HK_TZ)
    if hk_only:
        sources_cfg = cfg.get("sources") or {}
        interval = float(cfg.get("request_min_interval_sec") or 1.6)
        watchlist = cfg.get("watchlist") or []
        print(f"[fetch] HK-only refresh × {len(watchlist)} (JP reference preserved)")
        jp_by_id = _jp_preserved_from_latest()
        snkr_on = bool(sources_cfg.get("snkrdunk", {}).get("enabled"))
        snkr_status: dict[str, Any] = {
            "enabled": snkr_on,
            "status": "disabled" if not snkr_on else "pending",
            "ok_items": 0,
            "errors": [],
            "note": "SNKRDUNK active asks refreshed into the HKD sell-ask pool; local listings still use that band",
        }
        if snkr_on:
            print(f"[fetch] SNKRDUNK asks × {len(watchlist)} (interval≥{interval}s)")
            for item in watchlist:
                slot = jp_by_id.setdefault(item["id"], {"status": "preserved", "snkrdunk": {}})
                snkr = slot.get("snkrdunk") if isinstance(slot.get("snkrdunk"), dict) else {}
                if item.get("identity_review"):
                    continue
                apparel_id = snkrdunk.apparel_id_from_url(str(snkr.get("url") or ""))
                if not apparel_id:
                    continue
                quote = snkrdunk.ask_quote_for_id(
                    apparel_id,
                    kind=str(item.get("kind") or ""),
                    min_interval=interval,
                )
                if quote.get("error"):
                    snkr_status["errors"].append(f"{item['id']}: {quote.get('error')}")
                    continue
                refreshed = dict(snkr)
                refreshed["ok"] = True
                refreshed["market_jpy"] = quote.get("market_jpy")
                refreshed["ask_prices_jpy"] = quote.get("ask_prices_jpy") or []
                refreshed["ask_min_jpy"] = quote.get("ask_min_jpy")
                refreshed["ask_median_jpy"] = quote.get("ask_median_jpy")
                refreshed["ask_max_jpy"] = quote.get("ask_max_jpy")
                if str(item.get("kind") or "") != "sealed":
                    refreshed["ask_jpy"] = quote.get("ask_jpy")
                if quote.get("market_jpy") or quote.get("ask_prices_jpy"):
                    snkr_status["ok_items"] += 1
                slot["snkrdunk"] = refreshed
            snkr_status["status"] = "ok" if snkr_status["ok_items"] else "empty"
        hk_by_id, hk_status = hk_asks.collect_hk(
            watchlist,
            min_interval=interval,
            carousell_on=bool(sources_cfg.get("carousell_hk", {}).get("enabled")),
            shops_on=bool(sources_cfg.get("hk_card_shops", {}).get("enabled")),
            facebook_on=bool(sources_cfg.get("facebook_hk", {}).get("enabled")),
            jp_hkd_by_id=_band_hkd_map(cfg, jp_by_id),
        )
        for name, bucket in hk_status.items():
            print(
                f"  {name}: status={bucket.get('status')} "
                f"ok_items={bucket.get('ok_items')} listings={bucket.get('listings')}",
                flush=True,
            )
        source_status = {
            "yahoo_auctions_jp": _yahoo_preserved_status(),
            "snkrdunk": snkr_status,
        }
        source_status.update(hk_status)
    elif jp_only:
        jp_by_id, _hk_unused, source_status = fetch_all(
            {
                **cfg,
                "sources": {
                    **(cfg.get("sources") or {}),
                    "carousell_hk": {"enabled": False},
                    "hk_card_shops": {"enabled": False},
                    "facebook_hk": {"enabled": False},
                },
            }
        )
        hk_by_id, hk_status = _hk_preserved_from_latest()
        source_status.update(hk_status)
        print("[fetch] JP-only refresh (HK asks preserved)", flush=True)
    elif snkr_only:
        print("[fetch] SNKRDUNK-only refresh (Yahoo sold and HK asks preserved)", flush=True)
        fresh_cfg = {
            **cfg,
            "sources": {
                **(cfg.get("sources") or {}),
                "yahoo_auctions_jp": {"enabled": False},
                "carousell_hk": {"enabled": False},
                "hk_card_shops": {"enabled": False},
                "facebook_hk": {"enabled": False},
            },
        }
        jp_fresh, _hk_unused, source_status = fetch_all(fresh_cfg)
        jp_by_id = _snkr_only_books(cfg, jp_fresh)
        hk_by_id, hk_status = _hk_preserved_from_latest()
        _drop_empty_psa10_preserved_asks(jp_by_id, hk_by_id)
        for bucket in hk_status.values():
            if isinstance(bucket, dict):
                bucket["note"] = "Preserved HK asks; this run refreshed SNKRDUNK"
        yahoo = _yahoo_preserved_status()
        yahoo["note"] = "Preserved JP sold; this run refreshed SNKRDUNK asks"
        source_status["yahoo_auctions_jp"] = yahoo
        source_status.update(hk_status)
    else:
        jp_by_id, hk_by_id, source_status = fetch_all(cfg)
    items = merge_and_compute(cfg, jp_by_id, hk_by_id, now)
    min_hkd = float(cfg.get("min_list_price_hkd") or 0)
    quoted_before = len(items)
    if min_hkd > 0:
        items = [it for it in items if snkrdunk.meets_min_list_price(it, min_hkd)]
    excluded_below = quoted_before - len(items)
    sections = compute_sections(items, cfg)

    n_hk = sum(1 for it in items if it.get("hk_ask_hkd") is not None)
    n_jp = sum(1 for it in items if it.get("price_jpy") is not None)
    # is_sample only if TOTAL failure (no real JP and no real HK)
    is_sample = (n_jp == 0 and n_hk == 0)

    return {
        "_watchlist": cfg.get("watchlist") or [],
        "meta": {
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Hong_Kong",
            "is_sample": is_sample,
            "sample_label": (
                "範例資料 — 抓取全失敗時保留"
                if is_sample
                else None
            ),
            "fx_jpy_to_hkd": cfg["fx_jpy_to_hkd"],
            "min_list_price_hkd": min_hkd,
            "display_currency": cfg["display_currency"],
            "thresholds": cfg["thresholds"],
            "top_n": cfg["top_n"],
            "history_days": cfg["history_days"],
            "item_count": len(items),
            "counts": {
                "with_jp_price": n_jp,
                "with_hk_ask": n_hk,
                "excluded_below_min_hkd": excluded_below,
            },
            "pipeline": [
                "discover: SNKRDUNK Hottest Items, then hottest search fill",
                "fetch yahoo_auctions_jp sold (reference) + title-matched HK asks",
                "backfill shallow series from closed comps (merge by date; never wipe)",
                "normalize HKD via fx_jpy_to_hkd",
                "compute movers / liquidity / spreads from history",
                "thumbnails: official TCGdex / pokemon-card.com art only (never auction photos)",
                "write latest.json + history day file + series + catalog",
            ],
            "discovery": _discovery_meta(),
            "image_source": "official",
            "image_source_note": "Dashboard thumbnails from TCGdex card faces or pokemon-card.com product art; Yahoo listing photos are never used.",
            "sources_enabled": {
                k: v.get("enabled", False) for k, v in cfg.get("sources", {}).items()
            },
            "source_status": source_status,
            "display": cfg.get("display"),
        },
        "items": items,
        "sections": {
            "大異動": sections["big_moves"],
            "流動性": sections["liquidity"],
            "價差": sections["spreads"],
        },
    }


def _discovery_meta() -> dict | None:
    path = ROOT / "data" / "catalog" / "liquidity_rank.json"
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    return {
        "applied": doc.get("applied"),
        "updated_at": doc.get("updated_at"),
        "method": doc.get("method"),
        "selected_count": doc.get("selected_count"),
        "psa10_slots": doc.get("psa10_slots"),
        "sealed_slots": doc.get("sealed_slots"),
        "window_days": doc.get("window_days"),
        "rank_path": "data/catalog/liquidity_rank.json",
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = load_config()
    if "--no-discover" not in sys.argv:
        from discover_watchlist import refresh_watchlist

        cfg = refresh_watchlist(cfg, force=("--discover" in sys.argv))
    if not cfg.get("watchlist"):
        print("ERROR: config.json missing watchlist", file=sys.stderr)
        sys.exit(1)
    if len(cfg.get("watchlist") or []) < 45:
        print(
            f"ERROR: watchlist has {len(cfg.get('watchlist') or [])} items; "
            "expected at least 45 after discovery",
            file=sys.stderr,
        )
        sys.exit(1)
    payload = build_payload(
        cfg,
        hk_only=("--hk-only" in sys.argv),
        jp_only=("--jp-only" in sys.argv),
        snkr_only=("--snkr-only" in sys.argv),
    )
    write_outputs(payload)
    # Print source_status summary
    ss = payload["meta"].get("source_status") or {}
    print("--- source_status ---")
    print(json.dumps(ss, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
