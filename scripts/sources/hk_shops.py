"""Public HK shop asks: LONO category pages and Zenox JP booster boxes.

Facebook Marketplace is probed once and recorded. This worker gets HTTP 400
with no listing HTML; there is no logged-in session and no login bypass.
"""
from __future__ import annotations

import re
from typing import Any

from ._http import polite_get
from .hk_match import match_item

LONO_PATHS = (
    "/categories/psa-ptcg",
    "/categories/pokemon-tcg",
)
ZENOX_JP_BOXES = (
    "https://www.zenoxstore.com/collections/booster-packs-collection-box-jp/products.json?limit=250"
)
FACEBOOK_PROBE = "https://www.facebook.com/marketplace/hongkong/search/?query=pokemon%20psa10"

_lono_cache: list[dict] | None = None
_zenox_cache: list[dict] | None = None
_lono_error: str | None = None
_zenox_error: str | None = None

_LONO_CARD = re.compile(
    r'class="title text-primary-color\s*"[^>]*>\s*([^<]+?)\s*</div>'
    r'.*?<span class="[^"]*sl-price price[^"]*"[^>]*>\s*HK\$([\d,]+(?:\.\d+)?)',
    re.S,
)


def _unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("\u0026amp;", "&")
        .strip()
    )


def parse_lono_cards(html: str) -> list[dict]:
    rows: list[dict] = []
    for title, price_s in _LONO_CARD.findall(html):
        title = _unescape(re.sub(r"\s+", " ", title))
        try:
            price = float(price_s.replace(",", ""))
        except ValueError:
            continue
        if price <= 0 or not title:
            continue
        rows.append({"card_name": title, "price": price, "source": "lono", "id": title})
    return rows


def _fetch_lono(min_interval: float) -> tuple[list[dict], str | None]:
    global _lono_cache, _lono_error
    if _lono_cache is not None:
        return _lono_cache, _lono_error
    rows: list[dict] = []
    seen: set[tuple[str, float]] = set()
    err: str | None = None
    for path in LONO_PATHS:
        for page in range(1, 11):
            url = f"https://www.lono.com.hk{path}"
            try:
                resp = polite_get(
                    url,
                    params={"page": str(page)},
                    headers={"Accept-Language": "zh-HK,en;q=0.8"},
                    min_interval=min_interval,
                    timeout=30,
                )
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                break
            if resp.status_code != 200:
                err = f"HTTP {resp.status_code} {path} p{page}"
                break
            batch = parse_lono_cards(resp.text)
            added = 0
            for row in batch:
                key = (row["card_name"], float(row["price"]))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
                added += 1
            if added == 0 or len(batch) < 8:
                break
    _lono_cache = rows
    _lono_error = None if rows else (err or "empty LONO catalog")
    return _lono_cache, _lono_error


def _fetch_zenox(min_interval: float) -> tuple[list[dict], str | None]:
    global _zenox_cache, _zenox_error
    if _zenox_cache is not None:
        return _zenox_cache, _zenox_error
    try:
        resp = polite_get(
            ZENOX_JP_BOXES,
            headers={"Accept": "application/json"},
            min_interval=min_interval,
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        _zenox_cache = []
        _zenox_error = f"{type(e).__name__}: {e}"
        return _zenox_cache, _zenox_error
    if resp.status_code != 200:
        _zenox_cache = []
        _zenox_error = f"HTTP {resp.status_code}"
        return _zenox_cache, _zenox_error
    try:
        payload = resp.json()
    except ValueError:
        _zenox_cache = []
        _zenox_error = "Zenox products.json was not JSON"
        return _zenox_cache, _zenox_error
    products = payload.get("products") if isinstance(payload, dict) else None
    rows: list[dict] = []
    if isinstance(products, list):
        for product in products:
            if not isinstance(product, dict):
                continue
            title = str(product.get("title") or "")
            variants = product.get("variants")
            price = None
            if isinstance(variants, list):
                for variant in variants:
                    if not isinstance(variant, dict):
                        continue
                    try:
                        price = float(variant.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if price > 0:
                        break
            if price is None or not title:
                continue
            rows.append(
                {
                    "card_name": title,
                    "price": price,
                    "source": "zenox",
                    "id": product.get("id"),
                }
            )
    _zenox_cache = rows
    _zenox_error = None if rows else "empty Zenox JP box catalog"
    return _zenox_cache, _zenox_error


def prefetch_shops(*, min_interval: float) -> dict[str, Any]:
    lono_rows, lono_err = _fetch_lono(min_interval)
    zenox_rows, zenox_err = _fetch_zenox(min_interval)
    return {
        "lono": {"catalog_size": len(lono_rows), "error": lono_err},
        "zenox": {"catalog_size": len(zenox_rows), "error": zenox_err},
    }


def match_shop(
    source: str,
    item: dict,
    *,
    min_interval: float,
) -> dict[str, Any]:
    if source == "lono":
        catalog, err = _fetch_lono(min_interval)
    elif source == "zenox":
        catalog, err = _fetch_zenox(min_interval)
    else:
        catalog, err = [], f"unknown shop {source}"
    hits = match_item(catalog, item)
    return {
        "ok": bool(hits),
        "asks_hkd": [h["price_hkd"] for h in hits],
        "listings": hits[:12],
        "error": None if hits else err,
        "status": "ok" if hits else ("empty" if catalog else "error"),
        "catalog_size": len(catalog),
    }


def probe_facebook(*, min_interval: float) -> dict[str, Any]:
    """One public request. Do not log in or bypass a wall."""
    note = (
        "Facebook Marketplace/login HTML is not reachable from this worker "
        "(no logged-in browser; login walls are not bypassed)."
    )
    try:
        resp = polite_get(
            FACEBOOK_PROBE,
            headers={"Accept-Language": "zh-HK,en;q=0.8"},
            min_interval=min_interval,
            timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "enabled": True,
            "status": "unreachable",
            "ok_items": 0,
            "listings": 0,
            "http_status": None,
            "note": f"{note} {type(e).__name__}: {e}",
        }
    body = resp.text[:500].lower()
    usable = resp.status_code == 200 and "marketplace" in body and "error" not in resp.text[:200].lower()
    return {
        "enabled": True,
        "status": "ok" if usable else "unreachable",
        "ok_items": 0,
        "listings": 0,
        "http_status": resp.status_code,
        "note": note if not usable else "Public Marketplace HTML returned.",
    }
