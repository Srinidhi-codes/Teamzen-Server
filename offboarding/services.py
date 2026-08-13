from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from offboarding.models import (
    EmployeeOffboarding,
    ExitInvite,
    FnfSettlement,
    OffboardingTaskDefinition,
    OffboardingTaskInstance,
    OffboardingTemplate,
)
from offboarding.settlement import build_settlement_draft


DEFAULT_TASKS = [
    {
        "title": "Submit resignation / exit form",
        "assignee_role": "employee",
        "phase": "notice",
        "due_offset_days": -14,
        "requires_document_category": "exit_clearance",
        "sort_order": 10,
    },
    {
        "title": "Return company assets (laptop, badge, keys)",
        "assignee_role": "employee",
        "phase": "last_day",
        "due_offset_days": 0,
        "requires_document_category": "exit_clearance",
        "sort_order": 20,
    },
    {
        "title": "IT access revocation",
        "assignee_role": "it",
        "phase": "clearance",
        "due_offset_days": 0,
        "sort_order": 30,
    },
    {
        "title": "Manager clearance",
        "assignee_role": "manager",
        "phase": "clearance",
        "due_offset_days": 1,
        "sort_order": 40,
    },
    {
        "title": "HR document & KYC check",
        "assignee_role": "hr",
        "phase": "clearance",
        "due_offset_days": 2,
        "sort_order": 50,
    },
    {
        "title": "Prepare Full & Final settlement",
        "assignee_role": "hr",
        "phase": "settlement",
        "due_offset_days": 5,
        "sort_order": 60,
    },
    {
        "title": "Issue experience & relieving letters",
        "assignee_role": "hr",
        "phase": "letters",
        "due_offset_days": 7,
        "sort_order": 70,
    },
]


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def exit_portal_url(raw_token: str) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/exit/{raw_token}"


def ensure_default_template(organization, *, actor=None) -> OffboardingTemplate:
    tpl = OffboardingTemplate.objects.filter(
        organization=organization, is_default=True
    ).first()
    if tpl:
        ensure_exit_form_upload_on_template(tpl)
        return tpl
    tpl = OffboardingTemplate.objects.create(
        organization=organization,
        name="Default F&F checklist",
        description="Standard clearance, settlement, and letter tasks",
        is_default=True,
        created_by=actor,
    )
    for t in DEFAULT_TASKS:
        OffboardingTaskDefinition.objects.create(
            template=tpl,
            title=t["title"],
            description="",
            assignee_role=t["assignee_role"],
            phase=t["phase"],
            due_offset_days=t.get("due_offset_days", 0),
            requires_document_category=t.get("requires_document_category", ""),
            is_required=True,
            sort_order=t.get("sort_order", 0),
        )
    return tpl


def _is_exit_form_task_title(title: str) -> bool:
    t = (title or "").lower()
    return "exit form" in t or "resignation" in t


def ensure_exit_form_upload_on_template(tpl: OffboardingTemplate) -> None:
    """Backfill upload requirement on resignation / exit form checklist items."""
    OffboardingTaskDefinition.objects.filter(template=tpl).filter(
        title__icontains="resignation"
    ).exclude(requires_document_category="exit_clearance").update(
        requires_document_category="exit_clearance"
    )
    OffboardingTaskDefinition.objects.filter(template=tpl).filter(
        title__icontains="exit form"
    ).exclude(requires_document_category="exit_clearance").update(
        requires_document_category="exit_clearance"
    )


def ensure_exit_form_upload_on_offboarding(offboarding: EmployeeOffboarding) -> None:
    """Ensure live F&F task instances require an exit-form upload when applicable."""
    if offboarding.template_id:
        ensure_exit_form_upload_on_template(offboarding.template)
    for task in offboarding.tasks.all():
        if task.assignee_role != "employee":
            continue
        if _is_exit_form_task_title(task.title) and not task.requires_document_category:
            task.requires_document_category = "exit_clearance"
            task.save(update_fields=["requires_document_category"])


