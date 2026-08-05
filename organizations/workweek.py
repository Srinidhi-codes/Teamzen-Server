"""Organization work-week helpers (weekend days).

Weekday ints match Python's ``date.weekday()``: Mon=0 … Sun=6.
Default is Sunday-only ``[6]`` to preserve historical leave duration behaviour.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional, Sequence

DEFAULT_WEEKEND_DAYS: tuple[int, ...] = (6,)

WEEKDAY_LABELS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def normalize_weekend_days(raw: Optional[Any]) -> list[int]:
    """Return a sorted unique list of valid weekday ints.

    ``None`` (unset) falls back to Sunday-only. An explicit empty list means
    no weekly offs (every day is a working day unless a holiday).
    """
    if raw is None:
        return list(DEFAULT_WEEKEND_DAYS)
    if not isinstance(raw, (list, tuple)):
        return list(DEFAULT_WEEKEND_DAYS)
    cleaned: set[int] = set()
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            cleaned.add(day)
    return sorted(cleaned)


def get_weekend_days(organization) -> frozenset[int]:
    if organization is None:
        return frozenset(DEFAULT_WEEKEND_DAYS)
    raw = getattr(organization, "weekend_days", None)
    # Distinguishing unset vs empty: DB default after migrate is [6]; empty [] is intentional.
    if raw is None:
        return frozenset(DEFAULT_WEEKEND_DAYS)
    return frozenset(normalize_weekend_days(raw))


def is_org_weekend(day: date, organization) -> bool:
    return day.weekday() in get_weekend_days(organization)


def is_org_working_day(day: date, organization, holiday_dates: Optional[Iterable[date]] = None) -> bool:
    if is_org_weekend(day, organization):
        return False
    if holiday_dates is not None and day in holiday_dates:
        return False
    return True


def validate_weekend_days_input(days: Optional[Sequence[int]]) -> list[int]:
    """Validate mutation input; empty list is allowed (no weekly offs)."""
    if days is None:
        return list(DEFAULT_WEEKEND_DAYS)
    cleaned: set[int] = set()
    for item in days:
        try:
            day = int(item)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid weekend day: {item}")
        if day < 0 or day > 6:
            raise ValueError("Weekend days must be integers 0 (Mon) through 6 (Sun)")
        cleaned.add(day)
    return sorted(cleaned)
