"""Helpers for matching official TRACES Form 16 PDFs to employees."""
from __future__ import annotations

import re
from datetime import date

from django.utils import timezone

PAN_IN_FILENAME_RE = re.compile(r"([A-Z]{5}[0-9]{4}[A-Z])", re.IGNORECASE)


def parse_financial_year(fy: str) -> tuple[date, date, str, str]:
    """
    '2025-26' -> (2025-04-01, 2026-03-31, AY '2026-27', FY label '2025-26').
    """
    raw = (fy or "").strip().replace("/", "-")
    m = re.match(r"^(\d{4})\s*-\s*(\d{2}|\d{4})$", raw)
    if not m:
        today = timezone.localdate()
        start_year = today.year if today.month >= 4 else today.year - 1
    else:
        start_year = int(m.group(1))
        end_part = m.group(2)
        if len(end_part) == 4:
            end_year = int(end_part)
        else:
            end_year = start_year + 1
        if end_year != start_year + 1:
            end_year = start_year + 1

    fy_start = date(start_year, 4, 1)
    fy_end = date(start_year + 1, 3, 31)
    ay = f"{start_year + 1}-{str(start_year + 2)[-2:]}"
    fy_label = f"{start_year}-{str(start_year + 1)[-2:]}"
    return fy_start, fy_end, ay, fy_label


def extract_pan_from_filename(name: str) -> str | None:
    stem = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    m = PAN_IN_FILENAME_RE.search(stem.upper())
    return m.group(1).upper() if m else None
