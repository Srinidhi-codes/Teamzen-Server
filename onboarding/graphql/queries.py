from __future__ import annotations

from datetime import date
from typing import List, Optional

import strawberry
from django.db.models import Count, Q
from django.utils import timezone
from strawberry.types import Info

from onboarding.auth import can_view_onboarding, require_auth, require_hr, resolve_org
from onboarding.graphql.types import (
    EmployeeDocumentType,
    EmployeeOnboardingType,
    LetterTemplateType,
    OfferLetterType,
    OnboardingOverviewType,
    OnboardingTaskDefinitionType,
    OnboardingTaskInstanceType,
    OnboardingTemplateType,
)
from onboarding.models import (
    DocumentLetterTemplate,
    EmployeeDocument,
    EmployeeOnboarding,
    OnboardingTaskInstance,
    OnboardingTemplate,
)
from onboarding.services import ensure_default_template, get_invite_by_token


def _task_def_type(d) -> OnboardingTaskDefinitionType:
    return OnboardingTaskDefinitionType(
        id=strawberry.ID(str(d.id)),
        title=d.title,
        description=d.description or "",
        assignee_role=d.assignee_role,
        phase=d.phase,
        due_offset_days=d.due_offset_days,
        requires_document_category=d.requires_document_category or "",
        is_required=d.is_required,
        sort_order=d.sort_order,
    )


def _template_type(t: OnboardingTemplate) -> OnboardingTemplateType:
    defs = list(t.task_definitions.all())
    return OnboardingTemplateType(
        id=strawberry.ID(str(t.id)),
        name=t.name,
        description=t.description or "",
        organization_id=strawberry.ID(str(t.organization_id)),
        department_id=strawberry.ID(str(t.department_id)) if t.department_id else None,
        designation_id=strawberry.ID(str(t.designation_id)) if t.designation_id else None,
        employment_type=t.employment_type or "",
        is_default=t.is_default,
        it_contact_id=strawberry.ID(str(t.it_contact_id)) if t.it_contact_id else None,
        task_definitions=[_task_def_type(d) for d in defs],
    )


def _task_type(t: OnboardingTaskInstance) -> OnboardingTaskInstanceType:
    assignee_name = None
    if t.assignee_id:
        assignee_name = (
            f"{t.assignee.first_name} {t.assignee.last_name}".strip() or t.assignee.email
        )
    return OnboardingTaskInstanceType(
        id=strawberry.ID(str(t.id)),
        title=t.title,
        description=t.description or "",
        assignee_role=t.assignee_role,
        phase=t.phase,
        status=t.status,
        due_at=t.due_at,
        is_required=t.is_required,
        requires_document_category=t.requires_document_category or "",
        sort_order=t.sort_order,
        notes=t.notes or "",
        assignee_id=strawberry.ID(str(t.assignee_id)) if t.assignee_id else None,
        assignee_name=assignee_name,
        completed_at=t.completed_at,
        completed_by_id=strawberry.ID(str(t.completed_by_id)) if t.completed_by_id else None,
    )


def _doc_type(d: EmployeeDocument) -> EmployeeDocumentType:
    url = None
    try:
        url = d.file.url if d.file else None
    except Exception:
        url = None
    return EmployeeDocumentType(
        id=strawberry.ID(str(d.id)),
        category=d.category,
        title=d.title or "",
        file_name=d.file_name or "",
        file_url=url,
        verification_status=d.verification_status,
        rejection_reason=d.rejection_reason or "",
        expiry_date=d.expiry_date,
        ai_suggested_category=d.ai_suggested_category or "",
        ai_confidence=d.ai_confidence,
        created_at=d.created_at,
        verified_at=d.verified_at,
    )


