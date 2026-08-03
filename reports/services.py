from datetime import date, timedelta
from calendar import monthrange


def default_date_range(days: int = 90):
    end = date.today()
    start = end - timedelta(days=days)
    return start, end


def month_starts(start: date, end: date):
    """Yield first-of-month dates covering [start, end]."""
    cur = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cur <= last:
        yield cur
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


def month_label(d: date) -> str:
    return d.strftime("%b %Y")


def days_in_month(d: date) -> int:
    return monthrange(d.year, d.month)[1]


def clamp_range(start: date | None, end: date | None, default_days: int = 90):
    if not start or not end:
        return default_date_range(default_days)
    if start > end:
        start, end = end, start
    return start, end
