"""Series history I/O — append/merge by date (never wipe prior real points)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "data" / "history" / "series"
CATALOG_DIR = ROOT / "data" / "catalog"
CATALOG_PATH = CATALOG_DIR / "watchlist.json"


def load_series_doc(item_id: str) -> dict[str, Any]:
    path = SERIES_DIR / f"{item_id}.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_series_points(item_id: str) -> list[dict]:
    """Load prior real history points (drops sample-only series with no real_points)."""
    doc = load_series_doc(item_id)
    if not doc:
        return []
    if doc.get("is_sample") and not doc.get("real_points"):
        return []
    hist = doc.get("history") or []
    return [p for p in hist if isinstance(p, dict) and p.get("date")]


def merge_history_by_date(
    prior: list[dict],
    incoming: list[dict],
    *,
    prefer_incoming: bool = True,
    history_days: int | None = None,
) -> list[dict]:
    """Merge daily points keyed by ``date``.

    - Prior real points are never dropped solely because a re-run missed that day.
    - Same date: incoming overwrites price/volume when prefer_incoming (fresh scrape),
      but preserves prior ``hk_ask_hkd`` if incoming has null.
    - Optionally trim to last ``history_days`` calendar span by keeping the newest N dates.
    """
    by_date: dict[str, dict] = {}
    for p in prior:
        d = p.get("date")
        if not d:
            continue
        by_date[d] = dict(p)

    for p in incoming:
        d = p.get("date")
        if not d:
            continue
        if d not in by_date:
            by_date[d] = dict(p)
            continue
        old = by_date[d]
        if prefer_incoming:
            merged = dict(old)
            for k, v in p.items():
                if k == "hk_ask_hkd" and v is None and old.get("hk_ask_hkd") is not None:
                    continue
                if v is not None or k not in merged:
                    merged[k] = v
            # If incoming has price, take it; keep old hk_ask if needed
            if merged.get("hk_ask_hkd") is None and old.get("hk_ask_hkd") is not None:
                merged["hk_ask_hkd"] = old["hk_ask_hkd"]
            by_date[d] = merged
        else:
            # Only fill gaps
            merged = dict(p)
            merged.update({k: v for k, v in old.items() if v is not None})
            by_date[d] = merged

    dates = sorted(by_date.keys())
    if history_days is not None and history_days > 0 and len(dates) > history_days:
        dates = dates[-history_days:]
    return [by_date[d] for d in dates]


def write_series_merged(
    item: dict,
    meta: dict,
    *,
    history_days: int | None = None,
    extra: dict | None = None,
) -> Path:
    """Merge item['history'] into on-disk series and write. Returns path."""
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    iid = item["id"]
    prior_doc = load_series_doc(iid)
    prior_hist = load_series_points(iid)
    incoming = [p for p in (item.get("history") or []) if isinstance(p, dict) and p.get("date")]
    merged = merge_history_by_date(
        prior_hist, incoming, prefer_incoming=True, history_days=history_days
    )

    doc = {
        "id": iid,
        "name_zh": item.get("name_zh") or prior_doc.get("name_zh"),
        "name_jp": item.get("name_jp") or prior_doc.get("name_jp"),
        "kind": item.get("kind") or prior_doc.get("kind"),
        "set": item.get("set") or prior_doc.get("set"),
        "image": item.get("image") or prior_doc.get("image"),
        "image_source": "official" if item.get("image") else prior_doc.get("image_source"),
        "tcgdex_id": item.get("tcgdex_id") or prior_doc.get("tcgdex_id"),
        "is_sample": False,
        "real_points": True,
        "history_days": len(merged),
        "updated_at": meta.get("updated_at"),
        "history": merged,
    }
    if prior_doc.get("backfill") and not (extra or {}).get("backfill"):
        doc["backfill"] = prior_doc["backfill"]
    if extra:
        doc.update({k: v for k, v in extra.items() if v is not None})

    path = SERIES_DIR / f"{iid}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Reflect merged history back onto item for latest.json consistency
    item["history"] = merged
    return path


def _load_catalog_item(item_id: str) -> dict[str, Any]:
    path = CATALOG_DIR / f"{item_id}.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_catalog_item(
    wl: dict,
    item: dict | None = None,
    meta: dict | None = None,
) -> Path:
    """Upsert durable per-id catalog entry (names, official image, tcgdex ids).

    Missing keys keep the previous value. An explicit null or empty official
    URL, tcgdex id, or search alias clears that field so a wrong face or
    alias cannot stick.
    """
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    iid = wl["id"]
    old = _load_catalog_item(iid)
    it = item or {}
    meta = meta or {}

    def field(key: str):
        if key in wl:
            value = wl.get(key)
            if value is None or value == "":
                return None
            return value
        return old.get(key)

    blank_face = "image_official_url" in wl and not wl.get("image_official_url")
    if blank_face:
        image = None
        image_url = None
    else:
        image = it.get("image") or old.get("image")
        image_url = field("image_official_url") or field("official_image")
    tcgdex_id = field("tcgdex_id")

    # Infer image_source: local official file wins
    image_source = "none" if blank_face else (old.get("image_source") or "none")
    if image and Path(str(image)).name:
        # treat any stored images/{id}.* as official after migration
        image_source = "official"
    elif image_url:
        image_source = old.get("image_source") or "official_url_only"

    hist = it.get("history") or []
    dates = sorted(
        {p.get("date") for p in hist if isinstance(p, dict) and p.get("date")}
        | (
            {old["first_seen"], old["last_seen"]}
            if old.get("first_seen") and old.get("last_seen")
            else set()
        )
    )
    dates = [d for d in dates if d]
    history_points = max(len(hist), int(old.get("history_points") or 0))
    if hist:
        history_points = max(history_points, len(hist))

    doc = {
        "id": iid,
        "name_zh": field("name_zh"),
        "name_jp": field("name_jp"),
        "name_en": field("name_en"),
        "kind": field("kind"),
        "set": field("set"),
        "search_jp": field("search_jp"),
        "search_hk": field("search_hk"),
        "tcgdex_id": tcgdex_id,
        "image": image,
        "image_official_url": image_url,
        "image_note": field("image_note"),
        "image_source": image_source,
        "series_path": f"history/series/{iid}.json",
        "history_points": history_points,
        "first_seen": (dates[0] if dates else old.get("first_seen")),
        "last_seen": (dates[-1] if dates else old.get("last_seen")),
        "updated_at": meta.get("updated_at") or old.get("updated_at"),
    }
    if wl.get("identity_review"):
        doc["identity_review"] = True
    path = CATALOG_DIR / f"{iid}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_catalog(watchlist: list[dict], items: list[dict], meta: dict) -> Path:
    """Write per-id catalog files + aggregate watchlist.json index."""
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    by_id = {it["id"]: it for it in items if it.get("id")}
    entries = []
    for wl in watchlist:
        iid = wl["id"]
        path = write_catalog_item(wl, by_id.get(iid), meta)
        entries.append(json.loads(path.read_text(encoding="utf-8")))

    doc = {
        "updated_at": meta.get("updated_at"),
        "timezone": meta.get("timezone") or meta.get("timezone") or "Asia/Hong_Kong",
        "note": "Stable card identity + official image refs. Series history under history/series/.",
        "image_source": "official",
        "item_count": len(entries),
        "items": entries,
    }
    CATALOG_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CATALOG_PATH
