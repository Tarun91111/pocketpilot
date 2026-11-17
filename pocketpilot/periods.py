"""Turn phrases like "last weekend" into a (start, end) datetime range."""

from __future__ import annotations

import re
from datetime import datetime, timedelta


def _day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_period(text: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    today = _day(now)
    t = text.lower().strip()

    if t in ("today", ""):
        return today, now
    if t == "yesterday":
        return today - timedelta(days=1), today
    if "weekend" in t:
        # Most recent full Sat-Sun before today (this weekend if today is Mon+).
        days_since_sat = (today.weekday() - 5) % 7
        sat = today - timedelta(days=days_since_sat)
        if sat + timedelta(days=2) > now:  # weekend still in progress
            if "last" in t or "past" in t:
                sat -= timedelta(days=7)
            else:
                return sat, now
        return sat, sat + timedelta(days=2)
    if t in ("this week",):
        return today - timedelta(days=today.weekday()), now
    if t in ("last week", "past week"):
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=7)
    if t in ("this month",):
        return today.replace(day=1), now
    if t in ("last month", "past month"):
        first = today.replace(day=1)
        start = (first - timedelta(days=1)).replace(day=1)
        return start, first
    m = re.search(r"(\d+)\s*(day|week|month)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return today - timedelta(days=days - 1), now
    raise ValueError(f"I don't understand the time period '{text}'")
