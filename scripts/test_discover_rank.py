#!/usr/bin/env python3
"""Offline checks for liquidity membership selection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discover_watchlist import (  # noqa: E402
    append_pinned,
    include_pinned_rows,
    select_membership,
)


def row(i: int, kind: str, total: int, window: int = 0, status: str = "ok") -> dict:
    return {
        "id": f"{kind}-{i:03d}",
        "kind": kind,
        "total_available": total,
        "window_count": window,
        "status": status,
    }


def test_slots_and_cap() -> None:
    psa = [row(i, "psa10", 1000 - i) for i in range(40)]
    sealed = [row(i, "sealed", 5000 - i) for i in range(30)]
    chosen = select_membership(
        psa + sealed, top_n=50, psa10_slots=32, sealed_slots=18, min_closed=1
    )
    assert len(chosen) == 50
    assert sum(1 for r in chosen if r["kind"] == "psa10") == 32
    assert sum(1 for r in chosen if r["kind"] == "sealed") == 18
    assert chosen[0]["kind"] == "sealed"
    assert chosen[0]["total_available"] == 5000
    ids = {r["id"] for r in chosen}
    assert "psa10-032" not in ids  # 33rd PSA (0-index 32) loses the slot
    assert "sealed-018" not in ids


def test_fill_when_one_kind_is_short() -> None:
    psa = [row(i, "psa10", 100 - i) for i in range(40)]
    sealed = [row(i, "sealed", 50 - i) for i in range(10)]
    chosen = select_membership(
        psa + sealed, top_n=50, psa10_slots=32, sealed_slots=18, min_closed=1
    )
    # 32 PSA slots + 10 sealed, then the remaining 8 PSA fill to 50.
    assert len(chosen) == 50
    assert sum(1 for r in chosen if r["kind"] == "sealed") == 10
    assert sum(1 for r in chosen if r["kind"] == "psa10") == 40


def test_skips_errors_and_zero_volume() -> None:
    rows = [
        row(1, "psa10", 10),
        row(2, "psa10", 0),
        row(3, "psa10", 99, status="error"),
        row(4, "sealed", 20),
        {"id": "raw-1", "kind": "raw", "total_available": 9999, "window_count": 0, "status": "ok"},
    ]
    chosen = select_membership(rows, top_n=50, psa10_slots=32, sealed_slots=18, min_closed=1)
    ids = [r["id"] for r in chosen]
    assert ids == ["sealed-004", "psa10-001"]


def test_pin_appended_outside_top_n() -> None:
    rows = [row(i, "psa10", 1000 - i) for i in range(60)]
    chosen = select_membership(
        rows, top_n=50, psa10_slots=32, sealed_slots=18, min_closed=1
    )
    assert len(chosen) == 50
    assert "psa10-059" not in {r["id"] for r in chosen}
    pool = {r["id"]: r for r in rows}
    merged = append_pinned(chosen, pool, ["psa10-059", "psa10-001"])
    assert len(merged) == 51
    assert merged[-1]["id"] == "psa10-059"
    assert [r["id"] for r in merged].count("psa10-001") == 1


def test_liquidity_keeps_pinned_outside_top_n() -> None:
    ranked = [row(i, "psa10", i) for i in range(10)]
    ranked.sort(key=lambda r: -r["total_available"])
    shown = include_pinned_rows(ranked, ["psa10-000"], top_n=3)
    assert [r["id"] for r in shown] == ["psa10-009", "psa10-008", "psa10-007", "psa10-000"]
    again = include_pinned_rows(ranked, ["psa10-009"], top_n=3)
    assert [r["id"] for r in again] == ["psa10-009", "psa10-008", "psa10-007"]


def test_van_gogh_pinned_in_config_and_latest() -> None:
    root = Path(__file__).resolve().parent.parent
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert cfg["pinned"] == ["psa10-van-gogh-pikachu"]
    card = next(w for w in cfg["watchlist"] if w["id"] == "psa10-van-gogh-pikachu")
    assert "梵高比卡超" in card["name_zh"]
    assert "ゴッホ" in card["name_jp"]
    assert "Van Gogh" in card["name_en"]
    assert "Grey Felt Hat" in card["name_en"]
    assert card["image_official_url"].startswith("https://www.pokemon.com/")
    seeds = json.loads((root / "scripts" / "liquidity_seeds.json").read_text(encoding="utf-8"))
    assert any(c["id"] == "psa10-van-gogh-pikachu" for c in seeds["candidates"])
    latest = json.loads((root / "data" / "latest.json").read_text(encoding="utf-8"))
    assert any(it["id"] == "psa10-van-gogh-pikachu" for it in latest["items"])
    liq = latest["sections"]["流動性"]
    pinned = next(it for it in liq if it["id"] == "psa10-van-gogh-pikachu")
    assert pinned["name_en"]
    assert pinned["image"]
    image = root / "data" / pinned["image"]
    assert image.is_file() and image.stat().st_size > 5000
    # English names are on the liquidity rows the search box reads.
    assert all(it.get("name_en") for it in liq)


def test_window_count_tie_break() -> None:
    rows = [
        row(1, "psa10", 10, window=1),
        row(2, "psa10", 10, window=5),
    ]
    chosen = select_membership(rows, top_n=50, psa10_slots=32, sealed_slots=18)
    assert [r["id"] for r in chosen] == ["psa10-002", "psa10-001"]


def main() -> None:
    test_slots_and_cap()
    test_fill_when_one_kind_is_short()
    test_skips_errors_and_zero_volume()
    test_pin_appended_outside_top_n()
    test_liquidity_keeps_pinned_outside_top_n()
    test_van_gogh_pinned_in_config_and_latest()
    test_window_count_tie_break()
    print("ok")


if __name__ == "__main__":
    main()
