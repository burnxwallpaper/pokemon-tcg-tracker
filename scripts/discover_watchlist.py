#!/usr/bin/env python3
"""Refresh the active watchlist to about top_n by Yahoo closed-auction liquidity.

Candidate pool: scripts/liquidity_seeds.json UNION the current config watchlist
(config fields win when an id already exists, so search strings stay stable).

Rank key (v1):
  1. total_available — Yahoo closedsearch totalResultsAvailable for that
     exact keyword (closed comps still indexed, typically ~120 days).
  2. window_count — comps on the first page (n=20) that ended within
     discovery.window_days. Caps at 20, so it only breaks ties.
  3. id — stable.

Membership: take up to psa10_slots PSA10 and sealed_slots sealed, then fill
toward top_n from the other kind if one side is short. Raw singles are never
eligible. Ids listed in config.pinned are appended after that cut, so a
notable card stays on the watchlist even when it is outside the top 50.
Series files, images, and per-id catalog JSON for ids that drop out are left
on disk (merge-by-date; this script does not delete history).

Writes config.json watchlist + data/catalog/liquidity_rank.json.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from sources.yahoo_auctions_jp import probe_closed_count  # noqa: E402

CONFIG_PATH = ROOT / "config.json"
SEEDS_PATH = SCRIPTS / "liquidity_seeds.json"
RANK_PATH = ROOT / "data" / "catalog" / "liquidity_rank.json"
HK_TZ = timezone(timedelta(hours=8))

ALLOWED_KINDS = ("psa10", "sealed")


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_seeds() -> list[dict]:
    doc = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    rows = doc.get("candidates") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise SystemExit("liquidity_seeds.json missing candidates")
    return [r for r in rows if isinstance(r, dict) and r.get("id")]


def discovery_settings(cfg: dict) -> dict[str, Any]:
    raw = cfg.get("discovery") if isinstance(cfg.get("discovery"), dict) else {}
    top_n = int(cfg.get("top_n") or 50)
    psa = int(raw.get("psa10_slots") or 32)
    sealed = int(raw.get("sealed_slots") or 18)
    psa = max(0, min(psa, top_n))
    sealed = max(0, min(sealed, top_n - psa))
    backend = str(raw.get("backend") or "yahoo").strip().lower()
    return {
        "enabled": bool(raw.get("enabled", True)),
        "backend": backend,
        "refresh_hours": float(raw.get("refresh_hours") or 20),
        "window_days": int(raw.get("window_days") or 14),
        "psa10_slots": psa,
        "sealed_slots": sealed,
        "min_closed": int(raw.get("min_closed") or 1),
        "top_n": top_n,
        "pages": max(1, int(raw.get("pages") or 10)),
        "hottest_brand": str(raw.get("hottest_brand") or "pokemon").strip() or "pokemon",
        "hottest_per_page": max(12, int(raw.get("hottest_per_page") or 48)),
        "min_selected": int(raw.get("min_selected") or (80 if backend == "snkrdunk" else 45)),
        "method": (
            "snkrdunk_hottest_items"
            if backend == "snkrdunk"
            else "yahoo_closedsearch_totalResultsAvailable"
        ),
    }


def merge_candidates(cfg: dict, seeds: list[dict]) -> list[dict]:
    """Seed pool plus current watchlist. Existing config fields overlay seeds."""
    by_id: dict[str, dict] = {}
    for seed in seeds:
        kind = seed.get("kind")
        if kind not in ALLOWED_KINDS:
            continue
        by_id[seed["id"]] = dict(seed)
    for wl in cfg.get("watchlist") or []:
        if not isinstance(wl, dict) or not wl.get("id"):
            continue
        kind = wl.get("kind")
        if kind not in ALLOWED_KINDS:
            continue
        base = dict(by_id.get(wl["id"]) or {})
        clearable = {
            "image_official_url",
            "tcgdex_id",
            "search_jp",
            "search_hk",
            "set",
            "image_note",
        }
        for key, val in wl.items():
            if key in clearable and (val is None or val == ""):
                base[key] = None
                continue
            if val is not None and val != "":
                base[key] = val
        base["id"] = wl["id"]
        base["kind"] = kind
        by_id[wl["id"]] = base
    return [by_id[k] for k in sorted(by_id)]


def select_membership(
    rows: list[dict],
    *,
    top_n: int,
    psa10_slots: int,
    sealed_slots: int,
    min_closed: int = 1,
) -> list[dict]:
    """Pick the active universe. ``rows`` need id, kind, total_available, window_count, status."""
    eligible = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("kind") not in ALLOWED_KINDS:
            continue
        if int(row.get("total_available") or 0) < min_closed:
            continue
        eligible.append(row)

    def sort_key(row: dict) -> tuple:
        return (
            -int(row.get("total_available") or 0),
            -int(row.get("window_count") or 0),
            str(row.get("id") or ""),
        )

    eligible.sort(key=sort_key)
    psa = [r for r in eligible if r["kind"] == "psa10"]
    sealed = [r for r in eligible if r["kind"] == "sealed"]
    chosen = psa[:psa10_slots] + sealed[:sealed_slots]
    chosen_ids = {r["id"] for r in chosen}
    if len(chosen) < top_n:
        for row in eligible:
            if row["id"] in chosen_ids:
                continue
            chosen.append(row)
            chosen_ids.add(row["id"])
            if len(chosen) >= top_n:
                break
    chosen.sort(key=sort_key)
    return chosen[:top_n]


def _rank_is_fresh(settings: dict) -> bool:
    if not RANK_PATH.exists():
        return False
    try:
        doc = json.loads(RANK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not doc.get("applied"):
        return False
    expected = settings.get("method")
    if expected and doc.get("method") != expected:
        return False
    stamp = doc.get("updated_at")
    if not stamp:
        return False
    try:
        updated = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=HK_TZ)
    age = datetime.now(HK_TZ) - updated
    return age < timedelta(hours=settings["refresh_hours"])


def _probe_one(keyword: str, *, interval: float, window_days: int) -> dict:
    res = probe_closed_count(keyword, min_interval=interval, window_days=window_days)
    if res.get("status") in ("blocked", "error", "parse_error"):
        # One polite retry. A hard block should stop the run (caller checks).
        res = probe_closed_count(keyword, min_interval=max(interval, 3.0), window_days=window_days)
    return res


def probe_candidates(
    candidates: list[dict],
    *,
    interval: float,
    window_days: int,
) -> tuple[list[dict], str | None]:
    """Return probe rows. Second value is a fatal status (blocked) if we must stop."""
    rows: list[dict] = []
    for i, cand in enumerate(candidates, 1):
        keyword = cand.get("search_jp") or cand.get("name_jp") or ""
        print(f"  rank {i}/{len(candidates)} {cand['id']}", flush=True)
        res = _probe_one(keyword, interval=interval, window_days=window_days)
        if res.get("status") == "blocked":
            print(f"    blocked: {res.get('error')}", flush=True)
            return rows, "blocked"
        row = {
            "id": cand["id"],
            "kind": cand["kind"],
            "name_zh": cand.get("name_zh"),
            "search_jp": keyword,
            "total_available": int(res.get("total_available") or 0),
            "window_count": int(res.get("window_count") or 0),
            "status": res.get("status") or "error",
            "error": res.get("error"),
        }
        rows.append(row)
        print(
            f"    total={row['total_available']} window={row['window_count']} {row['status']}",
            flush=True,
        )
    return rows, None


def pinned_ids(cfg: dict) -> list[str]:
    """Config pins, in order. Strings or ``{"id": ...}`` objects."""
    raw = cfg.get("pinned") or []
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for row in raw:
        if isinstance(row, str) and row:
            ids.append(row)
        elif isinstance(row, dict) and row.get("id"):
            ids.append(str(row["id"]))
    return ids


def append_pinned(chosen: list[dict], pool: dict[str, dict], pins: list[str]) -> list[dict]:
    """Keep the ranked selection, then add pinned ids that missed the cut."""
    have = {c.get("id") for c in chosen}
    out = list(chosen)
    for pid in pins:
        if not pid or pid in have:
            continue
        cand = pool.get(pid)
        if not isinstance(cand, dict):
            continue
        if cand.get("kind") not in ALLOWED_KINDS:
            continue
        out.append(dict(cand))
        have.add(pid)
    return out


def include_pinned_rows(ranked: list[dict], pins: list[str], top_n: int) -> list[dict]:
    """Liquidity table: top_n by score, plus pinned rows that fell outside it."""
    cap = max(0, int(top_n))
    head = list(ranked[:cap])
    have = {row.get("id") for row in head}
    out = head
    by_id: dict[str, dict] = {}
    for row in ranked:
        iid = row.get("id")
        if iid and iid not in by_id:
            by_id[str(iid)] = row
    for pid in pins:
        if not pid or pid in have:
            continue
        row = by_id.get(pid)
        if row is None:
            continue
        out.append(row)
        have.add(pid)
    return out


def watchlist_entry(cand: dict) -> dict:
    keys = (
        "id",
        "name_zh",
        "name_jp",
        "name_en",
        "kind",
        "set",
        "search_jp",
        "search_hk",
        "tcgdex_id",
        "image_official_url",
        "image_note",
        "identity_review",
        "snkrdunk_apparel_id",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key in cand:
            out[key] = cand[key]
    return out


def write_config_watchlist(cfg: dict, selected_candidates: list[dict]) -> None:
    cfg["watchlist"] = [watchlist_entry(c) for c in selected_candidates]
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_rank_file(
    *,
    settings: dict,
    rows: list[dict],
    selected_ids: list[str],
    applied: bool,
    fatal: str | None,
    now: datetime,
    method: str | None = None,
    method_note: str | None = None,
    extra: dict | None = None,
) -> None:
    selected = set(selected_ids)
    rankings = []
    ordered = sorted(
        rows,
        key=lambda r: (
            -int(r.get("total_available") or 0),
            -int(r.get("window_count") or 0),
            str(r.get("id") or ""),
        ),
    )
    for i, row in enumerate(ordered, 1):
        rankings.append({**row, "rank": i, "selected": row["id"] in selected})
    doc = {
        "updated_at": now.isoformat(timespec="seconds"),
        "timezone": "Asia/Hong_Kong",
        "applied": applied,
        "fatal": fatal,
        "method": method or "yahoo_closedsearch_totalResultsAvailable",
        "method_note": method_note or (
            "Primary liquidity key is Yahoo closedsearch totalResultsAvailable "
            "for each seed keyword (closed comps still indexed, typically ~120 days). "
            "window_count is the number of those comps on the first page (n=20) whose "
            "endTime falls inside window_days; it caps at 20 and only breaks ties. "
            "Membership takes psa10_slots + sealed_slots, then fills toward top_n if one kind is short. "
            "config.pinned ids are kept even when they rank outside top_n. "
            "Ids that leave the active watchlist keep series, images, and per-id catalog files."
        ),
        "window_days": settings["window_days"],
        "top_n": settings["top_n"],
        "psa10_slots": settings["psa10_slots"],
        "sealed_slots": settings["sealed_slots"],
        "min_closed": settings["min_closed"],
        "probed": len(rows),
        "selected_count": len(selected_ids) if applied else 0,
        "selected_ids": selected_ids if applied else [],
        "rankings": rankings,
    }
    if extra:
        doc.update(extra)
    RANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RANK_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def persist_missing_pins(cfg: dict) -> dict:
    """Append config.pinned cards that are not already on the watchlist."""
    pins = pinned_ids(cfg)
    if not pins:
        return cfg
    current = [w for w in (cfg.get("watchlist") or []) if isinstance(w, dict) and w.get("id")]
    have = {w["id"] for w in current}
    if all(pid in have for pid in pins):
        return cfg
    pool = {c["id"]: c for c in merge_candidates(cfg, load_seeds())}
    for row in cfg.get("pinned") or []:
        if isinstance(row, dict) and row.get("id"):
            base = dict(pool.get(row["id"]) or {})
            for key, val in row.items():
                if val is not None and val != "":
                    base[key] = val
            pool[str(row["id"])] = base
    merged = append_pinned(current, pool, pins)
    if [w.get("id") for w in merged] == [w.get("id") for w in current]:
        return cfg
    write_config_watchlist(cfg, merged)
    print(f"[discover] pinned watchlist={len(merged)}", flush=True)
    return load_config()


def _print_key(set_code: str | None, number: str | None) -> str | None:
    if not set_code or not number or not str(number).isdigit():
        return None
    return f"{str(set_code).lower()}:{int(number):03d}"


def watch_print_keys(item: dict) -> set[str]:
    """Set code + collector number, from the set field and from tcgdex id."""
    from sources.jp_match import _item_fraction, _item_set_code

    keys: set[str] = set()
    code = _item_set_code(item)
    frac = _item_fraction(item)
    if code and frac:
        key = _print_key(code, frac[0])
        if key:
            keys.add(key)
    found = re.match(r"([A-Za-z]+\d+[A-Za-z]*)-(\d{2,3})$", str(item.get("tcgdex_id") or ""))
    if found:
        key = _print_key(found.group(1), found.group(2))
        if key:
            keys.add(key)
    return keys


def _sealed_identity(item: dict) -> str:
    from sources.jp_match import _identity

    return _identity(item)


def _index_existing(watchlist: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_print: dict[str, dict] = {}
    sealed_groups: dict[str, list[dict]] = {}
    for item in watchlist:
        if not isinstance(item, dict) or item.get("kind") not in ALLOWED_KINDS:
            continue
        if item.get("kind") == "psa10":
            for key in watch_print_keys(item):
                by_print.setdefault(key, item)
            continue
        ident = _sealed_identity(item)
        if len(ident) >= 4:
            sealed_groups.setdefault(ident, []).append(item)
    sealed_unique = {key: rows[0] for key, rows in sealed_groups.items() if len(rows) == 1}
    return by_print, sealed_unique


def scrub_face(entry: dict) -> dict:
    """Drop a single's official URL when it is not this set and collector number."""
    if entry.get("kind") == "sealed":
        return entry
    url = str(entry.get("image_official_url") or "").strip()
    if not url:
        return entry
    keys = watch_print_keys(entry)
    if not keys:
        return entry
    from sources.snkrdunk import official_face_matches

    out = dict(entry)
    for key in keys:
        code, number = key.split(":", 1)
        if official_face_matches(url, code, number):
            return entry
    out["image_official_url"] = None
    note = str(out.get("image_note") or "")
    if "cleared:" not in note:
        out["image_note"] = (
            (note + "; " if note else "")
            + "cleared: URL does not encode this set and collector number"
        )
    return out