def _offer_type(o, onboarding=None) -> Optional[OfferLetterType]:
    if not o:
        return None
    annual = None
    if o.annual_ctc is not None:
        try:
            annual = float(o.annual_ctc)
        except Exception:
            annual = None

    subject = o.subject or ""
    body_html = o.body_html or ""
    # Safety: if stored letter still has tokens, merge now for display
    if ("{{" in subject or "{{" in body_html) and onboarding is not None:
        from onboarding.services import merge_letter_fields

        subject = merge_letter_fields(onboarding, subject)
        body_html = merge_letter_fields(onboarding, body_html)

    return OfferLetterType(
        id=strawberry.ID(str(o.id)),
        subject=subject,
        body_html=body_html,
        pdf_url=o.pdf_url or "",
        signed_pdf_url=getattr(o, "signed_pdf_url", None) or "",
        signed_uploaded_at=getattr(o, "signed_uploaded_at", None),
        status=o.status,
        source=getattr(o, "source", None) or "generated",
        include_ctc_annexure=bool(getattr(o, "include_ctc_annexure", False)),
        annual_ctc=annual,
        accepted_name=o.accepted_name or "",
        accepted_at=o.accepted_at,
        updated_at=getattr(o, "updated_at", None),
    )


def _onboarding_type(
    ob: EmployeeOnboarding, *, include_details: bool = True
) -> EmployeeOnboardingType:
    # Backfill verification for hires who already finished onboarding
    if ob.status == "completed":
        from onboarding.services import sync_user_verified_from_onboarding

        sync_user_verified_from_onboarding(ob, notify=False)

    user = ob.user
    tasks = []
    docs = []
    offer = None
    if include_details:
        tasks = [_task_type(t) for t in ob.tasks.select_related("assignee").all()]
        docs = [_doc_type(d) for d in ob.documents.all()]
        offer = _offer_type(getattr(ob, "offer_letter", None), onboarding=ob)

    return EmployeeOnboardingType(
        id=strawberry.ID(str(ob.id)),
        status=ob.status,
        progress_pct=ob.progress_pct,
        join_date=ob.join_date,
        started_at=ob.started_at,
        completed_at=ob.completed_at,
        activated_at=ob.activated_at,
        notes=ob.notes or "",
        organization_id=strawberry.ID(str(ob.organization_id)),
        user_id=strawberry.ID(str(ob.user_id)),
        user_email=user.email,
        user_name=f"{user.first_name} {user.last_name}".strip() or user.email,
        department_name=getattr(user.department, "name", None),
        designation_name=getattr(user.designation, "name", None),
        template_id=strawberry.ID(str(ob.template_id)) if ob.template_id else None,
        template_name=ob.template.name if ob.template_id else None,
        tasks=tasks,
        documents=docs,
        offer_letter=offer,
    )


def _letter_template_type(t: DocumentLetterTemplate) -> LetterTemplateType:
    return LetterTemplateType(
        id=strawberry.ID(str(t.id)),
        name=t.name,
        letter_type=t.letter_type,
        subject=t.subject or "",
        body_html=t.body_html or "",
        is_default=t.is_default,
        organization_id=strawberry.ID(str(t.organization_id)),
    )


