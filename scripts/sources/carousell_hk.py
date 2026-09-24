"""Carousell HK asks (PRIMARY) + HKCardLink public JSON fallback.

Carousell is often behind Cloudflare from datacenter IPs. We still try
mild HTML/JSON first; on block, fall back to HKCardLink's public
Supabase REST (anon key from their frontend bundle) — real HK asks in HKD.

Strategy for fallback (mild + reliable):
  - Batch-pull recent active PSA10 / sealed-ish listings (few requests)
  - Match each watchlist keyword client-side (avoids PostgREST statement timeouts)

No Facebook, no paid Apify. ≥1.5s between requests.
"""
from __future__ import annotations

import re
from typing import Any

import requests

from ._http import BROWSER_UA, is_cloudflare_block, median, polite_get

HKCARDLINK_JS = "https://hkcardlink.com/assets/index-WOdeJcRN.js"
HKCARDLINK_HOME = "https://hkcardlink.com/"
SUPABASE_BASE = "https://nhkbjdeidlavovimjueh.supabase.co"

_anon_cache: str | None = None
_js_asset_cache: str | None = None
_catalog_cache: list[dict] | None = None


def _try_carousell(keyword: str, *, min_interval: float) -> dict[str, Any]:
    out: dict[str, Any] = {
        "backend": "carousell_hk",
        "ok": False,
        "asks_hkd": [],
        "median_hkd": None,
        "listings": [],
        "error": None,
        "status": "ok",
    }
    try:
        q = requests.utils.quote(keyword)
        url = f"https://www.carousell.com.hk/search/{q}/"
        resp = polite_get(
            url,
            params={"addRecent": "false", "canChangeKeyword": "false", "sort_by": "3"},
            headers={"Accept-Language": "zh-HK,en;q=0.8"},
            min_interval=min_interval,
            timeout=20,
        )
        if is_cloudflare_block(resp) or resp.status_code == 403:
            out["status"] = "blocked"
            out["error"] = f"Cloudflare/HTTP {resp.status_code}"
            return out
        if resp.status_code != 200:
            out["status"] = "error"
            out["error"] = f"HTTP {resp.status_code}"
            return out

        text = resp.text
        prices: list[float] = []
        for m in re.finditer(
            r'"price"\s*:\s*"?(?:HK\$|\$)?\s*([\d,]+(?:\.\d+)?)"?', text
        ):
            try:
                prices.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
        for m in re.finditer(r"HK\$\s*([\d,]+(?:\.\d+)?)", text):
            try:
                prices.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
        prices = [p for p in prices if 20 <= p <= 500_000]
        seen: set[float] = set()
        uniq: list[float] = []
        for p in prices:
            key = round(p, 2)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        prices = uniq[:40]
        if not prices:
            out["status"] = "empty"
            out["error"] = "no prices parsed from Carousell HTML"
            return out
        out.update(
            {
                "ok": True,
                "asks_hkd": prices,
                "median_hkd": round(median(prices), 2),
                "listings": [{"price_hkd": p} for p in prices],
                "status": "ok",
            }
        )
        return out
    except Exception as e:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def _discover_hkcardlink_asset() -> str | None:
    global _js_asset_cache
    if _js_asset_cache:
        return _js_asset_cache
    try:
        resp = polite_get(HKCARDLINK_HOME, min_interval=1.2, timeout=20)
        m = re.search(r'src="(/assets/index-[^"]+\.js)"', resp.text)
        if m:
            _js_asset_cache = "https://hkcardlink.com" + m.group(1)
            return _js_asset_cache
    except Exception:
        pass
    return HKCARDLINK_JS


def _hkcardlink_anon_key(*, min_interval: float) -> str | None:
    global _anon_cache
    if _anon_cache:
        return _anon_cache
    asset = _discover_hkcardlink_asset() or HKCARDLINK_JS
    try:
        resp = polite_get(asset, min_interval=min_interval, timeout=35)
        keys = re.findall(
            r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
            resp.text,
        )
        if keys:
            _anon_cache = keys[0]
            return _anon_cache
    except Exception:
        return None
    return None


