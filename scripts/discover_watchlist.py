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
eligible. Series files, images, and per-id catalog JSON for ids that drop out
are left on disk (merge-by-date; this script does not delete history).

Writes config.json watchlist + data/catalog/liquidity_rank.json.
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
    return {
        "enabled": bool(raw.get("enabled", True)),
        "refresh_hours": float(raw.get("refresh_hours") or 20),
        "window_days": int(raw.get("window_days") or 14),
        "psa10_slots": psa,
        "sealed_slots": sealed,
        "min_closed": int(raw.get("min_closed") or 1),
        "top_n": top_n,
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
        for key, val in wl.items():
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


def watchlist_entry(cand: dict) -> dict:
    keys = (
        "id",
        "name_zh",
        "name_jp",
        "kind",
        "set",
        "search_jp",
        "search_hk",
        "tcgdex_id",
        "image_official_url",
        "image_note",
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
        "method": "yahoo_closedsearch_totalResultsAvailable",
        "method_note": (
            "Primary liquidity key is Yahoo closedsearch totalResultsAvailable "
            "for each seed keyword (closed comps still indexed, typically ~120 days). "
            "window_count is the number of those comps on the first page (n=20) whose "
            "endTime falls inside window_days; it caps at 20 and only breaks ties. "
            "Membership takes psa10_slots + sealed_slots, then fills toward top_n if one kind is short. "
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
    RANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RANK_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_watchlist(cfg: dict | None = None, *, force: bool = False) -> dict:
    """Probe seeds and rewrite config watchlist when a full ranking succeeds."""
    _stdout_utf8()
    cfg = cfg if cfg is not None else load_config()
    settings = discovery_settings(cfg)
    if not settings["enabled"] and not force:
        print("[discover] disabled in config", flush=True)
        return cfg
    if not force and _rank_is_fresh(settings):
        print("[discover] liquidity rank is fresh; keeping watchlist", flush=True)
        return cfg

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
