"""Ranked Next Best Actions + AI insight cards for dashboards."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, List, Optional

from django.db.models import Count
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceCorrection
from leaves.models import CompanyHoliday, LeaveBalance, LeaveRequest
from users.models import CustomUser


def _insight(
    *,
    title: str,
    message: str,
    type: str,
    query: str,
    path: Optional[str] = None,
    label: Optional[str] = None,
    priority: int = 50,
) -> dict[str, Any]:
    return {
        "title": title,
        "message": message,
        "type": type,
        "query": query,
        "path": path,
        "label": label,
        "priority": priority,
    }


def _onboarding_actions(user) -> List[dict]:
    try:
        from onboarding.models import EmployeeOnboarding
    except Exception:
        return []

    ob = (
        EmployeeOnboarding.objects.prefetch_related("tasks", "documents")
        .filter(user=user)
        .exclude(status="cancelled")
        .first()
    )
    if not ob or ob.status == "completed":
        return []

    open_tasks = [t for t in ob.tasks.all() if t.status not in ("completed", "skipped")]
    rejected = [d for d in ob.documents.all() if d.verification_status == "rejected"]
    pending_docs = [d for d in ob.documents.all() if d.verification_status == "pending"]

    actions = []
    if rejected:
        actions.append(
            _insight(
                title="Documents need a re-upload",
                message=f"{len(rejected)} document(s) were rejected. Fix them on My Onboarding so HR can verify.",
                type="warning",
                query="Which of my onboarding documents were rejected and what should I upload?",
                path="/onboarding",
                label="Fix documents",
                priority=10,
            )
        )
    elif open_tasks:
        next_t = sorted(open_tasks, key=lambda t: (t.sort_order, t.id))[0]
        actions.append(
            _insight(
                title="Finish joining checklist",
                message=f"Next: {next_t.title}. {ob.progress_pct or 0}% complete overall.",
                type="info",
                query="What's left on my onboarding and explain my next task?",
                path="/onboarding",
                label="Open My Onboarding",
                priority=15,
            )
        )
    elif pending_docs:
        actions.append(
            _insight(
                title="Docs awaiting verification",
                message=f"{len(pending_docs)} document(s) are pending HR review.",
                type="info",
                query="What's the status of my onboarding documents?",
                path="/onboarding",
                label="View onboarding",
                priority=25,
            )
        )
    return actions


def _attendance_actions(user) -> List[dict]:
    from organizations.workweek import is_org_weekend

    today = date.today()
    yesterday = today - timedelta(days=1)
    actions = []

    today_rec = (
        AttendanceRecord.objects.filter(user=user, attendance_date=today)
        .order_by("-id")
        .first()
    )
    if not today_rec or not today_rec.login_time:
        # Only nudge on working days during day hours (server local)
        if not is_org_weekend(today, user.organization) and 7 <= timezone.localtime().hour < 20:
            actions.append(
                _insight(
                    title="Check in for today",
                    message="You haven't punched in yet. Open Attendance with location enabled.",
                    type="warning",
                    query="Have I checked in today? Help me mark attendance.",
                    path="/attendance",
                    label="Go to Attendance",
                    priority=12,
                )
            )

    y_rec = (
        AttendanceRecord.objects.filter(user=user, attendance_date=yesterday)
        .order_by("-id")
        .first()
    )
    if y_rec and y_rec.login_time and not y_rec.logout_time:
        actions.append(
            _insight(
                title="Missing checkout yesterday",
                message="Yesterday's attendance has no logout. Square it off with a correction request.",
                type="warning",
                query="List my pending attendance corrections and help me fix yesterday's missing checkout.",
                path="/attendance/attendance-correction",
                label="Request correction",
                priority=11,
            )
        )

    pending_corr = AttendanceCorrection.objects.filter(
        attendance_record__user=user,
        _status="pending",
    ).count()
    if pending_corr:
        actions.append(
            _insight(
                title="Correction awaiting review",
                message=f"You have {pending_corr} attendance correction(s) pending.",
                type="info",
                query="Show my pending attendance corrections.",
                path="/attendance/attendance-correction",
                label="View corrections",
                priority=30,
            )
        )

    total_recs = AttendanceRecord.objects.filter(user=user).count()
    present_recs = AttendanceRecord.objects.filter(
        user=user,
        status__in=["present", "late_login", "early_logout", "half_day"],
    ).count()
    rate = (present_recs / total_recs * 100) if total_recs > 0 else 0
    if total_recs >= 5 and rate < 85:
        actions.append(
            _insight(
                title="Attendance alert",
                message=f"Your attendance rate ({rate:.1f}%) is below the usual benchmark.",
                type="warning",
                query="How can I improve my attendance and what are late login policies?",
                path="/attendance",
                label="View attendance",
                priority=35,
            )
        )
    elif total_recs >= 5:
        actions.append(
            _insight(
                title="Solid attendance",
                message=f"You've kept a {rate:.1f}% attendance rate. Nice consistency.",
                type="stats",
                query="How is my attendance compared to last month?",
                path="/attendance",
                label="View attendance",
                priority=80,
            )
        )

    return actions


def _leave_actions(user) -> List[dict]:
    today = date.today()
    actions = []
    balances = LeaveBalance.objects.filter(user=user, year=today.year).select_related(
        "leave_type"
    )
    for bal in balances:
        available = float(bal.get_available_balance())
        if available > 8 and today.month >= 11:
            actions.append(
                _insight(
                    title="Use your leaves",
                    message=f"You still have {available:g} days of {bal.leave_type.name}. They may expire.",
                    type="info",
                    query=f"Suggest a good window to take {bal.leave_type.name} based on my team.",
                    path="/leaves?action=apply",
                    label="Request leave",
                    priority=40,
                )
            )
            break

    pending = LeaveRequest.objects.filter(user=user, _status="pending").count()
    if pending:
        actions.append(
            _insight(
                title="Leave request pending",
                message=f"You have {pending} leave request(s) waiting for approval.",
                type="info",
                query="Show my pending leave requests.",
                path="/leaves",
                label="View leaves",
                priority=28,
            )
        )

    if user.role in ("manager", "admin", "hr", "superadmin"):
        team_pending = LeaveRequest.objects.filter(
            _status="pending",
            user__manager=user,
        ).count()
        if user.role in ("admin", "hr", "superadmin") and user.organization_id:
            team_pending = max(
                team_pending,
                LeaveRequest.objects.filter(
                    _status="pending",
                    user__organization_id=user.organization_id,
                ).count(),
            )
        if team_pending:
            path = (
                "/leaves/approvals"
                if user.role == "manager"
                else "/leaves"
            )
            actions.append(
                _insight(
                    title="Approvals waiting",
                    message=f"{team_pending} leave request(s) need a decision.",
                    type="warning",
                    query="Show pending leave requests for my team.",
                    path=path,
                    label="Review leaves",
                    priority=14,
                )
            )

    next_holiday = (
        CompanyHoliday.objects.filter(
            organization=user.organization,
            holiday_date__gte=today,
        )
        .order_by("holiday_date")
        .first()
        if user.organization_id
        else None
    )
    if next_holiday:
        days_diff = (next_holiday.holiday_date - today).days
        if days_diff <= 14 and next_holiday.holiday_date.weekday() in (0, 4):
            actions.append(
                _insight(
                    title="Long weekend ahead",
                    message=f"{next_holiday.name} falls on a {next_holiday.holiday_date.strftime('%A')}.",
                    type="info",
                    query="What's the best way to apply for leave around the upcoming holiday?",
                    path="/leaves?action=apply",
                    label="Plan leave",
                    priority=55,
                )
            )

    return actions


def generate_user_insights(user) -> List[dict]:
    """Ranked next-best-actions for the employee dashboard (top items first)."""
    bundled: List[dict] = []
    bundled.extend(_onboarding_actions(user))
    bundled.extend(_attendance_actions(user))
    bundled.extend(_leave_actions(user))

    # Deduplicate by title, keep highest priority (lowest number)
    by_title: dict[str, dict] = {}
    for item in bundled:
        prev = by_title.get(item["title"])
        if not prev or item["priority"] < prev["priority"]:
            by_title[item["title"]] = item

    ranked = sorted(by_title.values(), key=lambda x: x["priority"])
    # Strip internal priority before GraphQL
    out = []
    for item in ranked[:5]:
        out.append(
            {
                "title": item["title"],
                "message": item["message"],
                "type": item["type"],
                "query": item["query"],
                "path": item.get("path"),
                "label": item.get("label"),
            }
        )
    return out


def generate_admin_insights(user) -> List[dict]:
    insights: List[dict] = []
    today = date.today()
    org = user.organization
    if not org:
        return insights

    active_emps = CustomUser.objects.filter(organization=org, is_active=True).count()
    if active_emps > 0:
        present_today = AttendanceRecord.objects.filter(
            attendance_date=today,
            user__organization=org,
            status__in=["present", "late_login", "early_logout", "half_day"],
        ).count()
        rate = present_today / active_emps * 100
        if rate < 75:
            insights.append(
                {
                    "title": "High absence today",
                    "message": f"Only {rate:.0f}% present ({present_today}/{active_emps}).",
                    "type": "warning",
                    "query": "Which departments have the lowest attendance today?",
                    "path": "/attendance",
                    "label": "Open attendance",
                }
            )

    next_week = today + timedelta(days=7)
    overlaps = (
        LeaveRequest.objects.filter(
            user__organization=org,
            _status="approved",
            from_date__lte=next_week,
            to_date__gte=today,
        )
        .values("user__department__name")
        .annotate(count=Count("id"))
        .filter(count__gt=3)
    )
    for o in overlaps:
        dept = o["user__department__name"] or "Unassigned"
        insights.append(
            {
                "title": f"Coverage risk: {dept}",
                "message": f"{o['count']} people in this department are on leave soon.",
                "type": "anomaly",
                "query": f"Report overlapping leaves in {dept} and suggest coverage.",
                "path": "/leaves?tab=requests",
                "label": "Review leaves",
            }
        )

    try:
        from onboarding.models import EmployeeOnboarding

        stuck = (
            EmployeeOnboarding.objects.filter(
                organization=org,
                status__in=["invited", "preboarding", "in_progress"],
            ).count()
        )
        if stuck:
            insights.append(
                {
                    "title": "Hires in progress",
                    "message": f"{stuck} onboarding record(s) still open. Check invites, docs, or activation.",
                    "type": "info",
                    "query": "Summarize pending onboarding hires and what's blocking them.",
                    "path": "/onboarding",
                    "label": "Open onboarding",
                }
            )
    except Exception:
        pass

    pending_leaves = LeaveRequest.objects.filter(
        user__organization=org, _status="pending"
    ).count()
    if pending_leaves:
        insights.append(
            {
                "title": "Pending leave approvals",
                "message": f"{pending_leaves} leave request(s) await a decision.",
                "type": "warning",
                "query": "List pending leave requests for the organization.",
                "path": "/leaves?tab=requests",
                "label": "Review requests",
            }
        )

    return insights[:5]