def _reuse_sealed(tile: dict, sealed_unique: dict[str, dict]) -> dict | None:
    from sources.jp_match import _norm

    label = _norm(str(tile.get("label") or ""))
    hits = [(ident, item) for ident, item in sealed_unique.items() if ident and ident in label]
    if not hits:
        return None
    hits.sort(key=lambda pair: len(pair[0]), reverse=True)
    best = len(hits[0][0])
    top = [item for ident, item in hits if len(ident) == best]
    if len(top) != 1:
        return None
    return dict(top[0])


def entry_for_tile(
    tile: dict,
    kind: str,
    by_print: dict[str, dict],
    sealed_unique: dict[str, dict],
    used_ids: set[str],
) -> dict:
    """Reuse a watchlist id for the same print, or mint one from the SNKRDUNK label."""
    apparel_id = str(tile.get("apparel_id") or "")
    reused: dict | None = None
    if kind == "psa10":
        key = _print_key(tile.get("set_code"), tile.get("number"))
        found = by_print.get(key) if key else None
        if found:
            reused = dict(found)
    else:
        reused = _reuse_sealed(tile, sealed_unique)
    if reused and reused.get("id"):
        reused["snkrdunk_apparel_id"] = apparel_id
        used_ids.add(str(reused["id"]))
        return scrub_face(reused)
    label = str(tile.get("label") or "").strip()
    if kind == "psa10":
        code = str(tile.get("set_code") or "card").lower()
        raw_number = str(tile.get("number"))
        number = int(raw_number)
        iid = f"psa10-{code}-{number:03d}"
        if iid in used_ids:
            iid = f"psa10-{code}-{number:03d}-snkr-{apparel_id}"
        set_field = f"{tile.get('set_code')} / {raw_number}"
        denom = tile.get("denom")
        if denom:
            set_field = f"{set_field}/{denom}"
    else:
        iid = f"sealed-snkr-{apparel_id}"
        if iid in used_ids:
            iid = f"sealed-snkr-{apparel_id}-b"
        set_field = ""
    used_ids.add(iid)
    return {
        "id": iid,
        "name_zh": label,
        "name_jp": label,
        "kind": kind,
        "set": set_field,
        "search_jp": label,
        "search_hk": label,
        "snkrdunk_apparel_id": apparel_id,
        "image_official_url": None,
        "image_note": "SNKRDUNK hottest catalog; official face stays empty until the URL encodes this print",
    }