def _norm(s: str) -> str:
    s = s.lower()
    s = s.replace("　", " ")
    # unify psa10 spellings
    s = re.sub(r"psa\s*10(?:\.0)?", "psa10", s)
    s = re.sub(r"[\s\-_/]+", "", s)
    return s


# Alias map: watchlist tokens → alternate spellings seen on HK marketplaces
_ALIASES: dict[str, list[str]] = {
    "噴火龍": ["charizard", "リザードン", "喷火龙"],
    "皮卡丘": ["pikachu", "ピカチュウ", "比卡超"],
    "夢幻": ["mew", "ミュウ", "梦幻"],
    "耿鬼": ["gengar", "ゲンガー"],
    "月亮伊布": ["umbreon", "ブラッキー", "月伊"],
    "葉伊布": ["leafeon", "リーフィア", "叶伊布"],
    "洛奇亞": ["lugia", "ルギア", "洛奇亚"],
    "烈空坐": ["rayquaza", "レックウザ"],
    "奇樹": ["iono", "ナンジャモ", "奇树"],
    "黑炎": ["黒炎", "blackflame", "sv3"],
    "未來閃光": ["未来の一閃", "futureflash"],
    "古代咆哮": ["古代の咆哮", "ancientroar"],
    "太晶慶典": ["テラスタルフェス", "terastal"],
    "超電": ["超電ブレイカー", "superelectric"],
    "黯夜漫遊者": ["ナイトワンダラー", "nightwanderer"],
    "樂園龍": ["楽園ドラゴーナ", "paradisedragona"],
    "熱浪競技場": ["熱風アリーナ", "heatwave"],
    "伊布英雄": ["イーブイヒーローズ", "eeveeheroes"],
}


def _tokens_for(keyword: str, name_jp: str | None = None, name_zh: str | None = None) -> list[str]:
    raw = " ".join(x for x in [keyword, name_jp or "", name_zh or ""] if x)
    parts = re.split(r"[\s/|+,，、]+", raw)
    tokens: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 2:
            continue
        tokens.append(p)
        for k, alts in _ALIASES.items():
            if k in p or p in k:
                tokens.extend(alts)
            for a in alts:
                if a.lower() == p.lower():
                    tokens.append(k)
                    tokens.extend(alts)
    # unique preserve order
    seen = set()
    out = []
    for t in tokens:
        nt = _norm(t)
        if nt and nt not in seen:
            seen.add(nt)
            out.append(t)
    return out


def _is_psa10_name(name: str, row: dict | None = None) -> bool:
    n = _norm(name)
    if "psa10" in n:
        return True
    if row:
        gc = (row.get("grade_company") or "").upper()
        try:
            score = float(row["grade_score"]) if row.get("grade_score") is not None else None
        except (TypeError, ValueError):
            score = None
        if gc == "PSA" and score is not None and score >= 10:
            return True
    return False


def _is_sealed_name(name: str) -> bool:
    n = name.lower()
    return any(
        t in n
        for t in ("box", "未開封", "シュリンク", "sealed", "原盒", "補充包", "ブースター")
    )


