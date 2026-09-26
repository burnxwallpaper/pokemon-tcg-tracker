"""Windows for 1日 / 7日 / 30日 must stay distinct and stay empty when history is short."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from price_windows import change_windows  # noqa: E402


def _point(day: str, price: float, ask: float | None = None) -> dict:
    return {"date": day, "price_hkd": price, "hk_ask_hkd": ask, "volume": 1.0}


def test_today_only_is_blank_not_zero() -> None:
    short, med, long = change_windows([_point("2026-09-25", 1000)], today="2026-09-25", current=1000)
    assert short is None
    assert med is None
    assert long is None


def test_missing_price_is_blank() -> None:
    assert change_windows([_point("2026-09-24", 1000)], today="2026-09-25", current=None) == (None, None, None)


def test_one_day_uses_yesterday_and_seven_day_stays_blank() -> None:
    history = [_point("2026-09-24", 800), _point("2026-09-25", 1000)]
    short, med, long = change_windows(history, today="2026-09-25", current=1000)
    assert short == 25.0
    assert med is None
    assert long is None


def test_last_sale_before_today_within_three_days() -> None:
    history = [_point("2026-09-23", 500), _point("2026-09-25", 550)]
    short, med, long = change_windows(history, today="2026-09-25", current=550)
    assert short == 10.0
    assert med is None
    assert long is None


def test_four_day_gap_is_one_day_not_seven_day() -> None:
    history = [_point("2026-09-21", 1237.5), _point("2026-09-25", 1237.5)]
    short, med, long = change_windows(history, today="2026-09-25", current=1237.5)
    assert short == 0.0
    assert med is None
    assert long is None


def test_seven_day_does_not_reuse_the_one_day_sale() -> None:
    history = [
        _point("2026-08-01", 100),
        _point("2026-09-24", 200),
        _point("2026-09-25", 220),
    ]
    short, med, long = change_windows(history, today="2026-09-25", current=220)
    assert short == 10.0
    assert med is None
    assert long is None


def test_seven_day_uses_the_week_ago_sale() -> None:
    history = [
        _point("2026-09-18", 400),
        _point("2026-09-24", 500),
        _point("2026-09-25", 450),
    ]
    short, med, long = change_windows(history, today="2026-09-25", current=450)
    assert short == -10.0
    assert med == 12.5
    assert long is None


def test_same_price_is_a_real_zero() -> None:
    history = [_point("2026-09-18", 100), _point("2026-09-24", 100), _point("2026-09-25", 100)]
    assert change_windows(history, today="2026-09-25", current=100) == (0.0, 0.0, None)


def test_week_old_sale_is_not_also_the_one_day_change() -> None:
    history = [_point("2026-09-18", 80), _point("2026-09-25", 100)]
    short, med, long = change_windows(history, today="2026-09-25", current=100)
    assert short is None
    assert med == 25.0
    assert long is None


def test_thirty_day_stays_distinct_from_nearer_windows() -> None:
    history = [
        _point("2026-08-25", 100),
        _point("2026-09-18", 150),
        _point("2026-09-24", 180),
        _point("2026-09-25", 200),
    ]
    short, med, long = change_windows(history, today="2026-09-25", current=200)
    assert short == 11.11
    assert med == 33.33
    assert long == 100.0


def test_thirty_day_accepts_a_sale_within_two_weeks_before_the_target() -> None:
    history = [
        _point("2026-08-15", 80),
        _point("2026-09-10", 90),
        _point("2026-09-25", 100),
    ]
    short, med, long = change_windows(history, today="2026-09-25", current=100)
    assert short is None
    assert med is None
    assert long == 25.0


def test_thirty_day_does_not_reuse_a_sale_outside_its_window() -> None:
    history = [
        _point("2026-08-01", 50),
        _point("2026-09-10", 80),
        _point("2026-09-24", 90),
        _point("2026-09-25", 100),
    ]
    short, med, long = change_windows(history, today="2026-09-25", current=100)
    assert short == 11.11
    assert med is None
    assert long is None


def test_ask_is_not_a_sold_price() -> None:
    history = [
        {"date": "2026-09-24", "price_hkd": None, "hk_ask_hkd": 999},
        _point("2026-09-25", 100, ask=100),
    ]
    assert change_windows(history, today="2026-09-25", current=100) == (None, None, None)


if __name__ == "__main__":
    test_today_only_is_blank_not_zero()
    test_missing_price_is_blank()
    test_one_day_uses_yesterday_and_seven_day_stays_blank()
    test_last_sale_before_today_within_three_days()
    test_four_day_gap_is_one_day_not_seven_day()
    test_seven_day_does_not_reuse_the_one_day_sale()
    test_seven_day_uses_the_week_ago_sale()
    test_same_price_is_a_real_zero()
    test_week_old_sale_is_not_also_the_one_day_change()
    test_thirty_day_stays_distinct_from_nearer_windows()
    test_thirty_day_accepts_a_sale_within_two_weeks_before_the_target()
    test_thirty_day_does_not_reuse_a_sale_outside_its_window()
    test_ask_is_not_a_sold_price()
    print("ok")