def _attach_van_gogh(chosen: list[dict], *, interval: float) -> None:
    """One extra search so the pinned promo keeps a SNKRDUNK id when it is listed."""
    card = next((row for row in chosen if row.get("id") == "psa10-van-gogh-pikachu"), None)
    if card is None or str(card.get("snkrdunk_apparel_id") or "").isdigit():
        return
    from sources._http import polite_get
    from sources.snkrdunk import SEARCH_URL, parse_tiles

    try:
        resp = polite_get(
            SEARCH_URL,
            params={"keywords": "ゴッホ ピカチュウ"},
            min_interval=interval,
            timeout=25,
            headers={"Accept-Language": "ja,en;q=0.8"},
        )
    except Exception as exc:
        print(f"[discover] van gogh search skipped: {type(exc).__name__}", flush=True)
        return
    if resp.status_code != 200:
        print(f"[discover] van gogh search HTTP {resp.status_code}", flush=True)
        return
    for tile in parse_tiles(resp.text):
        label = str(tile.get("label") or "")
        if "ゴッホ" in label and "ピカチュウ" in label:
            card["snkrdunk_apparel_id"] = str(tile["apparel_id"])
            print(f"[discover] van gogh apparel {card['snkrdunk_apparel_id']}", flush=True)
            return
    print("[discover] van gogh not on the first SNKRDUNK page", flush=True)


