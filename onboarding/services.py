"""Onboarding domain services: templates, tasks, progress, activation."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from onboarding.models import (
    DocumentLetterTemplate,
    EmployeeDocument,
    EmployeeOnboarding,
    OnboardingTaskDefinition,
    OnboardingTaskInstance,
    OnboardingTemplate,
    OfferLetter,
    PreboardingInvite,
)

logger = logging.getLogger(__name__)
User = get_user_model()

DEFAULT_TASKS = [
    {
        "title": "Accept offer letter",
        "description": "Review and digitally accept your offer letter.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -7,
        "requires_document_category": "",
        "sort_order": 10,
    },
    {
        "title": "Complete personal & bank details",
        "description": "Fill phone, PAN, Aadhaar, bank account and IFSC.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -5,
        "requires_document_category": "",
        "sort_order": 20,
    },
    {
        "title": "Upload ID proof",
        "description": "Upload a government-issued photo ID.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -5,
        "requires_document_category": "id_proof",
        "sort_order": 30,
    },
    {
        "title": "Upload PAN card",
        "description": "Upload a clear scan or photo of your PAN card.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -5,
        "requires_document_category": "pan",
        "sort_order": 40,
    },
    {
        "title": "Upload Aadhaar",
        "description": "Upload Aadhaar (masked OK) for KYC.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -5,
        "requires_document_category": "aadhaar",
        "sort_order": 50,
    },
    {
        "title": "Upload bank proof",
        "description": "Cancelled cheque or bank statement showing account details.",
        "assignee_role": "hire",
        "phase": "preboarding",
        "due_offset_days": -5,
        "requires_document_category": "bank_proof",
        "sort_order": 60,
    },
    {
        "title": "Verify KYC documents",
        "description": "HR verifies uploaded identity and bank documents.",
        "assignee_role": "hr",
        "phase": "preboarding",
        "due_offset_days": -2,
        "requires_document_category": "",
        "sort_order": 70,
    },
    {
        "title": "Provision laptop / IT assets",
        "description": "Prepare laptop, accounts, and access badges.",
        "assignee_role": "it",
        "phase": "day1",
        "due_offset_days": 0,
        "requires_document_category": "",
        "sort_order": 100,
    },
    {
        "title": "Create work email & accounts",
        "description": "Provision email, Slack/Teams, and tool accounts.",
        "assignee_role": "it",
        "phase": "day1",
        "due_offset_days": 0,
        "requires_document_category": "",
        "sort_order": 110,
    },
    {
        "title": "Manager welcome & intro",
        "description": "Schedule intro meeting and share team context.",
        "assignee_role": "manager",
        "phase": "day1",
        "due_offset_days": 0,
        "requires_document_category": "",
        "sort_order": 120,
    },
    {
        "title": "Acknowledge company handbook",
        "description": "Read and acknowledge key company policies.",
        "assignee_role": "hire",
        "phase": "day1",
        "due_offset_days": 1,
        "requires_document_category": "signed_policy",
        "sort_order": 130,
    },
    {
        "title": "First attendance punch",
        "description": "Complete first check-in at the office or remote geofence.",
        "assignee_role": "hire",
        "phase": "day1",
        "due_offset_days": 0,
        "requires_document_category": "",
        "sort_order": 140,
    },
    {
        "title": "Enroll face for attendance",
        "description": "Complete face enrollment if the org uses face attendance.",
        "assignee_role": "hire",
        "phase": "week1",
        "due_offset_days": 3,
        "requires_document_category": "",
        "sort_order": 150,
    },
    {
        "title": "30-day check-in",
        "description": "Manager check-in on goals, blockers, and culture fit.",
        "assignee_role": "manager",
        "phase": "day30",
        "due_offset_days": 30,
        "requires_document_category": "",
        "sort_order": 200,
    },
    {
        "title": "90-day review",
        "description": "Formal 90-day onboarding completion review.",
        "assignee_role": "manager",
        "phase": "day90",
        "due_offset_days": 90,
        "requires_document_category": "",
        "sort_order": 300,
    },
]

DEFAULT_OFFER_BODY = """
<p>Dear {{employee_name}},</p>
<p>We are pleased to offer you the position of <strong>{{designation}}</strong>
at <strong>{{company_name}}</strong>.</p>
<p>Your proposed joining date is <strong>{{join_date}}</strong>.
Department: <strong>{{department}}</strong>.</p>
<p>Please review this offer and accept it through the preboarding portal.</p>
<p>Welcome aboard!<br/>{{company_name}} HR</p>
"""


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def ensure_default_template(organization, created_by=None) -> OnboardingTemplate:
    existing = OnboardingTemplate.objects.filter(
        organization=organization, is_default=True
    ).first()
    if existing:
        return existing

    with transaction.atomic():
        template = OnboardingTemplate.objects.create(
            organization=organization,
            name="Standard Onboarding",
            description="Default preboarding + day-1 through day-90 checklist",
            is_default=True,
            created_by=created_by,
        )
        for spec in DEFAULT_TASKS:
            OnboardingTaskDefinition.objects.create(template=template, **spec)

        if not DocumentLetterTemplate.objects.filter(
            organization=organization, letter_type="offer", is_default=True
        ).exists():
            DocumentLetterTemplate.objects.create(
                organization=organization,
                name="Standard Offer Letter",
                letter_type="offer",
                subject="Offer of Employment — {{company_name}}",
                body_html=DEFAULT_OFFER_BODY.strip(),
                is_default=True,
                created_by=created_by,
            )
    return template


def resolve_template(
    organization,
    *,
    template_id=None,
    department_id=None,
    designation_id=None,
    employment_type: str = "",
) -> OnboardingTemplate:
    if template_id:
        tpl = OnboardingTemplate.objects.filter(
            id=template_id, organization=organization
        ).first()
        if tpl:
            return tpl

    qs = OnboardingTemplate.objects.filter(organization=organization)
    if designation_id:
        match = qs.filter(designation_id=designation_id).first()
        if match:
            return match
    if department_id:
        match = qs.filter(department_id=department_id, designation__isnull=True).first()
        if match:
            return match
    if employment_type:
        match = qs.filter(employment_type=employment_type).first()
        if match:
            return match
    return ensure_default_template(organization)


def resolve_assignee(onboarding: EmployeeOnboarding, role: str):
    user = onboarding.user
    if role == "hire":
        return user
    if role == "manager":
        return user.manager
    if role == "it":
        if onboarding.template and onboarding.template.it_contact_id:
            return onboarding.template.it_contact
        return (
            User.objects.filter(
                organization_id=onboarding.organization_id,
                role__in=["admin", "hr"],
                is_active=True,
            )
            .order_by("id")
            .first()
        )
    if role == "hr":
        return (
            User.objects.filter(
                organization_id=onboarding.organization_id,
                role__in=["hr", "admin"],
                is_active=True,
            )
            .order_by("id")
            .first()
        )
    return None


def _due_date(join_date: Optional[date], offset_days: int) -> Optional[date]:
    if not join_date:
        return None
    return join_date + timedelta(days=offset_days)


def instantiate_tasks(
    onboarding: EmployeeOnboarding,
    *,
    phases: Optional[list[str]] = None,
) -> list[OnboardingTaskInstance]:
    if not onboarding.template_id:
        return []

    defs = onboarding.template.task_definitions.all()
    if phases is not None:
        defs = defs.filter(phase__in=phases)

    created = []
    existing_def_ids = set(
        onboarding.tasks.exclude(definition_id=None).values_list(
            "definition_id", flat=True
        )
    )
    for d in defs:
        if d.id in existing_def_ids:
            continue
        inst = OnboardingTaskInstance.objects.create(
            onboarding=onboarding,
            definition=d,
            title=d.title,
            description=d.description,
            assignee_role=d.assignee_role,
            phase=d.phase,
            assignee=resolve_assignee(onboarding, d.assignee_role),
            due_at=_due_date(onboarding.join_date, d.due_offset_days),
            is_required=d.is_required,
            requires_document_category=d.requires_document_category or "",
            sort_order=d.sort_order,
        )
        created.append(inst)
    recompute_progress(onboarding)
    return created


def recompute_progress(onboarding: EmployeeOnboarding) -> int:
    tasks = onboarding.tasks.filter(is_required=True)
    total = tasks.count()
    if total == 0:
        pct = 0
    else:
        done = tasks.filter(status__in=["completed", "skipped"]).count()
        pct = int(round(100 * done / total))
    onboarding.progress_pct = pct
    if total > 0 and pct >= 100 and onboarding.status == "in_progress":
        onboarding.status = "completed"
        onboarding.completed_at = timezone.now()
    onboarding.save(update_fields=["progress_pct", "status", "completed_at", "updated_at"])
    return pct


@transaction.atomic
def start_preboarding(
    *,
    actor,
    organization,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    department_id=None,
    designation_id=None,
    office_location_id=None,
    manager_id=None,
    employment_type: str = "full_time",
    date_of_joining=None,
    phone_number: str = "",
    template_id=None,
    generate_offer: bool = True,
    letter_template_id=None,
    include_ctc_annexure: bool = False,
    annual_ctc=None,
) -> tuple[EmployeeOnboarding, str | None]:
    """
    Create pending inactive user + onboarding + preboarding tasks.
    Returns (onboarding, raw_invite_token).
    """
    if User.objects.filter(email__iexact=email).exists():
        raise ValueError("A user with this email already exists.")

    template = resolve_template(
        organization,
        template_id=template_id,
        department_id=department_id,
        designation_id=designation_id,
        employment_type=employment_type,
    )

    new_user = User.objects.create_user(
        email=email,
        username=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role="employee",
        employment_type=employment_type or "full_time",
        is_active=False,
        organization=organization,
    )
    if department_id:
        new_user.department_id = department_id
    if designation_id:
        new_user.designation_id = designation_id
    if office_location_id:
        new_user.office_location_id = office_location_id
    if manager_id:
        new_user.manager_id = manager_id
    if date_of_joining:
        new_user.date_of_joining = date_of_joining
    if phone_number:
        new_user.phone_number = phone_number
    new_user.save()

    onboarding = EmployeeOnboarding.objects.create(
        organization=organization,
        user=new_user,
        template=template,
        status="invited",
        join_date=date_of_joining or new_user.date_of_joining,
        created_by=actor,
        started_at=timezone.now(),
    )

    instantiate_tasks(onboarding, phases=["preboarding"])

    if generate_offer:
        generate_offer_letter(
            onboarding,
            actor=actor,
            letter_template_id=letter_template_id,
            include_ctc_annexure=include_ctc_annexure,
            annual_ctc=annual_ctc,
        )

    raw_token, _invite = create_preboarding_invite(onboarding, created_by=actor)
    onboarding.status = "preboarding"
    onboarding.save(update_fields=["status", "updated_at"])

    return onboarding, raw_token


def create_preboarding_invite(
    onboarding: EmployeeOnboarding,
    *,
    created_by=None,
    expires_days: int = 14,
) -> tuple[str, PreboardingInvite]:
    raw = secrets.token_urlsafe(32)
    invite = PreboardingInvite.objects.create(
        onboarding=onboarding,
        token_hash=hash_invite_token(raw),
        expires_at=timezone.now() + timedelta(days=expires_days),
        created_by=created_by,
    )
    return raw, invite


def get_invite_by_token(raw_token: str) -> Optional[PreboardingInvite]:
    if not raw_token:
        return None
    invite = (
        PreboardingInvite.objects.select_related(
            "onboarding", "onboarding__user", "onboarding__organization"
        )
        .filter(token_hash=hash_invite_token(raw_token))
        .first()
    )
    if not invite:
        return None
    if invite.expires_at < timezone.now():
        return None
    return invite


def preboarding_portal_url(raw_token: str) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/preboarding/{raw_token}"


def merge_letter_fields(onboarding: EmployeeOnboarding, text: str) -> str:
    user = onboarding.user
    org = onboarding.organization
    join = onboarding.join_date or user.date_of_joining
    mapping = {
        "employee_name": f"{user.first_name} {user.last_name}".strip() or user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.email,
        "designation": getattr(user.designation, "name", None) or "",
        "department": getattr(user.department, "name", None) or "",
        "company_name": org.name if org else "Company",
        "company_address": (org.headquarters_address if org else "") or "",
        "company_gst": (org.gst_number if org else "") or "",
        "company_pan": (org.pan_number if org else "") or "",
        "join_date": join.strftime("%d %b %Y") if join else "",
        "employment_type": user.employment_type or "",
        "manager_name": (
            f"{user.manager.first_name} {user.manager.last_name}".strip()
            if user.manager_id
            else ""
        ),
    }
    result = text or ""
    for key, value in mapping.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def generate_offer_letter(
    onboarding: EmployeeOnboarding,
    *,
    actor=None,
    letter_template_id=None,
    include_ctc_annexure: bool = False,
    annual_ctc=None,
    ctc_components: list | None = None,
) -> OfferLetter:
    tpl = None
    if letter_template_id:
        tpl = DocumentLetterTemplate.objects.filter(
            id=letter_template_id, organization=onboarding.organization
        ).first()
    if not tpl:
        tpl = DocumentLetterTemplate.objects.filter(
            organization=onboarding.organization,
            letter_type="offer",
            is_default=True,
        ).first()
    if not tpl:
        tpl = DocumentLetterTemplate.objects.create(
            organization=onboarding.organization,
            name="Standard Offer Letter",
            letter_type="offer",
            subject="Offer of Employment — {{company_name}}",
            body_html=DEFAULT_OFFER_BODY.strip(),
            is_default=True,
            created_by=actor,
        )

    subject = merge_letter_fields(onboarding, tpl.subject)
    body = merge_letter_fields(onboarding, tpl.body_html)

    from onboarding.offer_pdf import resolve_ctc_snapshot, render_offer_pdf_url

    ctc_snapshot = resolve_ctc_snapshot(
        onboarding,
        include_ctc_annexure=include_ctc_annexure,
        annual_ctc=annual_ctc,
        ctc_components=ctc_components,
    )
    if include_ctc_annexure and not ctc_snapshot:
        raise ValueError(
            "CTC annexure requested but no annual CTC found. "
            "Enter annual CTC or assign a salary structure first."
        )

    pdf_url = ""
    try:
        pdf_url = (
            render_offer_pdf_url(
                onboarding, subject, body, ctc_snapshot=ctc_snapshot
            )
            or ""
        )
    except Exception:
        logger.exception("Offer PDF generation failed for onboarding=%s", onboarding.id)

    offer, _created = OfferLetter.objects.update_or_create(
        onboarding=onboarding,
        defaults={
            "letter_template": tpl,
            "subject": subject,
            "body_html": body,
            "pdf_url": pdf_url,
            "source": "generated",
            "include_ctc_annexure": bool(ctc_snapshot),
            "annual_ctc": (
                ctc_snapshot.get("annual_ctc") if ctc_snapshot else None
            ),
            "ctc_snapshot": ctc_snapshot,
            "status": "sent",
            "created_by": actor,
        },
    )
    return offer


def attach_uploaded_offer_letter(
    onboarding: EmployeeOnboarding,
    *,
    file_bytes: bytes,
    filename: str = "offer.pdf",
    subject: str = "",
    actor=None,
) -> OfferLetter:
    from onboarding.offer_pdf import upload_offer_pdf_bytes

    pdf_url = upload_offer_pdf_bytes(onboarding, file_bytes, filename=filename)
    if not pdf_url:
        raise ValueError("Failed to upload offer PDF")

    existing = getattr(onboarding, "offer_letter", None)
    body_html = existing.body_html if existing else ""
    final_subject = (
        subject.strip()
        or (existing.subject if existing else "")
        or f"Offer of Employment — {onboarding.organization.name}"
    )

    offer, _created = OfferLetter.objects.update_or_create(
        onboarding=onboarding,
        defaults={
            "subject": final_subject,
            "body_html": body_html
            or "<p>Offer letter uploaded by HR. Please download the PDF.</p>",
            "pdf_url": pdf_url,
            "source": "uploaded",
            "status": "sent",
            "created_by": actor,
        },
    )
    return offer


def attach_signed_offer_letter(
    onboarding: EmployeeOnboarding,
    *,
    file_bytes: bytes,
    filename: str = "signed_offer.pdf",
    actor=None,
    mark_accepted: bool = True,
    accepted_name: str = "",
    ip: str | None = None,
    ua: str = "",
) -> OfferLetter:
    """Store a scanned/signed offer PDF returned by the hire or uploaded by HR."""
    from onboarding.offer_pdf import upload_offer_pdf_bytes

    offer = getattr(onboarding, "offer_letter", None)
    if not offer:
        offer = OfferLetter.objects.create(
            onboarding=onboarding,
            subject=f"Offer of Employment — {onboarding.organization.name}",
            body_html="<p>Signed offer letter uploaded.</p>",
            status="sent",
            created_by=actor,
        )

    signed_url = upload_offer_pdf_bytes(
        onboarding,
        file_bytes,
        filename=filename,
        public_id=f"offer_signed_{onboarding.id}",
    )
    if not signed_url:
        raise ValueError("Failed to upload signed offer PDF")

    offer.signed_pdf_url = signed_url
    offer.signed_uploaded_at = timezone.now()
    offer.signed_uploaded_by = actor
    update_fields = [
        "signed_pdf_url",
        "signed_uploaded_at",
        "signed_uploaded_by",
        "updated_at",
    ]

    if mark_accepted and offer.status != "accepted":
        offer.status = "accepted"
        offer.accepted_name = (
            accepted_name.strip()
            or (
                f"{onboarding.user.first_name} {onboarding.user.last_name}".strip()
                if onboarding.user_id
                else ""
            )
            or onboarding.user.email
        )
        offer.accepted_at = timezone.now()
        offer.accepted_ip = ip
        offer.accepted_ua = (ua or "")[:2000]
        update_fields.extend(
            ["status", "accepted_name", "accepted_at", "accepted_ip", "accepted_ua"]
        )

    offer.save(update_fields=update_fields)

    if offer.status == "accepted":
        task = onboarding.tasks.filter(
            title__icontains="accept offer", status="pending"
        ).first()
        if task:
            complete_task(
                task,
                completed_by=actor or onboarding.user,
                notes="Signed offer letter uploaded",
            )
    return offer


def accept_offer(
    onboarding: EmployeeOnboarding,
    *,
    accepted_name: str,
    ip: str | None = None,
    ua: str = "",
) -> OfferLetter:
    offer = getattr(onboarding, "offer_letter", None)
    if not offer:
        raise ValueError("No offer letter found.")
    if offer.status == "accepted":
        return offer
    offer.status = "accepted"
    offer.accepted_name = accepted_name.strip()
    offer.accepted_at = timezone.now()
    offer.accepted_ip = ip
    offer.accepted_ua = (ua or "")[:2000]
    offer.save()

    # Complete matching hire task if present
    task = onboarding.tasks.filter(
        title__icontains="accept offer", status="pending"
    ).first()
    if task:
        complete_task(task, completed_by=onboarding.user, notes="Offer accepted")
    return offer


def complete_task(
    task: OnboardingTaskInstance,
    *,
    completed_by=None,
    notes: str = "",
) -> OnboardingTaskInstance:
    task.status = "completed"
    task.completed_at = timezone.now()
    task.completed_by = completed_by
    if notes:
        task.notes = notes
    task.save()
    recompute_progress(task.onboarding)
    return task


def verify_document(
    document: EmployeeDocument,
    *,
    verifier,
    approve: bool,
    rejection_reason: str = "",
) -> EmployeeDocument:
    document.verification_status = "approved" if approve else "rejected"
    document.verified_by = verifier
    document.verified_at = timezone.now()
    document.rejection_reason = "" if approve else (rejection_reason or "Rejected")
    document.save()

    onboarding = document.onboarding
    if onboarding and approve and document.category:
        # Auto-complete hire doc tasks when matching category is approved
        for task in onboarding.tasks.filter(
            requires_document_category=document.category,
            status__in=["pending", "in_progress"],
        ):
            complete_task(task, completed_by=verifier, notes="Document verified")

        # If all KYC docs approved, complete HR verify task
        pending_docs = onboarding.documents.exclude(
            verification_status="approved"
        ).exclude(category="offer")
        if not pending_docs.exists():
            hr_task = onboarding.tasks.filter(
                title__icontains="verify kyc", status__in=["pending", "in_progress"]
            ).first()
            if hr_task:
                complete_task(hr_task, completed_by=verifier, notes="All docs verified")

    return document


@transaction.atomic
def activate_onboarding(
    onboarding: EmployeeOnboarding,
    *,
    actor=None,
    temp_password: str | None = None,
) -> EmployeeOnboarding:
    if onboarding.status == "cancelled":
        raise ValueError("Cannot activate a cancelled onboarding.")

    user = onboarding.user
    user.is_active = True
    user.save(update_fields=["is_active"])

    onboarding.status = "in_progress"
    onboarding.activated_at = timezone.now()
    onboarding.save(update_fields=["status", "activated_at", "updated_at"])

    instantiate_tasks(
        onboarding, phases=["day1", "week1", "day30", "day90"]
    )

    # Notify hire + manager/IT assignees
    try:
        from notifications.utils import notify_user

        notify_user(
            recipient_id=user.id,
            verb="Welcome to Teamzen",
            message=(
                f"Your Teamzen account is active. Complete remaining onboarding tasks."
            ),
            actor_id=getattr(actor, "id", None),
            target_type="Welcome",
            target_id=str(user.id),
            level="personal",
            notification_type="BOTH",
            extra_context={
                "temp_password": temp_password or "",
                "manager_name": (
                    f"{user.manager.first_name} {user.manager.last_name}".strip()
                    if user.manager_id
                    else ""
                ),
            },
        )
        assignee_ids = set(
            onboarding.tasks.exclude(assignee_id=None)
            .exclude(assignee_id=user.id)
            .values_list("assignee_id", flat=True)
        )
        for aid in assignee_ids:
            notify_user(
                recipient_id=aid,
                verb="Onboarding task assigned",
                message=(
                    f"You have onboarding tasks for "
                    f"{user.first_name} {user.last_name}".strip()
                ),
                actor_id=getattr(actor, "id", None),
                target_type="Onboarding",
                target_id=str(onboarding.id),
                level="admin",
            )
    except Exception:
        logger.exception("Activation notifications failed for onboarding=%s", onboarding.id)

    return onboarding


def cancel_onboarding(onboarding: EmployeeOnboarding, *, actor=None) -> EmployeeOnboarding:
    onboarding.status = "cancelled"
    onboarding.save(update_fields=["status", "updated_at"])
    return onboarding


def suggest_document_category(file_name: str = "", title: str = "") -> tuple[str, float]:
    """Heuristic category suggestion (Phase 2 lite — no LLM required)."""
    text = f"{file_name} {title}".lower()
    rules = [
        ("pan", ["pan"]),
        ("aadhaar", ["aadhaar", "aadhar", "uidai"]),
        ("bank_proof", ["cheque", "bank", "passbook", "statement"]),
        ("id_proof", ["passport", "license", "licence", "voter", "id"]),
        ("education", ["degree", "marksheet", "diploma", "certificate"]),
        ("offer", ["offer"]),
        ("signed_policy", ["policy", "handbook", "nda"]),
    ]
    for category, keywords in rules:
        if any(k in text for k in keywords):
            return category, 0.75
    return "other", 0.3
