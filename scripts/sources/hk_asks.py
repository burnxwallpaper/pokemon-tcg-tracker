"""Combine title-matched HK asks. JP Yahoo stays a reference price elsewhere."""
from __future__ import annotations

from typing import Any

from . import carousell_hk, hk_shops
from .hk_match import (
    broad_query,
    english_query,
    extra_queries,
    lowest_ask,
    primary_query,
    robust_median,
)
from .reference_links import best_bid, is_wtb


def _empty_source() -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "pending",
        "ok_items": 0,
        "listings": 0,
        "errors": [],
    }


def collect_hk(
    watchlist: list[dict],
    *,
    min_interval: float,
    carousell_on: bool,
    shops_on: bool,
    facebook_on: bool,
) -> tuple[dict[str, dict], dict[str, Any]]:
    status: dict[str, Any] = {
        "carousell_hk": {
            **_empty_source(),
            "enabled": carousell_on,
            "status": "disabled" if not carousell_on else "pending",
            "note": "Title-matched listingCards from Carousell HK search",
        },
        "hkcardlink": {
            **_empty_source(),
            "note": "Public Supabase listings matched by title",
        },
        "lono": {
            **_empty_source(),
            "enabled": shops_on,
            "status": "disabled" if not shops_on else "pending",
            "note": "lono.com.hk PSA + Pokémon category prices",
        },
        "zenox": {
            **_empty_source(),
            "enabled": shops_on,
            "status": "disabled" if not shops_on else "pending",
            "note": "zenoxstore.com Shopify JP booster boxes",
        },
        "facebook_hk": {
            **_empty_source(),
            "enabled": facebook_on,
            "status": "disabled" if not facebook_on else "pending",
            "note": "Public page probe only",
        },
    }
    hk_by_id: dict[str, dict] = {}
    carousell_blocked = False
    if carousell_on:
        probe = carousell_hk.prefetch_carousell_status(min_interval=min_interval)
        status["carousell_hk"]["probe"] = {
            "status": probe.get("status"),
            "error": probe.get("error"),
            "listing_count": probe.get("listing_count"),
        }
        carousell_blocked = not bool(probe.get("ok"))
        if carousell_blocked:
            status["carousell_hk"]["status"] = probe.get("status") or "blocked"
            status["carousell_hk"]["errors"].append(str(probe.get("error") or "unreachable"))

    if shops_on:
        shops = hk_shops.prefetch_shops(min_interval=min_interval)
        status["lono"]["catalog_size"] = shops["lono"]["catalog_size"]
        status["zenox"]["catalog_size"] = shops["zenox"]["catalog_size"]
        if shops["lono"]["error"]:
            status["lono"]["errors"].append(shops["lono"]["error"])
        if shops["zenox"]["error"]:
            status["zenox"]["errors"].append(shops["zenox"]["error"])

    if facebook_on:
        status["facebook_hk"] = hk_shops.probe_facebook(min_interval=min_interval)

    hkcardlink_size = None
    for item in watchlist:
        parts: dict[str, dict] = {}
        if carousell_on and not carousell_blocked:
            queries = []
            for query in (
                primary_query(item),
                *extra_queries(item),
                english_query(item),
                broad_query(item),
            ):
                if query and query not in queries:
                    queries.append(query)
            parts["carousell_hk"] = carousell_hk.search_carousell_item(
                item, min_interval=min_interval, queries=queries
            )
        if True:
            parts["hkcardlink"] = carousell_hk.search_hkcardlink_item(
                item, min_interval=min_interval
            )
            hkcardlink_size = parts["hkcardlink"].get("catalog_size")
        if shops_on:
            parts["lono"] = hk_shops.match_shop("lono", item, min_interval=min_interval)
            parts["zenox"] = hk_shops.match_shop("zenox", item, min_interval=min_interval)
        wtb = carousell_hk.search_hkcardlink_wtb(item, min_interval=min_interval)

        asks: list[float] = []
        listings: list[dict] = []
        bid_listings: list[dict] = []
        backends: list[str] = []
        for name, part in parts.items():
            bucket = status[name]
            sell_rows = [
                row for row in (part.get("listings") or []) if not is_wtb(row)
            ]
            if part.get("ok") and sell_rows:
                bucket["ok_items"] += 1
                bucket["listings"] += len(sell_rows)
                asks.extend(float(row["price_hkd"]) for row in sell_rows if row.get("price_hkd"))
                listings.extend(sell_rows)
                backends.append(name)
            elif part.get("error") and len(bucket["errors"]) < 12:
                bucket["errors"].append(f"{item.get('id')}: {part.get('error')}")
        for row in wtb.get("listings") or []:
            if is_wtb(row):
                bid_listings.append(row)
        median_hkd = robust_median(asks)
        low_hkd = lowest_ask(asks)
        bid_hkd, _bid_row = best_bid(bid_listings)
        hk_by_id[item["id"]] = {
            "ok": median_hkd is not None,
            "median_hkd": median_hkd,
            "lowest_hkd": low_hkd,
            "bid_hkd": bid_hkd,
            "listings": listings[:20],
            "bid_listings": bid_listings[:8],
            "backends": backends,
            "backend": "+".join(backends) if backends else None,
            "error": None if median_hkd is not None else "no title-matched HK ask",
        }

    if hkcardlink_size is not None:
        status["hkcardlink"]["catalog_size"] = hkcardlink_size
    for name, bucket in status.items():
        if bucket.get("status") in ("disabled", "unreachable"):
            continue
        if name == "facebook_hk":
            continue
        if bucket["ok_items"]:
            bucket["status"] = "ok"
        elif bucket["errors"] and bucket.get("status") == "pending":
            bucket["status"] = "empty"
        elif bucket.get("status") == "pending":
            bucket["status"] = "empty"
    return hk_by_id, status
