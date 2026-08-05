"""Deterministic First-Day Wizard payload (no LLM required)."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth import get_user_model


def _incomplete_onboarding(user) -> tuple[bool, dict[str, Any] | None]:
    from onboarding.models import EmployeeOnboarding

    ob = (
        EmployeeOnboarding.objects.select_related("user")
        .prefetch_related("tasks", "documents")
        .filter(user=user)
        .exclude(status="cancelled")
        .first()
    )
    if not ob:
        return False, None

    tasks = list(ob.tasks.all())
    docs = list(ob.documents.all())
    open_tasks = [t for t in tasks if t.status not in ("completed", "skipped")]
    pending_docs = [d for d in docs if d.verification_status == "pending"]
    rejected_docs = [d for d in docs if d.verification_status == "rejected"]
    next_task = next(
        (t for t in sorted(open_tasks, key=lambda x: (x.sort_order, x.id))),
        None,
    )
    progress = float(getattr(ob, "progress_pct", None) or 0)

    incomplete = ob.status != "completed" or bool(open_tasks) or bool(rejected_docs)
    payload = {
        "status": ob.status,
        "progress_pct": progress,
        "pending_task_count": len(open_tasks),
        "pending_doc_count": len(pending_docs),
        "rejected_doc_count": len(rejected_docs),
        "next_task_title": next_task.title if next_task else None,
        "next_task_phase": next_task.phase if next_task else None,
        "rejected_doc_titles": [
            (d.title or d.category or "Document") for d in rejected_docs[:5]
        ],
        "pending_doc_titles": [
            (d.title or d.category or "Document") for d in pending_docs[:5]
        ],
    }
    return incomplete, payload


def _leave_snapshot(user) -> dict[str, Any]:
    from leaves.models import LeaveBalance, LeaveType

    year = date.today().year
    balances = (
        LeaveBalance.objects.filter(user=user, year=year)
        .select_related("leave_type")
        .order_by("leave_type__name")
    )
    rows = []
    for bal in balances:
        rows.append(
            {
                "leave_type_id": bal.leave_type_id,
                "leave_type_name": bal.leave_type.name,
                "available": float(bal.get_available_balance()),
                "total_entitled": float(bal.total_entitled or 0),
                "used": float(bal.used or 0),
                "pending": float(bal.pending_approval or 0),
            }
        )
    types = []
    if user.organization_id:
        types = list(
            LeaveType.objects.filter(organization_id=user.organization_id, is_active=True)
            .order_by("name")
            .values_list("name", flat=True)[:8]
        )
    return {"balances": rows, "leave_type_names": types}


def _attendance_hint(user) -> dict[str, Any]:
    from attendance.models import AttendanceRecord

    today = date.today()
    rec = (
        AttendanceRecord.objects.filter(user=user, attendance_date=today)
        .order_by("-id")
        .first()
    )
    punched_in = bool(rec and rec.login_time)
    return {
        "checked_in_today": punched_in,
        "status": getattr(rec, "status", None) if rec else None,
        "tip": (
            "Open Attendance, allow location, and check in from the office geofence. "
            "If face enroll is required, complete it under Attendance."
            if not punched_in
            else "You're checked in for today. Use Attendance Correction if you miss a checkout."
        ),
    }


def _contacts(user) -> dict[str, Any]:
    manager = getattr(user, "manager", None)
    hr = None
    if user.organization_id:
        User = get_user_model()
        hr = (
            User.objects.filter(
                organization_id=user.organization_id,
                role__in=("hr", "admin"),
                is_active=True,
            )
            .exclude(id=user.id)
            .order_by("role", "first_name")
            .first()
        )
    return {
        "manager_name": (
            f"{manager.first_name or ''} {manager.last_name or ''}".strip()
            or (manager.email if manager else None)
        ),
        "manager_email": manager.email if manager else None,
        "hr_name": (
            f"{hr.first_name or ''} {hr.last_name or ''}".strip() or hr.email
            if hr
            else None
        ),
        "hr_email": hr.email if hr else None,
        "org_name": getattr(getattr(user, "organization", None), "name", None),
    }


def build_first_day_wizard(user) -> dict[str, Any]:
    """
    Build ordered wizard steps with answers + deep-links.
    should_show: not seen AI onboarding OR hire checklist still incomplete.
    """
    incomplete_ob, onboarding = _incomplete_onboarding(user)
    has_seen = bool(getattr(user, "has_seen_ai_onboarding", False))
    should_show = (not has_seen) or incomplete_ob

    leaves = _leave_snapshot(user)
    attendance = _attendance_hint(user)
    contacts = _contacts(user)
    profile = {
        "first_name": user.first_name or "",
        "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip()
        or user.email,
        "role": user.role,
        "department": getattr(getattr(user, "department", None), "name", None),
        "designation": getattr(getattr(user, "designation", None), "name", None),
        "organization": contacts.get("org_name"),
    }

    steps: list[dict[str, Any]] = []

    steps.append(
        {
            "id": "welcome",
            "title": f"Welcome{', ' + user.first_name if user.first_name else ''}",
            "summary": (
                f"I'm your Teamzen assistant for {contacts.get('org_name') or 'your company'}. "
                "I'll walk through joining, leave, attendance, and who to contact — "
                "so you don't need to chase HR for the basics."
            ),
            "route": "/dashboard",
            "route_label": None,
            "bullets": [
                f"Role: {user.role}",
                f"Department: {profile['department'] or '—'}",
                f"Designation: {profile['designation'] or '—'}",
            ],
        }
    )

    if onboarding:
        bullets = [
            f"Status: {onboarding['status']}",
            f"Progress: {onboarding['progress_pct']:.0f}%",
            f"Open tasks: {onboarding['pending_task_count']}",
        ]
        if onboarding.get("next_task_title"):
            bullets.append(f"Next: {onboarding['next_task_title']}")
        steps.append(
            {
                "id": "progress",
                "title": "Your joining progress",
                "summary": (
                    "Here's what's left on your onboarding checklist. "
                    "Open My Onboarding to upload docs or mark tasks done."
                    if incomplete_ob
                    else "Your onboarding checklist looks complete. You can still revisit it anytime."
                ),
                "route": "/onboarding",
                "route_label": "Open My Onboarding",
                "bullets": bullets,
            }
        )

        if onboarding["rejected_doc_count"] or onboarding["pending_doc_count"]:
            doc_bullets = []
            for t in onboarding.get("rejected_doc_titles") or []:
                doc_bullets.append(f"Rejected — re-upload: {t}")
            for t in onboarding.get("pending_doc_titles") or []:
                doc_bullets.append(f"Awaiting verification: {t}")
            steps.append(
                {
                    "id": "docs",
                    "title": "Documents & offer",
                    "summary": (
                        "Some documents still need your attention. "
                        "Fix rejected uploads or wait for HR verification on pending ones."
                    ),
                    "route": "/onboarding",
                    "route_label": "Fix documents",
                    "bullets": doc_bullets or ["Check the Documents section on My Onboarding."],
                }
            )

    leave_bullets = []
    for b in leaves["balances"][:6]:
        leave_bullets.append(
            f"{b['leave_type_name']}: {b['available']} available "
            f"(of {b['total_entitled']})"
        )
    if not leave_bullets and leaves["leave_type_names"]:
        leave_bullets = [f"Available types: {', '.join(leaves['leave_type_names'])}"]
    if not leave_bullets:
        leave_bullets = ["Leave types will appear once HR configures balances for you."]

    steps.append(
        {
            "id": "leave",
            "title": "How leave works here",
            "summary": (
                "Check balances below, then request leave from the Leaves page. "
                "Policies (sick, casual, etc.) are also searchable in the assistant."
            ),
            "route": "/leaves?action=apply",
            "route_label": "Request leave",
            "bullets": leave_bullets,
        }
    )

    steps.append(
        {
            "id": "attendance",
            "title": "Attendance day-1",
            "summary": attendance["tip"],
            "route": "/attendance",
            "route_label": "Go to Attendance",
            "bullets": [
                f"Checked in today: {'Yes' if attendance['checked_in_today'] else 'Not yet'}",
                "Share live location when punching in.",
                "Forgot checkout? Use Attendance Correction.",
            ],
        }
    )

    steps.append(
        {
            "id": "policies",
            "title": "Handbook & must-knows",
            "summary": (
                "Company policies (leave, attendance, conduct) live under Policies. "
                "Ask the assistant any policy question — answers cite the handbook."
            ),
            "route": "/policies",
            "route_label": "Browse policies",
            "bullets": [
                "Ask: “What is the sick leave policy?”",
                "Ask: “What are WFH rules?”",
                "Open full PDFs anytime from Policies.",
            ],
        }
    )

    contact_bullets = []
    if contacts.get("manager_name"):
        contact_bullets.append(
            f"Manager: {contacts['manager_name']}"
            + (f" · {contacts['manager_email']}" if contacts.get("manager_email") else "")
        )
    if contacts.get("hr_name"):
        contact_bullets.append(
            f"HR: {contacts['hr_name']}"
            + (f" · {contacts['hr_email']}" if contacts.get("hr_email") else "")
        )
    if not contact_bullets:
        contact_bullets = ["Your manager and HR contacts will show once assigned."]

    steps.append(
        {
            "id": "contacts",
            "title": "Who can help",
            "summary": (
                "Use these contacts for people issues. For how-to questions, "
                "keep using this assistant first — it knows leave, attendance, and policies."
            ),
            "route": "/team",
            "route_label": "View team",
            "bullets": contact_bullets,
        }
    )

    steps.append(
        {
            "id": "done",
            "title": "You're set",
            "summary": (
                "You can reopen help anytime via the assistant button. "
                "Path-aware suggestions change based on the page you're on."
            ),
            "route": None,
            "route_label": None,
            "bullets": [
                "Ask the floating assistant anything.",
                "Complete remaining onboarding tasks when ready.",
            ],
        }
    )

    return {
        "should_show": should_show,
        "has_seen_ai_onboarding": has_seen,
        "onboarding_incomplete": incomplete_ob,
        "profile": profile,
        "onboarding": onboarding,
        "steps": steps,
    }
