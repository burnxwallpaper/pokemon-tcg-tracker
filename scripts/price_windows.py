"""Sold-price windows for the 1-day, 7-day, and 30-day columns.

1日 is the current sold price versus the newest sale strictly before today,
when that sale is newer than the 7-day window (the last 6 calendar days:
yesterday, or the last sale before today if yesterday is missing).

7日 is the current sold price versus the newest sale on or before 7 calendar
days ago, when that sale is no more than 3 days older than the target
(today-10 through today-7).

30日 is the current sold price versus the newest sale on or before 30 calendar
days ago, when that sale is no more than 14 days older than the target
(today-44 through today-30). The longer slack matches how sparse monthly
sales are; the range still does not meet the 7-day window.

The three date ranges do not overlap. A window with no sale in range is None.
It is never copied from another window and never forced to 0.
"""
from __future__ import annotations

from datetime import date, timedelta

ONE_DAY_MAX_AGE = 6
SEVEN_DAY_LAG = 3
THIRTY_DAY_LAG = 14


def pct_change(curr: float | None, prev: float | None) -> float | None:
    if isinstance(curr, bool) or isinstance(prev, bool):
        return None
    if not isinstance(curr, (int, float)) or not isinstance(prev, (int, float)):
        return None
    prev_f = float(prev)
    if prev_f == 0:
        return None
    return round((float(curr) - prev_f) / prev_f * 100.0, 2)


def _sold_points(history: list[dict]) -> list[tuple[str, float]]:
    by_date: dict[str, float] = {}
    for point in history:
        if not isinstance(point, dict):
            continue
        day = point.get("date")
        raw = point.get("price_hkd")
        if not isinstance(day, str) or isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        price = float(raw)
        if price <= 0:
            continue
        by_date[day] = price
    return [(day, by_date[day]) for day in sorted(by_date)]


def change_windows(
    history: list[dict],
    *,
    today: str,
    current: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Return (1日 %, 7日 %, 30日 %) from the sold series. Any value may be None."""
    if isinstance(current, bool) or not isinstance(current, (int, float)) or float(current) <= 0:
        return None, None, None
    try:
        today_d = date.fromisoformat(today)
    except ValueError:
        return None, None, None
    prior = [(day, price) for day, price in _sold_points(history) if day < today]
    one_floor = (today_d - timedelta(days=ONE_DAY_MAX_AGE)).isoformat()
    one = [row for row in prior if row[0] >= one_floor]
    seven_target = (today_d - timedelta(days=7)).isoformat()
    seven_floor = (today_d - timedelta(days=7 + SEVEN_DAY_LAG)).isoformat()
    seven = [row for row in prior if seven_floor <= row[0] <= seven_target]
    thirty_target = (today_d - timedelta(days=30)).isoformat()
    thirty_floor = (today_d - timedelta(days=30 + THIRTY_DAY_LAG)).isoformat()
    thirty = [row for row in prior if thirty_floor <= row[0] <= thirty_target]
    prev_1 = one[-1][1] if one else None
    prev_7 = seven[-1][1] if seven else None
    prev_30 = thirty[-1][1] if thirty else None
    sold = float(current)
    return pct_change(sold, prev_1), pct_change(sold, prev_7), pct_change(sold, prev_30)
