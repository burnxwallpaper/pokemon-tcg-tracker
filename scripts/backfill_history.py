#!/usr/bin/env python3
"""
backfill_history.py — Aggregate Yahoo Auctions JP closed comps into ~90d series.

MERGE semantics: incoming daily points are merged by date into existing
data/history/series/{id}.json (never wipe prior real points). Incremental
mode: if series already has depth, only fetch recent pages.

Does NOT re-hit Carousell / wipe images. Preserves hk_ask_hkd + image paths.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from sources import yahoo_auctions_jp  # noqa: E402
from sources.yahoo_auctions_jp import comps_to_daily_history  # noqa: E402
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


def load_latest() -> dict:
    if not LATEST_PATH.exists():
        return {}
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def pct_change(curr: float | None, prev: float | None) -> float:
    if curr is None or prev is None or prev == 0:
        return 0.0
    return round((curr - prev) / prev * 100.0, 2)


def price_on_or_before(history: list[dict], target_date: str, field: str = "price_hkd") -> float | None:
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


def liquidity_score(vol_today: float, vol_7d: float, total_available: int) -> int:
    base = min(70.0, vol_today * 3.0 + vol_7d * 2.0)
    depth = min(25.0, (total_available or 0) / 40.0)
    return int(max(1, min(99, round(base + depth))))


def existing_image(item_id: str, prior: dict | None) -> str | None:
    """Prefer existing local file; retarget prior path if official images swapped ext."""
    if prior and prior.get("image"):
        rel = prior["image"]
        if (ROOT / "data" / rel).exists():
            return rel
    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        if (IMAGES_DIR / f"{item_id}{ext}").exists():
            return f"images/{item_id}{ext}"
    if prior and prior.get("image"):
        return prior["image"]
    return None


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
        key=lambda x: max(
            abs(x.get("short_change_pct") or 0), abs(x.get("medium_change_pct") or 0)
        ),
        reverse=True,
    )

    liquidity = sorted(items, key=lambda x: x.get("liquidity_score") or 0, reverse=True)
    liquidity = liquidity[: int(cfg.get("top_n") or 50)]

    spreads = [it for it in items if it.get("spread_jp_hk_pct") is not None]
    spreads.sort(key=lambda x: abs(x["spread_jp_hk_pct"]), reverse=True)

    def without_history(it: dict) -> dict:
        return {k: v for k, v in it.items() if k != "history"}

    return {
        "big_moves": [without_history(it) for it in big_moves],
        "liquidity": [without_history(it) for it in liquidity],
        "spreads": [without_history(it) for it in spreads],
    }


def write_series_files(items: list[dict], meta: dict, hist_days: int) -> int:
    """Merge each item history into on-disk series by date (append/upsert only)."""
    written = 0
    for it in items:
        write_series_merged(
            it,
            meta,
            history_days=hist_days,
            extra={"backfill": "yahoo_closedsearch"},
        )
        written += 1
    return written


def _series_depth_ok(prior_hist: list[dict], *, min_days: int = 14) -> bool:
    return len(prior_hist) >= min_days


def _choose_fetch_budget(prior_hist: list[dict], hist_days: int, force_full: bool) -> tuple[int, int]:
    """Return (days, max_pages). Incremental when series already deep."""
    if force_full or not _series_depth_ok(prior_hist):
        return hist_days, 8
    # Already backfilled — only refresh recent closed comps
    return min(14, hist_days), 2


def main() -> None:
    cfg = load_config()
    fx = float(cfg["fx_jpy_to_hkd"])
    hist_days = int(cfg.get("history_days") or 90)
    interval = float(cfg.get("request_min_interval_sec") or 1.6)
    # Mild: slightly slower for multi-page backfill
    interval = max(interval, 1.7)
    force_full = "--full" in sys.argv

    prior_latest = load_latest()
    prior_by_id = {it["id"]: it for it in (prior_latest.get("items") or []) if it.get("id")}

    now = datetime.now(HK_TZ)
    today = now.date().isoformat()
    day_1 = (now.date() - timedelta(days=1)).isoformat()
    day_7 = (now.date() - timedelta(days=7)).isoformat()

    watchlist = cfg.get("watchlist") or []
    print(
        f"[backfill] Yahoo closedsearch × {len(watchlist)} items, "
        f"target_days≤{hist_days}, interval≥{interval}s, "
        f"mode={'full' if force_full else 'incremental-if-deep'}",
        flush=True,
    )

    items_out: list[dict] = []
    depth_report: list[dict] = []
    jp_ok = 0
    errors: list[str] = []

    for i, wl in enumerate(watchlist, 1):
        iid = wl["id"]
        print(f"  [{i}/{len(watchlist)}] {iid} …", flush=True)
        prior = prior_by_id.get(iid) or {}
        prior_hist = load_series_points(iid)
        fetch_days, max_pages = _choose_fetch_budget(prior_hist, hist_days, force_full)
        print(
            f"    prior_series={len(prior_hist)}d → fetch days≤{fetch_days} pages≤{max_pages}",
            flush=True,
        )
        res = yahoo_auctions_jp.fetch_watchlist_item(
            wl, min_interval=interval, days=fetch_days, max_pages=max_pages
        )

        hk_ask = prior.get("hk_ask_hkd")
        if hk_ask is not None:
            hk_ask = round(float(hk_ask), 2)

        incoming = comps_to_daily_history(
            res.get("comps") or [],
            fx=fx,
            days=hist_days,
            today_hk_ask=hk_ask,
        )
        # MERGE by date into existing series (never wipe prior real points)
        history = merge_history_by_date(
            prior_hist, incoming, prefer_incoming=True, history_days=hist_days
        )

        # If Yahoo returned comps but none mapped to today, ensure today point
        # uses overall median so dashboard still has a current price.
        # Only real sale-date points (no synthetic "today" when Yahoo had no endTime today)
        today_point = next((p for p in history if p.get("date") == today), None)
        price_jpy = res.get("median_jpy")
        if today_point and today_point.get("price_hkd") is not None:
            price = float(today_point["price_hkd"])
            from sources._http import median as _med

            today_prices = []
            for c in res.get("comps") or []:
                et = c.get("end_time")
                if not et:
                    continue
                try:
                    dt = datetime.fromisoformat(et)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
                    if dt.astimezone(HK_TZ).date().isoformat() == today:
                        today_prices.append(int(c["price_jpy"]))
                except ValueError:
                    pass
            if today_prices:
                price_jpy = int(round(_med(today_prices)))
            if hk_ask is not None:
                today_point["hk_ask_hkd"] = hk_ask
        elif history:
            # Current = most recent sale day
            price = history[-1].get("price_hkd")
            if price is not None:
                price_jpy = int(round(float(price) / fx))
        elif price_jpy is not None:
            price = round(float(price_jpy) * fx, 2)
        else:
            price = prior.get("price_hkd")
            price_jpy = prior.get("price_jpy")

        # Trim
        history = [p for p in history if p.get("date")][-hist_days:]

        # Metrics from richer history
        prev_1 = price_on_or_before(history, day_1) if len(history) > 1 else None
        # If no point on day_1, price_on_or_before already walks; exclude today for lookback
        hist_before_today = [p for p in history if p.get("date") != today]
        prev_1 = price_on_or_before(hist_before_today, day_1) if hist_before_today else None
        prev_7 = price_on_or_before(hist_before_today, day_7) if hist_before_today else None

        short_pct = pct_change(price, prev_1) if price is not None else 0.0
        med_pct = pct_change(price, prev_7) if price is not None else 0.0

        # Re-resolve today_point after merge
        today_point = next((p for p in history if p.get("date") == today), None)
        vol_today = float(today_point.get("volume") or 0) if today_point else 0.0

        vol_7d = avg_volume(hist_before_today, 7) if hist_before_today else float(
            res.get("volume_7d_est") or 0
        )
        if vol_7d <= 0:
            vol_7d = float(res.get("volume_7d_est") or max(vol_today, 1))
        vol_ratio = round(vol_today / vol_7d, 2) if vol_7d else 0.0

        spread_pct = None
        if hk_ask is not None and price and price > 0:
            spread_pct = round((hk_ask - price) / price * 100.0, 2)

        srcs = list(prior.get("sources") or [])
        if res.get("ok") and "yahoo_auctions_jp" not in srcs:
            srcs.insert(0, "yahoo_auctions_jp")
        if not srcs and res.get("ok"):
            srcs = ["yahoo_auctions_jp"]

        image = existing_image(iid, prior)
        liq = liquidity_score(
            vol_today, vol_7d, int(res.get("total_available") or 0)
        )

        n_days = len(history)
        depth_report.append(
            {
                "id": iid,
                "days": n_days,
                "comps": len(res.get("comps") or []),
                "pages": res.get("pages_fetched"),
                "oldest": res.get("oldest_end"),
                "newest": res.get("newest_end"),
                "total_available": res.get("total_available"),
                "status": res.get("status"),
                "error": res.get("error"),
            }
        )
        if res.get("ok"):
            jp_ok += 1
        elif res.get("error"):
            errors.append(f"{iid}: {res.get('error')}")

        print(
            f"    → days={n_days} comps={len(res.get('comps') or [])} "
            f"pages={res.get('pages_fetched')} status={res.get('status')}",
            flush=True,
        )

        items_out.append(
            {
                "id": iid,
                "name_zh": wl.get("name_zh"),
                "name_jp": wl.get("name_jp"),
                "kind": wl.get("kind"),
                "set": wl.get("set"),
                "image": image,
                "price_hkd": price,
                "price_jpy": price_jpy,
                "short_change_pct": short_pct,
                "medium_change_pct": med_pct,
                "volume_today": int(vol_today),
                "volume_7d_avg": vol_7d,
                "volume_ratio": vol_ratio,
                "liquidity_score": liq,
                "hk_ask_hkd": hk_ask,
                "spread_jp_hk_pct": spread_pct,
                "sources": srcs,
                "is_sample": False,
                "jp_comps_n": len(res.get("comps") or []),
                "hk_listings_n": prior.get("hk_listings_n") or 0,
                "hk_backend": prior.get("hk_backend"),
                "history": history,
            }
        )

    sections = compute_sections(items_out, cfg)
    n_hk = sum(1 for it in items_out if it.get("hk_ask_hkd") is not None)
    n_jp = sum(1 for it in items_out if it.get("price_jpy") is not None)

    # Refresh Yahoo; keep every HK source count from the prior snapshot.
    prior_ss = (prior_latest.get("meta") or {}).get("source_status") or {}
    source_status = dict(prior_ss) if isinstance(prior_ss, dict) else {}
    source_status["yahoo_auctions_jp"] = {
        "enabled": True,
        "status": "ok" if jp_ok else "empty",
        "ok_items": jp_ok,
        "errors": errors[:20],
        "note": f"JP sold closedsearch backfill ≤{hist_days}d via __NEXT_DATA__",
        "backfill": True,
    }

    payload = {
        "meta": {
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Hong_Kong",
            "is_sample": False if (n_jp or n_hk) else True,
            "sample_label": None,
            "fx_jpy_to_hkd": fx,
            "display_currency": cfg["display_currency"],
            "thresholds": cfg["thresholds"],
            "top_n": cfg["top_n"],
            "history_days": hist_days,
            "item_count": len(items_out),
            "counts": {"with_jp_price": n_jp, "with_hk_ask": n_hk},
            "pipeline": [
                "backfill yahoo_auctions_jp closed comps by HKT sale date",
                "daily median JPY→HKD + volume; preserve HK asks + images",
                "recompute movers / liquidity / spreads from history",
                "write latest.json + series",
            ],
            "sources_enabled": {
                k: v.get("enabled", False) for k, v in cfg.get("sources", {}).items()
            },
            "source_status": source_status,
            "display": cfg.get("display"),
            "backfill_report": {
                "items": depth_report,
                "median_days": sorted(d["days"] for d in depth_report)[
                    len(depth_report) // 2
                ]
                if depth_report
                else 0,
            },
        },
        "items": items_out,
        "sections": {
            "大異動": sections["big_moves"],
            "流動性": sections["liquidity"],
            "價差": sections["spreads"],
        },
    }

    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LATEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Daily snapshot (same shape as update.py)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_doc = {
        "date": today,
        "note": "每日快照（Yahoo closedsearch 歷史回填後）。",
        "meta": {
            "updated_at": payload["meta"]["updated_at"],
            "fx_jpy_to_hkd": fx,
            "is_sample": payload["meta"]["is_sample"],
            "item_count": payload["meta"]["item_count"],
            "source_status": source_status,
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
            }
            for it in items_out
        ],
    }
    hist_path = HISTORY_DIR / f"{today}.json"
    with hist_path.open("w", encoding="utf-8") as f:
        json.dump(history_doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_series = write_series_files(items_out, payload["meta"], hist_days)
    # Sync item histories from merged on-disk series (write_series_merged mutates items)
    for it in items_out:
        it["history"] = merge_history_by_date(
            load_series_points(it["id"]), it.get("history") or [], history_days=hist_days
        )
        depth_for = next((d for d in depth_report if d["id"] == it["id"]), None)
        if depth_for is not None:
            depth_for["days"] = len(it["history"])

    # Refresh latest with merged histories
    payload["items"] = items_out
    payload["meta"]["pipeline"] = [
        "backfill yahoo_auctions_jp closed comps by HKT sale date",
        "MERGE daily points into series/{id}.json by date (never wipe)",
        "preserve HK asks + images; write catalog identity",
        "recompute movers / liquidity / spreads from history",
    ]
    with LATEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    cat_path = write_catalog(watchlist, items_out, payload["meta"])

    days_list = [d["days"] for d in depth_report]
    multi = sum(1 for d in days_list if d > 1)
    print("--- backfill summary ---")
    print(f"Wrote {LATEST_PATH.relative_to(ROOT)}")
    print(f"Wrote {hist_path.relative_to(ROOT)}")
    print(f"Merged {n_series} series (by date)")
    print(f"Wrote {cat_path.relative_to(ROOT)}")
    print(
        f"items={len(items_out)} jp_ok={jp_ok} multi_day={multi} "
        f"median_depth={sorted(days_list)[len(days_list)//2] if days_list else 0} "
        f"max_depth={max(days_list) if days_list else 0}"
    )
    print(json.dumps(depth_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