@strawberry.type
class OnboardingQuery:
    @strawberry.field
    def onboarding_overview(
        self, info: Info, organization_id: Optional[strawberry.ID] = None
    ) -> OnboardingOverviewType:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        qs = EmployeeOnboarding.objects.filter(organization=org)
        counts = qs.aggregate(
            total=Count("id"),
            invited=Count("id", filter=Q(status="invited")),
            preboarding=Count("id", filter=Q(status="preboarding")),
            in_progress=Count("id", filter=Q(status="in_progress")),
            completed=Count("id", filter=Q(status="completed")),
            cancelled=Count("id", filter=Q(status="cancelled")),
        )
        pending_verifications = EmployeeDocument.objects.filter(
            organization=org, verification_status="pending"
        ).count()
        overdue_tasks = OnboardingTaskInstance.objects.filter(
            onboarding__organization=org,
            status__in=["pending", "in_progress"],
            due_at__lt=timezone.localdate(),
        ).count()
        return OnboardingOverviewType(
            total=counts["total"] or 0,
            invited=counts["invited"] or 0,
            preboarding=counts["preboarding"] or 0,
            in_progress=counts["in_progress"] or 0,
            completed=counts["completed"] or 0,
            cancelled=counts["cancelled"] or 0,
            pending_verifications=pending_verifications,
            overdue_tasks=overdue_tasks,
        )

    @strawberry.field
    def onboardings(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[EmployeeOnboardingType]:
        user = info.context.request.user
        require_auth(user)
        if user.role in ("superadmin", "admin", "hr"):
            org = resolve_org(user, organization_id)
            qs = EmployeeOnboarding.objects.filter(organization=org).select_related(
                "user", "user__department", "user__designation", "template"
            )
        elif user.role == "manager":
            qs = EmployeeOnboarding.objects.filter(
                user__manager=user
            ).select_related("user", "user__department", "user__designation", "template")
        else:
            qs = EmployeeOnboarding.objects.filter(user=user).select_related(
                "user", "user__department", "user__designation", "template"
            )

        if status:
            qs = qs.filter(status=status)
        else:
            # Active board hides cancelled (e.g. after F&F starts).
            qs = qs.exclude(status="cancelled")
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )
        return [_onboarding_type(o, include_details=False) for o in qs.order_by("-created_at")[:200]]

    @strawberry.field
    def onboarding_detail(
        self, info: Info, id: strawberry.ID
    ) -> Optional[EmployeeOnboardingType]:
        user = info.context.request.user
        require_auth(user)
        ob = (
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .filter(id=id)
            .first()
        )
        if not ob or not can_view_onboarding(user, ob):
            return None
        return _onboarding_type(ob)

    @strawberry.field
    def my_onboarding(self, info: Info) -> Optional[EmployeeOnboardingType]:
        user = info.context.request.user
        require_auth(user)
        ob = (
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .filter(user=user)
            .exclude(status="cancelled")
            .first()
        )
        if not ob:
            return None
        return _onboarding_type(ob)

    @strawberry.field
    def my_assigned_onboarding_tasks(
        self, info: Info
    ) -> List[OnboardingTaskInstanceType]:
        user = info.context.request.user
        require_auth(user)
        tasks = (
            OnboardingTaskInstance.objects.filter(
                assignee=user, status__in=["pending", "in_progress"]
            )
            .select_related("assignee")
            .order_by("due_at", "sort_order")[:100]
        )
        return [_task_type(t) for t in tasks]

    @strawberry.field
    def onboarding_templates(
        self, info: Info, organization_id: Optional[strawberry.ID] = None
    ) -> List[OnboardingTemplateType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        ensure_default_template(org, created_by=user)
        templates = OnboardingTemplate.objects.filter(organization=org).prefetch_related(
            "task_definitions"
        )
        return [_template_type(t) for t in templates]

    @strawberry.field
    def letter_templates(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
        letter_type: Optional[str] = None,
    ) -> List[LetterTemplateType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        qs = DocumentLetterTemplate.objects.filter(organization=org)
        if letter_type:
            qs = qs.filter(letter_type=letter_type)
        return [_letter_template_type(t) for t in qs]

    @strawberry.field
    def pending_document_verifications(
        self, info: Info, organization_id: Optional[strawberry.ID] = None
    ) -> List[EmployeeDocumentType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        docs = EmployeeDocument.objects.filter(
            organization=org, verification_status="pending"
        ).order_by("created_at")[:100]
        return [_doc_type(d) for d in docs]

    @strawberry.field
    def preboarding_session(
        self, info: Info, invite_token: str
    ) -> Optional[EmployeeOnboardingType]:
        invite = get_invite_by_token(invite_token)
        if not invite:
            return None
        ob = (
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .get(id=invite.onboarding_id)
        )
        return _onboarding_type(ob)
