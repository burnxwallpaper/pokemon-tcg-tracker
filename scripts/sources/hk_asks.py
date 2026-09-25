"""Combine title-matched HK shop asks. JP Yahoo stays a reference price elsewhere."""
from __future__ import annotations

from typing import Any

from . import hk_shops
from .hk_match import publish_ask
from .reference_links import is_wtb

DROPPED_HK_SOURCES = frozenset({"carousell_hk", "hkcardlink"})


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
    shops_on: bool,
    facebook_on: bool,
    jp_hkd_by_id: dict[str, float] | None = None,
) -> tuple[dict[str, dict], dict[str, Any]]:
    status: dict[str, Any] = {
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
            "note": "zenoxstore.com JP booster boxes and in-stock PSA10 slabs",
        },
        "shipmytoy": {
            **_empty_source(),
            "enabled": shops_on,
            "status": "disabled" if not shops_on else "pending",
            "note": "shipmytoy.com.hk Pokémon category; box price, not the pack price",
        },
        "facebook_hk": {
            **_empty_source(),
            "enabled": facebook_on,
            "status": "disabled" if not facebook_on else "pending",
            "note": "Public page probe only",
        },
    }
    hk_by_id: dict[str, dict] = {}

    if shops_on:
        shops = hk_shops.prefetch_shops(min_interval=min_interval)
        status["lono"]["catalog_size"] = shops["lono"]["catalog_size"]
        status["zenox"]["catalog_size"] = shops["zenox"]["catalog_size"]
        status["shipmytoy"]["catalog_size"] = shops["shipmytoy"]["catalog_size"]
        if shops["lono"]["error"]:
            status["lono"]["errors"].append(shops["lono"]["error"])
        if shops["zenox"]["error"]:
            status["zenox"]["errors"].append(shops["zenox"]["error"])
        if shops["shipmytoy"]["error"]:
            status["shipmytoy"]["errors"].append(shops["shipmytoy"]["error"])

    if facebook_on:
        status["facebook_hk"] = hk_shops.probe_facebook(min_interval=min_interval)

    for item in watchlist:
        parts: dict[str, dict] = {}
        if shops_on:
            parts["lono"] = hk_shops.match_shop("lono", item, min_interval=min_interval)
            parts["zenox"] = hk_shops.match_shop("zenox", item, min_interval=min_interval)
            parts["shipmytoy"] = hk_shops.match_shop("shipmytoy", item, min_interval=min_interval)

        listings: list[dict] = []
        for name, part in parts.items():
            bucket = status[name]
            sell_rows = [
                row for row in (part.get("listings") or []) if not is_wtb(row)
            ]
            if part.get("ok") and sell_rows:
                bucket["ok_items"] += 1
                bucket["listings"] += len(sell_rows)
                for row in sell_rows:
                    copied = dict(row)
                    if not copied.get("source"):
                        copied["source"] = name
                    listings.append(copied)
            elif part.get("error") and len(bucket["errors"]) < 12:
                bucket["errors"].append(f"{item.get('id')}: {part.get('error')}")
        jp_hkd = (jp_hkd_by_id or {}).get(str(item.get("id") or ""))
        decision = publish_ask(listings, jp_hkd)
        published = decision.get("hkd")
        used = decision.get("listings") or []
        lows: list[float] = []
        for row in used:
            try:
                price = float(row.get("price_hkd"))
            except (TypeError, ValueError):
                continue
            if price > 0:
                lows.append(price)
        backends: list[str] = []
        for row in used:
            source = str(row.get("source") or "")
            if source and source not in backends and source not in DROPPED_HK_SOURCES:
                backends.append(source)
        hk_by_id[item["id"]] = {
            "ok": published is not None,
            "median_hkd": published,
            "published_hkd": published,
            "lowest_hkd": round(min(lows), 2) if lows else None,
            "bid_hkd": None,
            "match_count": decision.get("match_count") or 0,
            "example_url": decision.get("example_url"),
            "listings": used[:20],
            "bid_listings": [],
            "backends": backends,
            "backend": "+".join(backends) if backends else None,
            "error": None if published is not None else "no confident HK sell ask",
        }

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
