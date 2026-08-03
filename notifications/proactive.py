"""
Shared helpers for Team Pulse digests and burnout/attrition signals.
Used by Celery tasks and LangGraph agent tools.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Sum


PRESENT_STATUSES = ("present", "late_login", "early_logout", "half_day")
MANAGER_ROLES = ("manager", "admin", "hr", "superadmin")

# Burnout thresholds (trailing window)
BURNOUT_WINDOW_DAYS = 14
LATE_THRESHOLD = 4
CORRECTION_THRESHOLD = 2
LEAVE_SPIKE_DAYS = 5


def _prior_week_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start_of_this_week = today - timedelta(days=today.weekday())
    end = start_of_this_week - timedelta(days=1)
    start = end - timedelta(days=6)
    return start, end


def build_team_pulse(
    organization_id: int,
    *,
    manager=None,
    today: date | None = None,
) -> dict[str, Any]:
    """Build a Team Pulse summary for an org (or a manager's team subset)."""
    from django.contrib.auth import get_user_model
    from attendance.models import AttendanceRecord
    from leaves.models import LeaveRequest

    User = get_user_model()
    today = today or date.today()
    start, end = _prior_week_range(today)

    if manager is not None and getattr(manager, "role", None) == "manager":
        team_qs = manager.get_subordinates().filter(is_active=True)
    else:
        team_qs = User.objects.filter(
            organization_id=organization_id, is_active=True, role="employee"
        )

    team_ids = list(team_qs.values_list("id", flat=True))
    headcount = len(team_ids)
    if headcount == 0:
        return {
            "start_date": str(start),
            "end_date": str(end),
            "headcount": 0,
            "present_person_days": 0,
            "attendance_rate": 0.0,
            "pending_leaves": 0,
            "late_offenders": [],
            "message": "No team members found.",
        }

    working_days = 5
    present_person_days = AttendanceRecord.objects.filter(
        user_id__in=team_ids,
        attendance_date__range=[start, end],
        status__in=PRESENT_STATUSES,
    ).count()
    expected = headcount * working_days
    attendance_rate = round((present_person_days / expected) * 100, 1) if expected else 0.0

    pending_leaves = LeaveRequest.objects.filter(
        user_id__in=team_ids,
        _status="pending",
    ).count()

    late_rows = (
        AttendanceRecord.objects.filter(
            user_id__in=team_ids,
            attendance_date__range=[start, end],
            status="late_login",
        )
        .values("user_id")
        .annotate(c=Count("id"))
        .order_by("-c")[:5]
    )
    user_map = {
        u.id: u
        for u in User.objects.filter(id__in=[r["user_id"] for r in late_rows])
    }
    late_offenders = []
    for row in late_rows:
        u = user_map.get(row["user_id"])
        if not u:
            continue
        late_offenders.append(
            {
                "name": f"{u.first_name} {u.last_name}".strip() or u.email,
                "late_count": row["c"],
            }
        )

    message = (
        f"Team Pulse ({start} -> {end}): {attendance_rate}% attendance "
        f"({present_person_days}/{expected} person-days); "
        f"{pending_leaves} pending leave request(s)."
    )
    if late_offenders:
        top = ", ".join(
            f"{o['name']} ({o['late_count']}x late)" for o in late_offenders[:3]
        )
        message += f" Late pattern: {top}."
    return {
        "start_date": str(start),
        "end_date": str(end),
        "headcount": headcount,
        "present_person_days": present_person_days,
        "expected_person_days": expected,
        "attendance_rate": attendance_rate,
        "pending_leaves": pending_leaves,
        "late_offenders": late_offenders,
        "message": message,
    }


def detect_burnout_for_org(
    organization_id: int,
    *,
    manager=None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return flagged employees with burnout/attrition reasons."""
    from django.contrib.auth import get_user_model
    from attendance.models import AttendanceRecord, AttendanceCorrection
    from leaves.models import LeaveRequest

    User = get_user_model()
    today = today or date.today()
    start = today - timedelta(days=BURNOUT_WINDOW_DAYS)

    if manager is not None and getattr(manager, "role", None) == "manager":
        team_qs = manager.get_subordinates().filter(is_active=True)
    else:
        team_qs = User.objects.filter(
            organization_id=organization_id, is_active=True, role="employee"
        )

    signals: list[dict[str, Any]] = []
    for emp in team_qs.select_related("department"):
        reasons = []
        late_count = AttendanceRecord.objects.filter(
            user=emp,
            attendance_date__range=[start, today],
            status="late_login",
        ).count()
        if late_count >= LATE_THRESHOLD:
            reasons.append(f"{late_count} late check-ins")

        correction_count = AttendanceCorrection.objects.filter(
            requested_by=emp,
            created_at__date__range=[start, today],
            reason__icontains="Missed checkout",
        ).count()
        square_off = AttendanceRecord.objects.filter(
            user=emp,
            attendance_date__range=[start, today],
            remarks__icontains="Auto square-off",
        ).count()
        miss_count = max(correction_count, square_off)
        if miss_count >= CORRECTION_THRESHOLD:
            reasons.append(f"{miss_count} missed/square-off checkouts")

        leave_days = (
            LeaveRequest.objects.filter(
                user=emp,
                _status="approved",
                from_date__lte=today,
                to_date__gte=start,
            ).aggregate(total=Sum("duration_days"))["total"]
            or 0
        )
        try:
            leave_days_f = float(leave_days)
        except (TypeError, ValueError):
            leave_days_f = 0.0
        if leave_days_f >= LEAVE_SPIKE_DAYS:
            reasons.append(f"{leave_days_f:g} leave days in {BURNOUT_WINDOW_DAYS}d")

        if reasons:
            signals.append(
                {
                    "user_id": emp.id,
                    "name": f"{emp.first_name} {emp.last_name}".strip() or emp.email,
                    "department": emp.department.name if emp.department_id else None,
                    "reasons": reasons,
                }
            )

    return signals


def format_burnout_message(
    signals: list[dict[str, Any]], window_days: int = BURNOUT_WINDOW_DAYS
) -> str:
    if not signals:
        return f"No burnout/attrition signals in the last {window_days} days."
    lines = [f"Burnout watch ({window_days}d) — {len(signals)} flag(s):"]
    for s in signals[:10]:
        lines.append(f"- {s['name']}: {', '.join(s['reasons'])}")
    if len(signals) > 10:
        lines.append(f"...and {len(signals) - 10} more.")
    return "\n".join(lines)


def notify_telegram_user(user_id: int, html_text: str) -> bool:
    """Send HTML Telegram message if user has a verified active session."""
    return notify_bot_user(user_id, html_text, platforms=["telegram"])


def notify_bot_user(
    user_id: int,
    html_text: str,
    platforms: list[str] | None = None,
) -> bool:
    """
    Fan-out HTML (Telegram) / converted mrkdwn (Slack/WhatsApp) to verified bot sessions.
    Returns True if at least one platform delivered successfully.
    """
    try:
        from bot_gateway.adapters.registry import get_adapter
        from bot_gateway.formatters import format_for_platform
        from bot_gateway.models import BotSession
    except Exception:
        return False

    wanted = platforms or [
        BotSession.PLATFORM_TELEGRAM,
        BotSession.PLATFORM_SLACK,
        BotSession.PLATFORM_WHATSAPP,
    ]
    sessions = (
        BotSession.objects.filter(
            user_id=user_id,
            platform__in=wanted,
            is_verified=True,
        )
        .order_by("-updated_at")
    )
    sent = False
    seen_platforms: set[str] = set()
    for session in sessions:
        if session.platform in seen_platforms:
            continue
        if not session.is_active:
            continue
        seen_platforms.add(session.platform)
        try:
            adapter = get_adapter(session.platform)
            text = format_for_platform(html_text, session.platform)
            result = adapter.send_message(session.chat_id, text)
            if result.get("ok", True):
                sent = True
        except Exception:
            continue
    return sent
