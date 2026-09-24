"""Shared mild HTTP helpers: browser UA, delay, graceful errors."""
from __future__ import annotations

import time
from typing import Any

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-HK,zh-HK;q=0.9,ja;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

_last_request_at = 0.0


def polite_get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    min_interval: float = 1.5,
    session: requests.Session | None = None,
) -> requests.Response:
    """GET with ≥min_interval gap between calls (mild rate limit)."""
    global _last_request_at
    gap = min_interval - (time.monotonic() - _last_request_at)
    if gap > 0:
        time.sleep(gap)
    hdrs = {**DEFAULT_HEADERS, **(headers or {})}
    sess = session or requests
    resp = sess.get(url, params=params, headers=hdrs, timeout=timeout)
    _last_request_at = time.monotonic()
    return resp


def median(nums: list[float | int]) -> float | None:
    vals = sorted(float(x) for x in nums if x is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def is_cloudflare_block(resp: requests.Response) -> bool:
    if resp.status_code in (403, 503):
        t = resp.text[:800].lower()
        return "just a moment" in t or "cloudflare" in t or "cf-browser-verification" in t
    return False