def _fetch_hkcardlink_catalog(*, min_interval: float) -> tuple[list[dict], str | None]:
    """Pull a broad recent catalog (few queries). Cached for process lifetime."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache, None

    anon = _hkcardlink_anon_key(min_interval=min_interval)
    if not anon:
        return [], "could not load HKCardLink anon key"

    headers = {
        "User-Agent": BROWSER_UA,
        "apikey": anon,
        "Authorization": f"Bearer {anon}",
        "Accept": "application/json",
    }
    rows: list[dict] = []
    queries = [
        # Recent PSA10-ish by name
        {
            "select": "id,card_name,price,grade_company,grade_score,status,listing_type,created_at",
            "or": "(card_name.ilike.%PSA 10%,card_name.ilike.%PSA10%)",
            "status": "eq.active",
            "limit": "120",
            "order": "created_at.desc",
        },
        # Graded PSA score=10
        {
            "select": "id,card_name,price,grade_company,grade_score,status,listing_type,created_at",
            "grade_company": "eq.PSA",
            "grade_score": "eq.10",
            "status": "eq.active",
            "limit": "120",
            "order": "created_at.desc",
        },
        # Recent active (catch sealed / Chinese titles without PSA in name)
        {
            "select": "id,card_name,price,grade_company,grade_score,status,listing_type,created_at",
            "status": "eq.active",
            "under_review": "eq.false",
            "limit": "150",
            "order": "created_at.desc",
        },
        # Sealed / BOX asks
        {
            "select": "id,card_name,price,grade_company,grade_score,status,listing_type,created_at",
            "or": "(card_name.ilike.%BOX%,card_name.ilike.%未開封%,card_name.ilike.%原盒%)",
            "status": "eq.active",
            "limit": "80",
            "order": "created_at.desc",
        },
    ]
    err = None
    for params in queries:
        try:
            resp = polite_get(
                f"{SUPABASE_BASE}/rest/v1/listings",
                params=params,
                headers=headers,
                min_interval=min_interval,
                timeout=40,
            )
            if resp.status_code != 200:
                err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                continue
            batch = resp.json()
            if isinstance(batch, list):
                rows.extend(batch)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"

    # Dedup by id
    by_id: dict[str, dict] = {}
    for r in rows:
        rid = r.get("id")
        if rid and rid not in by_id:
            by_id[rid] = r
    _catalog_cache = list(by_id.values())
    return _catalog_cache, err


def _match_catalog(
    catalog: list[dict],
    *,
    keyword: str,
    kind: str,
    name_jp: str | None = None,
    name_zh: str | None = None,
) -> list[dict]:
    tokens = [_norm(t) for t in _tokens_for(keyword, name_jp, name_zh)]
    # Drop ultra-generic TCG tokens that cause false positives
    stop = {
        "psa10", "psa", "sar", "sr", "hr", "ur", "rr", "ar", "ex", "gx", "vmax", "vstar",
        "v", "box", "未開封", "pokemon", "ポケモン", "寶可夢", "ptcg", "tcg", "日版", "jp",
        "japanese", "promo",
    }
    strong = [t for t in tokens if t not in stop and len(t) >= 2]
    if not strong:
        return []

    # Identity tokens: character / set names (CJK ≥2 chars or latin ≥4)
    identity = []
    for t in strong:
        if any("一" <= c <= "鿿" or "぀" <= c <= "ヿ" for c in t):
            if len(t) >= 2:
                identity.append(t)
        elif t.isascii() and len(t) >= 4:
            identity.append(t)
    if not identity:
        identity = [t for t in strong if len(t) >= 3] or strong[:1]

    hits: list[dict] = []
    for row in catalog:
        title = row.get("card_name") or ""
        nt = _norm(title)
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue

        if kind == "psa10" and not _is_psa10_name(title, row):
            continue
        if kind == "sealed" and not (_is_sealed_name(title) or "box" in nt):
            continue

        # Must hit at least one identity token (pokemon / product name)
        id_hits = [t for t in identity if t and t in nt]
        if not id_hits:
            continue
        score = len(id_hits) + sum(1 for t in strong if t not in identity and t in nt)
        hits.append(
            {
                "id": row.get("id"),
                "title": title,
                "price_hkd": price,
                "grade_company": row.get("grade_company"),
                "grade_score": row.get("grade_score"),
                "match_score": score,
            }
        )
    hits.sort(key=lambda x: (-x["match_score"], x["price_hkd"]))
    return hits


def _try_hkcardlink(
    keyword: str,
    *,
    kind: str,
    min_interval: float,
    name_jp: str | None = None,
    name_zh: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "backend": "hkcardlink",
        "ok": False,
        "asks_hkd": [],
        "median_hkd": None,
        "listings": [],
        "error": None,
        "status": "ok",
    }
    catalog, err = _fetch_hkcardlink_catalog(min_interval=min_interval)
    if not catalog:
        out["status"] = "error"
        out["error"] = err or "empty HKCardLink catalog"
        return out

    hits = _match_catalog(
        catalog, keyword=keyword, kind=kind, name_jp=name_jp, name_zh=name_zh
    )
    asks = [h["price_hkd"] for h in hits]
    out.update(
        {
            "ok": bool(asks),
            "asks_hkd": asks,
            "median_hkd": round(median(asks), 2) if asks else None,
            "listings": hits[:20],
            "status": "ok" if asks else "empty",
            "catalog_size": len(catalog),
        }
    )
    if not asks and err:
        out["error"] = err
    return out


def search_asks(
    keyword: str,
    *,
    kind: str = "psa10",
    min_interval: float = 1.6,
    name_jp: str | None = None,
    name_zh: str | None = None,
    try_carousell: bool = True,
) -> dict[str, Any]:
    """HK ask search: Carousell first, HKCardLink catalog match on block/empty."""
    result: dict[str, Any] = {
        "ok": False,
        "source": "carousell_hk",
        "keyword": keyword,
        "backend": None,
        "asks_hkd": [],
        "median_hkd": None,
        "listings": [],
        "error": None,
        "status": "ok",
        "fallback_note": None,
    }

    primary = {"status": "skipped", "error": None, "ok": False}
    if try_carousell:
        primary = _try_carousell(keyword, min_interval=min_interval)
        if primary.get("ok"):
            result.update(
                {
                    "ok": True,
                    "backend": "carousell_hk",
                    "asks_hkd": primary["asks_hkd"],
                    "median_hkd": primary["median_hkd"],
                    "listings": primary["listings"],
                    "status": "ok",
                }
            )
            return result

    fb = _try_hkcardlink(
        keyword,
        kind=kind,
        min_interval=min_interval,
        name_jp=name_jp,
        name_zh=name_zh,
    )
    if primary.get("status") == "skipped":
        result["fallback_note"] = "Carousell skipped after probe block; using HKCardLink catalog"
    else:
        result["fallback_note"] = (
            f"Carousell {primary.get('status')}: {primary.get('error')}; using HKCardLink catalog"
        )
    result["backend"] = "hkcardlink"
    if fb.get("ok"):
        result.update(
            {
                "ok": True,
                "asks_hkd": fb["asks_hkd"],
                "median_hkd": fb["median_hkd"],
                "listings": fb["listings"],
                "status": "ok_fallback",
            }
        )
    else:
        result.update(
            {
                "ok": False,
                "error": fb.get("error") or primary.get("error"),
                "status": "blocked"
                if primary.get("status") == "blocked" and not fb.get("ok")
                else (fb.get("status") or "error"),
            }
        )
    return result


def fetch_watchlist_item(
    item: dict,
    *,
    min_interval: float = 1.6,
    try_carousell: bool = True,
) -> dict[str, Any]:
    kw = item.get("search_hk") or item.get("name_zh") or ""
    out = search_asks(
        kw,
        kind=item.get("kind") or "psa10",
        min_interval=min_interval,
        name_jp=item.get("name_jp"),
        name_zh=item.get("name_zh"),
        try_carousell=try_carousell,
    )
    out["item_id"] = item.get("id")
    return out


def prefetch_carousell_status(*, min_interval: float = 1.6) -> dict[str, Any]:
    """One probe to see if Carousell is reachable; used to skip per-item CF hits."""
    return _try_carousell("PSA10", min_interval=min_interval)
