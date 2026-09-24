"""Public HK shop asks: LONO, ShipMyToy, and Zenox.

Sell prices only. Pack-sized prices on a booster-box card are not the box ask.
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
ZENOX_PSA = (
    "https://www.zenoxstore.com/collections/pokemon-psa/products.json?limit=250"
)
SHIPMYTOY_PATH = "/categories/pokemon-tcg"
FACEBOOK_PROBE = "https://www.facebook.com/marketplace/hongkong/search/?query=pokemon%20psa10"

_lono_cache: list[dict] | None = None
_zenox_cache: list[dict] | None = None
_shipmytoy_cache: list[dict] | None = None
_lono_error: str | None = None
_zenox_error: str | None = None
_shipmytoy_error: str | None = None

def _unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("\u0026amp;", "&")
        .strip()
    )


_SHOPLINE_TITLE = re.compile(
    r'class="title text-primary-color\s*"[^>]*>\s*([^<]+?)\s*</div>'
)
_SOLD = re.compile(r"售完|售罄|sold\s*out", re.I)
_PSA10_LABEL = re.compile(r"psa\s*10(?!\d)", re.I)
_OTHER_GRADE = re.compile(r"psa\s*[1-9](?!\d)", re.I)


def sell_price(title: str, prices: list[float]) -> float | None:
    """Lowest current sell price. Ignore a pack price sitting under a box price."""
    vals = sorted(p for p in prices if p > 0)
    if not vals:
        return None
    if len(vals) >= 2 and min(vals) < max(vals) * 0.4:
        vals = [p for p in vals if p >= max(vals) * 0.4]
    return min(vals)


def parse_shopline_cards(html: str, source: str, *, origin: str = "") -> list[dict]:
    found = list(_SHOPLINE_TITLE.finditer(html))
    rows: list[dict] = []
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else match.end() + 1500
        chunk = html[match.end():end]
        if _SOLD.search(chunk):
            continue
        title = _unescape(re.sub(r"\s+", " ", match.group(1)))
        prices: list[float] = []
        for raw in re.findall(r"HK\$([\d,]+(?:\.\d+)?)", chunk):
            try:
                prices.append(float(raw.replace(",", "")))
            except ValueError:
                continue
        price = sell_price(title, prices)
        if price is None or not title:
            continue
        url = _product_url_before(html, match.start(), origin)
        rows.append(
            {
                "card_name": title,
                "price": price,
                "source": source,
                "id": title,
                "url": url,
            }
        )
    return rows


def _product_url_before(html: str, title_start: int, origin: str) -> str | None:
    """Product link sits above the title, not in the next card."""
    window = html[max(0, title_start - 1500):title_start]
    found = list(re.finditer(r'href="([^"]*?/products/[^"#?]+)', window))
    if not found:
        return None
    path = found[-1].group(1)
    if path.startswith("http"):
        return path
    if not origin:
        return None
    return origin.rstrip("/") + "/" + path.lstrip("/")


def parse_lono_cards(html: str) -> list[dict]:
    return parse_shopline_cards(html, "lono", origin="https://www.lono.com.hk")


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


def _variant_label(variant: dict) -> str:
    return " ".join(
        str(variant.get(key) or "")
        for key in ("title", "option1", "option2", "option3")
    )


def _available_price(variant: dict) -> float | None:
    if not variant.get("available", True):
        return None
    try:
        price = float(variant.get("price"))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def parse_zenox_products(payload: Any, *, graded: bool) -> list[dict]:
    products = payload.get("products") if isinstance(payload, dict) else None
    rows: list[dict] = []
    if not isinstance(products, list):
        return rows
    for product in products:
        if not isinstance(product, dict):
            continue
        title = str(product.get("title") or "").strip()
        variants = product.get("variants")
        if not title or not isinstance(variants, list):
            continue
        prices: list[float] = []
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            price = _available_price(variant)
            if price is None:
                continue
            if graded:
                label = _variant_label(variant)
                if not _PSA10_LABEL.search(label) or _OTHER_GRADE.search(label):
                    continue
            prices.append(price)
        chosen = sell_price(title, prices)
        if chosen is None:
            continue
        card_name = title if not graded or _PSA10_LABEL.search(title) else f"{title} PSA10"
        handle = str(product.get("handle") or "").strip()
        rows.append(
            {
                "card_name": card_name,
                "price": chosen,
                "source": "zenox",
                "id": product.get("id"),
                "url": f"https://www.zenoxstore.com/products/{handle}" if handle else None,
            }
        )
    return rows


def _fetch_json(url: str, *, min_interval: float) -> tuple[Any, str | None]:
    try:
        resp = polite_get(
            url,
            headers={"Accept": "application/json"},
            min_interval=min_interval,
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    try:
        return resp.json(), None
    except ValueError:
        return None, "response was not JSON"


def _fetch_zenox(min_interval: float) -> tuple[list[dict], str | None]:
    global _zenox_cache, _zenox_error
    if _zenox_cache is not None:
        return _zenox_cache, _zenox_error
    rows: list[dict] = []
    errors: list[str] = []
    for url, graded in ((ZENOX_JP_BOXES, False), (ZENOX_PSA, True)):
        payload, err = _fetch_json(url, min_interval=min_interval)
        if err:
            errors.append(err)
            continue
        rows.extend(parse_zenox_products(payload, graded=graded))
    _zenox_cache = rows
    _zenox_error = None if rows else ("; ".join(errors) or "empty Zenox catalog")
    return _zenox_cache, _zenox_error


def _fetch_shipmytoy(min_interval: float) -> tuple[list[dict], str | None]:
    global _shipmytoy_cache, _shipmytoy_error
    if _shipmytoy_cache is not None:
        return _shipmytoy_cache, _shipmytoy_error
    rows: list[dict] = []
    seen: set[tuple[str, float]] = set()
    err: str | None = None
    for page in range(1, 7):
        try:
            resp = polite_get(
                f"https://www.shipmytoy.com.hk{SHIPMYTOY_PATH}",
                params={"page": str(page)},
                headers={"Accept-Language": "zh-HK,en;q=0.8"},
                min_interval=min_interval,
                timeout=30,
            )
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            break
        if resp.status_code != 200:
            err = f"HTTP {resp.status_code} p{page}"
            break
        batch = parse_shopline_cards(
            resp.text, "shipmytoy", origin="https://www.shipmytoy.com.hk"
        )
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
    _shipmytoy_cache = rows
    _shipmytoy_error = None if rows else (err or "empty ShipMyToy catalog")
    return _shipmytoy_cache, _shipmytoy_error


def prefetch_shops(*, min_interval: float) -> dict[str, Any]:
    lono_rows, lono_err = _fetch_lono(min_interval)
    zenox_rows, zenox_err = _fetch_zenox(min_interval)
    ship_rows, ship_err = _fetch_shipmytoy(min_interval)
    return {
        "lono": {"catalog_size": len(lono_rows), "error": lono_err},
        "zenox": {"catalog_size": len(zenox_rows), "error": zenox_err},
        "shipmytoy": {"catalog_size": len(ship_rows), "error": ship_err},
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
    elif source == "shipmytoy":
        catalog, err = _fetch_shipmytoy(min_interval)
    else:
        catalog, err = [], f"unknown shop {source}"
    hits = match_item(catalog, item)
    return {
        "ok": bool(hits),
        "asks_hkd": [h["price_hkd"] for h in hits],
        "listings": hits,
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