def refresh_from_snkrdunk(cfg: dict, settings: dict, *, force: bool = False) -> dict:
    """Replace the watchlist from SNKRDUNK hottest search, up to top_n.

    A short or blocked scrape does not shrink the list. Pinned ids are appended
    after the cap. Series files for ids that drop out stay on disk.
    """
    _stdout_utf8()
    if not settings["enabled"] and not force:
        print("[discover] disabled in config", flush=True)
        return persist_missing_pins(cfg)
    if not force and _rank_is_fresh(settings):
        print("[discover] SNKRDUNK rank is fresh; keeping watchlist", flush=True)
        return persist_missing_pins(cfg)

    from sources.snkrdunk import (
        HOTTEST_HUB,
        catalog_kind,
        collect_brand_hottest,
        collect_brand_search_labels,
        collect_hottest_tiles,
        headline_under_min,
        prepare_brand_hottest,
    )

    interval = float(cfg.get("request_min_interval_sec") or 1.6)
    fx = float(cfg.get("fx_jpy_to_hkd") or 0)
    min_hkd = float(cfg.get("min_list_price_hkd") or 0)
    pages = int(settings["pages"])
    brand = str(settings["hottest_brand"])
    per_page = int(settings["hottest_per_page"])
    print(
        f"[discover] SNKRDUNK Hottest Items brand={brand} × {pages} pages "
        f"(per_page={per_page}, cap={settings['top_n']}, psa10={settings['psa10_slots']}, "
        f"sealed={settings['sealed_slots']}, floor=HK${min_hkd:g}, interval≥{interval}s)",
        flush=True,
    )
    brand_raw = collect_brand_hottest(
        pages=pages,
        min_interval=interval,
        per_page=per_page,
        brand_id=brand,
    )
    print(f"[discover] hottest items hits={len(brand_raw)}", flush=True)
    jp_labels = collect_brand_search_labels(pages=pages, min_interval=interval, brand_id=brand)
    brand_kept, localized = prepare_brand_hottest(
        brand_raw,
        jp_labels,
        fx=fx,
        minimum=min_hkd,
        min_interval=interval,
        localize_cap=int(settings["top_n"]) + 40,
    )
    print(
        f"[discover] hottest items eligible={len(brand_kept)} jp_labels={len(jp_labels)} "
        f"localized={localized}",
        flush=True,
    )
    keyword_tiles = collect_hottest_tiles(pages=pages, min_interval=interval)
    seen_apparel = {str(tile.get("apparel_id") or "") for tile in brand_kept}
    tiles = list(brand_kept)
    for tile in keyword_tiles:
        apparel_id = str(tile.get("apparel_id") or "")
        if not apparel_id or apparel_id in seen_apparel:
            continue
        seen_apparel.add(apparel_id)
        tiles.append(tile)
    print(f"[discover] catalog hits={len(tiles)} (keyword fill={len(tiles) - len(brand_kept)})", flush=True)
    watchlist = [w for w in (cfg.get("watchlist") or []) if isinstance(w, dict)]
    by_print, sealed_unique = _index_existing(watchlist)
    used_ids = {str(w.get("id")) for w in watchlist if w.get("id")}
    rows: list[dict] = []
    entries: dict[str, dict] = {}
    for index, tile in enumerate(tiles):
        kind = catalog_kind(tile)
        if kind not in ALLOWED_KINDS:
            continue
        if headline_under_min(tile, fx=fx, minimum=min_hkd):
            continue
        entry = entry_for_tile(tile, kind, by_print, sealed_unique, used_ids)
        iid = str(entry.get("id") or "")
        if not iid or iid in entries:
            continue
        entries[iid] = entry
        rows.append(
            {
                "id": iid,
                "kind": kind,
                "name_zh": entry.get("name_zh"),
                "search_jp": entry.get("search_jp"),
                "total_available": 100000 - index,
                "window_count": 0,
                "status": "ok",
            }
        )
    now = datetime.now(HK_TZ)
    selected_rows = select_membership(
        rows,
        top_n=settings["top_n"],
        psa10_slots=settings["psa10_slots"],
        sealed_slots=settings["sealed_slots"],
        min_closed=1,
    )
    applied = len(selected_rows) >= int(settings["min_selected"])
    selected_ids: list[str] = []
    if applied:
        chosen = [entries[row["id"]] for row in selected_rows if row["id"] in entries]
        pool = {str(w["id"]): scrub_face(dict(w)) for w in watchlist if w.get("id")}
        for entry in chosen:
            pool[str(entry["id"])] = entry
        chosen = append_pinned(chosen, pool, pinned_ids(cfg))
        _attach_van_gogh(chosen, interval=interval)
        selected_ids = [str(c["id"]) for c in chosen]
        write_config_watchlist(cfg, chosen)
        n_psa = sum(1 for c in chosen if c.get("kind") == "psa10")
        n_sealed = sum(1 for c in chosen if c.get("kind") == "sealed")
        print(
            f"[discover] watchlist={len(chosen)} psa10={n_psa} sealed={n_sealed}",
            flush=True,
        )
    else:
        print(
            f"[discover] not applying (selected={len(selected_rows)}, "
            f"need {settings['min_selected']}); config watchlist unchanged",
            flush=True,
        )
        cfg = persist_missing_pins(cfg)
    selected_apparel = {
        str(entries[iid].get("snkrdunk_apparel_id") or "")
        for iid in selected_ids
        if iid in entries
    }
    eligible_ids = [str(tile.get("apparel_id") or "") for tile in brand_kept]
    first_page_ids = [str(tile.get("apparel_id") or "") for tile in brand_raw[:12]]
    eligible_set = set(eligible_ids)
    first_eligible = [aid for aid in first_page_ids if aid in eligible_set]
    first_selected = [aid for aid in first_eligible if aid in selected_apparel]
    hottest_selected = [aid for aid in eligible_ids if aid in selected_apparel]
    print(
        f"[discover] hottest coverage selected={len(hottest_selected)}/{len(eligible_ids)} "
        f"first_page={len(first_selected)}/{len(first_eligible) or len(first_page_ids)}",
        flush=True,
    )
    write_rank_file(
        settings=settings,
        rows=rows,
        selected_ids=selected_ids,
        applied=applied,
        fatal=None,
        now=now,
        method="snkrdunk_hottest_items",
        method_note=(
            "SNKRDUNK Hottest Items on product pages "
            f"({HOTTEST_HUB}): /en/v1/brands/{brand}/streetwears?department=tradingCard. "
            "That order is the rank. Keyword search sort=hottest fills any slots left under the cap. "
            "HK$ min_list_price_hkd drops a headline under the floor (brand API minPrice is already HKD; "
            "search tiles are yen × fx_jpy_to_hkd). Cap is top_n with psa10_slots and sealed_slots. "
            "Fewer than min_selected hits does not replace the watchlist. "
            "The same set and collector number keeps its existing id and Chinese name. "
            "config.pinned ids stay even outside the cap. "
            "Ids that leave the active watchlist keep series, images, and per-id catalog files."
        ),
        extra={
            "hottest_hub": HOTTEST_HUB,
            "hottest_brand": brand,
            "hottest_fetched": len(brand_raw),
            "hottest_eligible": len(eligible_ids),
            "hottest_selected": len(hottest_selected) if applied else 0,
            "hottest_first_page_ids": first_page_ids,
            "hottest_first_page_eligible": first_eligible,
            "hottest_first_page_selected": first_selected if applied else [],
            "hottest_missed_ids": [
                aid for aid in eligible_ids if aid not in selected_apparel
            ][:40],
        },
    )
    return load_config()