def resolve_assignee(offboarding: EmployeeOffboarding, role: str):
    user = offboarding.user
    if role == "employee":
        return user
    if role == "manager":
        return user.manager
    if role == "it":
        tpl = offboarding.template
        if tpl and tpl.it_contact_id:
            return tpl.it_contact
        return None
    if role == "hr":
        return offboarding.created_by
    return None


def _due_date(lwd, offset_days: int):
    if not lwd:
        return None
    return lwd + timedelta(days=offset_days or 0)


def instantiate_tasks(offboarding: EmployeeOffboarding):
    if not offboarding.template_id:
        return []
    defs = offboarding.template.task_definitions.all()
    created = []
    existing = set(
        offboarding.tasks.exclude(definition_id=None).values_list("definition_id", flat=True)
    )
    lwd = offboarding.last_working_day or offboarding.exit_date
    for d in defs:
        if d.id in existing:
            continue
        inst = OffboardingTaskInstance.objects.create(
            offboarding=offboarding,
            definition=d,
            title=d.title,
            description=d.description,
            assignee_role=d.assignee_role,
            phase=d.phase,
            assignee=resolve_assignee(offboarding, d.assignee_role),
            due_at=_due_date(lwd, d.due_offset_days),
            is_required=d.is_required,
            requires_document_category=d.requires_document_category or "",
            sort_order=d.sort_order,
        )
        created.append(inst)
    recompute_progress(offboarding)
    return created


def recompute_progress(offboarding: EmployeeOffboarding) -> int:
    tasks = offboarding.tasks.filter(is_required=True)
    total = tasks.count()
    if total == 0:
        task_pct = 0
    else:
        done = tasks.filter(status__in=["completed", "skipped"]).count()
        task_pct = int(round(100 * done / total))

    has_settlement = False
    settlement_ok = False
    try:
        s = offboarding.settlement
        has_settlement = True
        settlement_ok = s.status in ("hr_approved", "acknowledged", "paid")
    except Exception:
        pass

    issued_types = set(
        offboarding.letters.filter(status="issued").values_list("letter_type", flat=True)
    )
    has_letters = "experience" in issued_types and "relieving" in issued_types

    # Overall %: do not show 100% until settlement + both letters are done.
    if task_pct >= 100 and settlement_ok and has_letters:
        pct = 100
    elif task_pct >= 100 and settlement_ok:
        pct = 95
    elif task_pct >= 100:
        pct = 90
    else:
        pct = task_pct

    offboarding.progress_pct = pct

    if offboarding.status not in ("cancelled", "completed"):
        if total > 0 and task_pct >= 100:
            if has_settlement and settlement_ok and has_letters:
                offboarding.status = "completed"
                offboarding.completed_at = timezone.now()
            elif has_settlement and settlement_ok:
                offboarding.status = "letters_pending"
            else:
                offboarding.status = "settlement_pending"
        elif offboarding.status == "initiated":
            offboarding.status = "in_progress"

    offboarding.save(
        update_fields=["progress_pct", "status", "completed_at", "updated_at"]
    )
    return pct


def create_exit_invite(offboarding: EmployeeOffboarding, *, created_by=None, expires_days=45):
    raw = secrets.token_urlsafe(32)
    invite = ExitInvite.objects.create(
        offboarding=offboarding,
        token_hash=hash_invite_token(raw),
        expires_at=timezone.now() + timedelta(days=expires_days),
        created_by=created_by,
    )
    return raw, invite


def get_exit_invite_by_token(raw_token: str):
    if not raw_token:
        return None
    invite = (
        ExitInvite.objects.select_related(
            "offboarding", "offboarding__user", "offboarding__organization"
        )
        .filter(token_hash=hash_invite_token(raw_token))
        .first()
    )
    if not invite:
        return None
    if invite.expires_at and invite.expires_at < timezone.now():
        return None
    if invite.offboarding.status == "cancelled":
        return None
    return invite


