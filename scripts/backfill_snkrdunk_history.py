#!/usr/bin/env python3
"""Backfill ~90d price and volume from SNKRDUNK charts.

PSA10 uses the used sales chart, option 22 only. Sealed uses the new-product
chart filtered to 1個, then sales-history dates when that chart is empty.
Points merge into data/history/series/{id}.json by date. An empty chart
leaves the series file untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from series_io import load_series_points, write_series_merged  # noqa: E402
from sources import snkrdunk  # noqa: E402

CONFIG_PATH = ROOT / "config.json"
LATEST_PATH = ROOT / "data" / "latest.json"
HK_TZ = timezone(timedelta(hours=8))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def apparel_id_for(item: dict) -> str | None:
    url = item.get("snkrdunk_url")
    found = snkrdunk.apparel_id_from_url(url if isinstance(url, str) else None)
    if found:
        return found
    links = item.get("links")
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            href = link.get("href")
            if not isinstance(href, str) or "snkrdunk.com" not in href:
                continue
            found = snkrdunk.apparel_id_from_url(href)
            if found:
                return found
    return None


def series_count(item_id: str) -> int:
    return len(load_series_points(item_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", action="append", default=[], help="Only these item ids")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N items with an apparel id")
    args = parser.parse_args()

    cfg = load_json(CONFIG_PATH)
    latest = load_json(LATEST_PATH)
    items = latest.get("items")
    if not isinstance(items, list):
        print("latest.json has no items", flush=True)
        return 1

    fx = float(cfg.get("fx_jpy_to_hkd") or 0.0495)
    days = int(cfg.get("history_days") or 90)
    interval = float(cfg.get("request_min_interval_sec") or 1.6)
    now = datetime.now(HK_TZ)
    wanted = set(args.id)
    rows = [it for it in items if isinstance(it, dict) and it.get("id")]
    if wanted:
        rows = [it for it in rows if it.get("id") in wanted]

    ids = [str(it["id"]) for it in rows]
    before_short = sum(1 for iid in ids if series_count(iid) < 5)
    before_counts = {iid: series_count(iid) for iid in ids}
    print(
        f"[backfill] {len(rows)} items, series<5 before {before_short}/{len(rows)}",
        flush=True,
    )

    filled = 0
    skipped = 0
    empty = 0
    best: tuple[int, str, int, int] | None = None
    seen = 0
    for item in rows:
        iid = str(item["id"])
        apparel_id = apparel_id_for(item)
        if not apparel_id:
            skipped += 1
            continue
        seen += 1
        if args.limit and seen > args.limit:
            break
        kind = str(item.get("kind") or "")
        if kind == "sealed":
            points = snkrdunk.fetch_sealed_90d_points(
                apparel_id, min_interval=interval, days=days, now=now
            )
        else:
            points = snkrdunk.fetch_psa10_90d_points(
                apparel_id, min_interval=interval, days=days, now=now
            )
        daily = snkrdunk.bucket_chart_points(points, fx=fx, days=days, now=now)
        prior_n = before_counts.get(iid, 0)
        if not daily:
            empty += 1
            print(f"  {iid} apparel {apparel_id} chart empty (series {prior_n})", flush=True)
            continue
        write_series_merged(
            {
                "id": iid,
                "name_zh": item.get("name_zh"),
                "name_jp": item.get("name_jp"),
                "kind": item.get("kind"),
                "set": item.get("set"),
                "image": item.get("image"),
                "tcgdex_id": item.get("tcgdex_id"),
                "history": daily,
            },
            {"updated_at": now.isoformat(timespec="seconds")},
            history_days=days,
            extra={"backfill": "snkrdunk_sales_chart"},
        )
        after_n = series_count(iid)
        filled += 1
        gain = after_n - prior_n
        if best is None or gain > best[0]:
            best = (gain, iid, prior_n, after_n)
        print(
            f"  {iid} apparel {apparel_id} {prior_n} -> {after_n} days",
            flush=True,
        )

    after_ids = [str(it["id"]) for it in rows]
    after_short = sum(1 for iid in after_ids if series_count(iid) < 5)
    print(
        f"[backfill] filled {filled}, empty {empty}, no apparel {skipped}",
        flush=True,
    )
    print(f"[backfill] series<5 before {before_short}/{len(rows)} after {after_short}/{len(rows)}", flush=True)
    if best is not None:
        _gain, iid, prior_n, after_n = best
        print(
            f"[backfill] example {iid} {prior_n} -> {after_n} "
            f"https://burnxwallpaper.github.io/pokemon-tcg-tracker/?id={iid}",
            flush=True,
        )
    from update import recompute_published_history

    recompute_published_history(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