def refresh_watchlist(cfg: dict | None = None, *, force: bool = False) -> dict:
    """Probe seeds and rewrite config watchlist when a full ranking succeeds."""
    _stdout_utf8()
    cfg = cfg if cfg is not None else load_config()
    settings = discovery_settings(cfg)
    if not settings["enabled"] and not force:
        print("[discover] disabled in config", flush=True)
        return persist_missing_pins(cfg)
    if settings["backend"] == "snkrdunk":
        return refresh_from_snkrdunk(cfg, settings, force=force)
    if not force and _rank_is_fresh(settings):
        print("[discover] liquidity rank is fresh; keeping watchlist", flush=True)
        return persist_missing_pins(cfg)

    seeds = load_seeds()
    candidates = merge_candidates(cfg, seeds)
    by_id = {c["id"]: c for c in candidates}
    interval = float(cfg.get("request_min_interval_sec") or 1.6)
    print(
        f"[discover] probing {len(candidates)} PSA10/sealed seeds "
        f"(top_n={settings['top_n']}, psa10={settings['psa10_slots']}, "
        f"sealed={settings['sealed_slots']}, interval≥{interval}s)",
        flush=True,
    )
    rows, fatal = probe_candidates(
        candidates, interval=interval, window_days=settings["window_days"]
    )
    now = datetime.now(HK_TZ)
    selected_rows = []
    applied = False
    if fatal is None:
        selected_rows = select_membership(
            rows,
            top_n=settings["top_n"],
            psa10_slots=settings["psa10_slots"],
            sealed_slots=settings["sealed_slots"],
            min_closed=settings["min_closed"],
        )
        # Require a real expansion band so a partial/blocked scrape cannot
        # freeze the universe back at the old 22-card list.
        applied = len(selected_rows) >= 45
    selected_ids = [r["id"] for r in selected_rows]
    if applied:
        chosen = []
        for row in selected_rows:
            cand = dict(by_id[row["id"]])
            cand["liquidity_total"] = row["total_available"]
            cand["liquidity_window"] = row["window_count"]
            chosen.append(cand)
        chosen = append_pinned(chosen, by_id, pinned_ids(cfg))
        selected_ids = [c["id"] for c in chosen]
        write_config_watchlist(cfg, chosen)
        n_psa = sum(1 for c in chosen if c.get("kind") == "psa10")
        n_sealed = sum(1 for c in chosen if c.get("kind") == "sealed")
        print(
            f"[discover] watchlist={len(chosen)} psa10={n_psa} sealed={n_sealed}",
            flush=True,
        )
    else:
        print(
            f"[discover] not applying (fatal={fatal}, selected={len(selected_rows)}); "
            "config watchlist unchanged",
            flush=True,
        )
        cfg = persist_missing_pins(cfg)
    write_rank_file(
        settings=settings,
        rows=rows,
        selected_ids=selected_ids,
        applied=applied,
        fatal=fatal,
        now=now,
    )
    return load_config()


def main() -> None:
    force = "--force" in sys.argv or "--discover" in sys.argv
    cfg = refresh_watchlist(force=force)
    n = len(cfg.get("watchlist") or [])
    print(f"[discover] active watchlist size={n}", flush=True)
    if n < 45:
        sys.exit(1)


if __name__ == "__main__":
    main()