@transaction.atomic
def start_offboarding(
    *,
    actor,
    user,
    exit_date,
    last_working_day=None,
    reason: str = "resign",
    template_id=None,
    deactivate_now: bool = True,
    send_invite: bool = True,
    notes: str = "",
) -> tuple[EmployeeOffboarding, str | None]:
    """
    Start F&F for an employee.

    Always marks the user inactive and cancels any active onboarding.
    ``deactivate_now`` is kept for API compatibility and is always treated as True.
    """
    _ = deactivate_now  # always deactivate on F&F
    if not user.organization_id:
        raise ValueError("Employee has no organization.")

    existing = EmployeeOffboarding.objects.filter(user_id=user.id).first()
    if existing and existing.status != "cancelled":
        raise ValueError(
            f"Offboarding already exists (id={existing.id}, status={existing.status})."
        )

    org = user.organization
    if template_id:
        template = OffboardingTemplate.objects.filter(
            id=template_id, organization=org
        ).first()
        if not template:
            raise ValueError("Template not found.")
    else:
        template = ensure_default_template(org, actor=actor)

    lwd = last_working_day or exit_date
    if existing and existing.status == "cancelled":
        offboarding = existing
        offboarding.template = template
        offboarding.status = "initiated"
        offboarding.reason = reason or "resign"
        offboarding.exit_date = exit_date
        offboarding.last_working_day = lwd
        offboarding.progress_pct = 0
        offboarding.started_at = timezone.now()
        offboarding.completed_at = None
        offboarding.notes = notes or ""
        offboarding.created_by = actor
        offboarding.save()
        offboarding.tasks.all().delete()
    else:
        offboarding = EmployeeOffboarding.objects.create(
            organization=org,
            user=user,
            template=template,
            status="initiated",
            reason=reason or "resign",
            exit_date=exit_date,
            last_working_day=lwd,
            started_at=timezone.now(),
            created_by=actor,
            notes=notes or "",
        )

    user.date_of_exit = exit_date
    # F&F always deactivates the employee account.
    user.is_active = False
    user.save(update_fields=["date_of_exit", "is_active"])
    offboarding.deactivated_at = timezone.now()
    offboarding.save(update_fields=["deactivated_at", "updated_at"])

    # Drop any active join / onboarding process for this employee.
    try:
        from onboarding.models import EmployeeOnboarding
        from onboarding.services import cancel_onboarding

        active_onboardings = EmployeeOnboarding.objects.filter(user_id=user.id).exclude(
            status="cancelled"
        )
        for ob in active_onboardings:
            cancel_onboarding(ob, actor=actor)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Failed to cancel onboarding while starting F&F user_id=%s", user.id
        )

    instantiate_tasks(offboarding)

    raw_token = None
    if send_invite:
        raw_token, _ = create_exit_invite(offboarding, created_by=actor)
        try:
            from notifications.utils import notify_user

            notify_user(
                recipient_id=user.id,
                verb="Exit / F&F portal",
                message=(
                    "Your Full & Final exit checklist is ready. "
                    f"Open {exit_portal_url(raw_token)} to complete clearance and download letters."
                ),
                actor_id=getattr(actor, "id", None),
                target_type="EmployeeOffboarding",
                target_id=str(offboarding.id),
                level="personal",
                notification_type="BOTH",
                extra_context={"exit_url": exit_portal_url(raw_token)},
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Exit invite email failed offboarding_id=%s", offboarding.id
            )

    return offboarding, raw_token


def complete_task(task: OffboardingTaskInstance, *, completed_by=None, notes: str = ""):
    task.status = "completed"
    task.completed_at = timezone.now()
    task.completed_by = completed_by
    if notes:
        task.notes = notes
    task.save()
    recompute_progress(task.offboarding)
    return task


def maybe_complete_letters_task(offboarding: EmployeeOffboarding, *, actor=None) -> bool:
    """
    When both experience and relieving letters are issued, auto-complete the
    letters checklist task (e.g. "Issue experience & relieving letters").
    """
    issued = set(
        offboarding.letters.filter(status="issued").values_list("letter_type", flat=True)
    )
    if "experience" not in issued or "relieving" not in issued:
        return False

    tasks = offboarding.tasks.exclude(status__in=["completed", "skipped"]).filter(
        phase="letters"
    )
    if not tasks.exists():
        tasks = offboarding.tasks.exclude(status__in=["completed", "skipped"]).filter(
            title__icontains="letter"
        )

    completed_any = False
    for task in tasks:
        complete_task(
            task,
            completed_by=actor,
            notes="Auto-completed after experience and relieving letters were issued.",
        )
        completed_any = True

    if not completed_any:
        recompute_progress(offboarding)
    return completed_any


