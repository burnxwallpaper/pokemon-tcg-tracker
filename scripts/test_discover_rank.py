#!/usr/bin/env python3
"""Offline checks for liquidity membership selection."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discover_watchlist import select_membership  # noqa: E402


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
    test_window_count_tie_break()
    print("ok")


if __name__ == "__main__":
    main()