def skip_task(task: OffboardingTaskInstance, *, actor=None, notes: str = ""):
    task.status = "skipped"
    task.completed_at = timezone.now()
    task.completed_by = actor
    if notes:
        task.notes = notes
    task.save()
    recompute_progress(task.offboarding)
    return task


def cancel_offboarding(offboarding: EmployeeOffboarding, *, actor=None):
    offboarding.status = "cancelled"
    offboarding.save(update_fields=["status", "updated_at"])
    return offboarding


def compute_and_save_settlement(
    offboarding: EmployeeOffboarding,
    *,
    actor=None,
    bonus_gratuity=None,
    recoveries=None,
    other_additions=None,
    other_deductions=None,
    notes: str = "",
) -> FnfSettlement:
    draft = build_settlement_draft(
        offboarding,
        bonus_gratuity=Decimal(bonus_gratuity) if bonus_gratuity is not None else None,
        recoveries=Decimal(recoveries) if recoveries is not None else None,
        other_additions=Decimal(other_additions) if other_additions is not None else None,
        other_deductions=Decimal(other_deductions) if other_deductions is not None else None,
    )
    settlement, _ = FnfSettlement.objects.update_or_create(
        offboarding=offboarding,
        defaults={
            "status": "draft",
            "pro_rata_salary": draft["pro_rata_salary"],
            "leave_encashment": draft["leave_encashment"],
            "bonus_gratuity": draft["bonus_gratuity"],
            "other_additions": draft["other_additions"],
            "recoveries": draft["recoveries"],
            "other_deductions": draft["other_deductions"],
            "net_payable": draft["net_payable"],
            "snapshot": draft["snapshot"],
            "notes": notes or "",
            "computed_at": timezone.now(),
        },
    )
    settlement.recompute_net()
    settlement.save()
    if offboarding.status in ("in_progress", "initiated", "settlement_pending"):
        offboarding.status = "settlement_pending"
        offboarding.save(update_fields=["status", "updated_at"])
    return settlement


def approve_settlement(settlement: FnfSettlement, *, actor=None) -> FnfSettlement:
    settlement.status = "hr_approved"
    settlement.approved_at = timezone.now()
    settlement.approved_by = actor
    settlement.save(
        update_fields=["status", "approved_at", "approved_by", "updated_at"]
    )
    recompute_progress(settlement.offboarding)
    try:
        from notifications.utils import notify_user

        notify_user(
            recipient_id=settlement.offboarding.user_id,
            verb="F&F settlement ready",
            message="Your Full & Final settlement statement is ready for review on the exit portal.",
            actor_id=getattr(actor, "id", None),
            target_type="FnfSettlement",
            target_id=str(settlement.id),
            level="personal",
            notification_type="BOTH",
        )
    except Exception:
        pass
    return settlement


def acknowledge_settlement(settlement: FnfSettlement) -> FnfSettlement:
    if settlement.status not in ("hr_approved", "acknowledged", "paid"):
        raise ValueError("Settlement is not approved yet.")
    if settlement.status == "hr_approved":
        settlement.status = "acknowledged"
        settlement.acknowledged_at = timezone.now()
        settlement.save(update_fields=["status", "acknowledged_at", "updated_at"])
    recompute_progress(settlement.offboarding)
    return settlement


def mark_settlement_paid(settlement: FnfSettlement, *, actor=None) -> FnfSettlement:
    settlement.status = "paid"
    settlement.paid_at = timezone.now()
    settlement.save(update_fields=["status", "paid_at", "updated_at"])
    recompute_progress(settlement.offboarding)
    return settlement
