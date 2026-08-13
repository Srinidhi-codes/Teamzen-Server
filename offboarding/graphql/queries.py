from __future__ import annotations

import json
from typing import List, Optional

import strawberry
from django.db.models import Count, Q
from strawberry.types import Info

from offboarding.auth import can_view_offboarding, require_auth, require_hr, resolve_org
from offboarding.graphql.types import (
    EmployeeOffboardingType,
    ExitLetterType,
    ExitSessionType,
    FnfSettlementType,
    OffboardingOverviewType,
    OffboardingTaskDefinitionType,
    OffboardingTaskInstanceType,
    OffboardingTemplateType,
)
from offboarding.models import (
    EmployeeOffboarding,
    ExitLetter,
    FnfSettlement,
    OffboardingTemplate,
)
from offboarding.services import get_exit_invite_by_token, ensure_exit_form_upload_on_offboarding


def _task_type(t) -> OffboardingTaskInstanceType:
    assignee_name = None
    if t.assignee_id:
        a = t.assignee
        assignee_name = f"{a.first_name} {a.last_name}".strip() or a.email
    return OffboardingTaskInstanceType(
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
    )


def _settlement_type(s: FnfSettlement | None) -> FnfSettlementType | None:
    if not s:
        return None
    return FnfSettlementType(
        id=strawberry.ID(str(s.id)),
        status=s.status,
        pro_rata_salary=float(s.pro_rata_salary or 0),
        leave_encashment=float(s.leave_encashment or 0),
        bonus_gratuity=float(s.bonus_gratuity or 0),
        other_additions=float(s.other_additions or 0),
        recoveries=float(s.recoveries or 0),
        other_deductions=float(s.other_deductions or 0),
        net_payable=float(s.net_payable or 0),
        notes=s.notes or "",
        statement_pdf_url=s.statement_pdf_url or "",
        snapshot_json=json.dumps(s.snapshot) if s.snapshot else None,
        computed_at=s.computed_at,
        approved_at=s.approved_at,
        acknowledged_at=s.acknowledged_at,
        paid_at=s.paid_at,
    )


def _letter_type(l: ExitLetter, offboarding: EmployeeOffboarding | None = None) -> ExitLetterType:
    from offboarding.letters import merge_exit_letter_fields

    subject = l.subject or ""
    body = l.body_html or ""
    if offboarding is not None:
        subject = merge_exit_letter_fields(offboarding, subject)
        body = merge_exit_letter_fields(offboarding, body)
        # Heal legacy subjects saved as "Relieving - {employee_name}"
        if subject != (l.subject or "") or body != (l.body_html or ""):
            ExitLetter.objects.filter(pk=l.pk).update(subject=subject, body_html=body)

    download = (l.pdf_url or "").strip() or None
    if l.issued_document_id:
        try:
            issued_url = (l.issued_document.download_url or "").strip()
            if issued_url:
                download = issued_url
        except Exception:
            pass
    return ExitLetterType(
        id=strawberry.ID(str(l.id)),
        letter_type=l.letter_type,
        subject=subject,
        body_html=body,
        pdf_url=l.pdf_url or "",
        status=l.status,
        issued_at=l.issued_at,
        download_url=download,
    )


def _offboarding_type(ob: EmployeeOffboarding, *, include_details: bool = True) -> EmployeeOffboardingType:
    user = ob.user
    tasks = []
    settlement = None
    letters = []
    if include_details:
        tasks = [_task_type(t) for t in ob.tasks.select_related("assignee").all()]
        try:
            settlement = _settlement_type(ob.settlement)
        except Exception:
            settlement = None
        letters = [
            _letter_type(l, ob)
            for l in ob.letters.select_related("issued_document").all()
        ]
    return EmployeeOffboardingType(
        id=strawberry.ID(str(ob.id)),
        status=ob.status,
        reason=ob.reason,
        progress_pct=ob.progress_pct,
        exit_date=ob.exit_date,
        last_working_day=ob.last_working_day,
        started_at=ob.started_at,
        completed_at=ob.completed_at,
        notes=ob.notes or "",
        organization_id=strawberry.ID(str(ob.organization_id)),
        user_id=strawberry.ID(str(ob.user_id)),
        user_email=user.email,
        user_name=f"{user.first_name} {user.last_name}".strip() or user.email,
        template_id=strawberry.ID(str(ob.template_id)) if ob.template_id else None,
        template_name=ob.template.name if ob.template_id else None,
        tasks=tasks,
        settlement=settlement,
        letters=letters,
    )


def _template_type(t: OffboardingTemplate) -> OffboardingTemplateType:
    defs = [
        OffboardingTaskDefinitionType(
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
        for d in t.task_definitions.all()
    ]
    return OffboardingTemplateType(
        id=strawberry.ID(str(t.id)),
        name=t.name,
        description=t.description or "",
        organization_id=strawberry.ID(str(t.organization_id)),
        is_default=t.is_default,
        it_contact_id=strawberry.ID(str(t.it_contact_id)) if t.it_contact_id else None,
        task_definitions=defs,
    )


@strawberry.type
class OffboardingQuery:
    @strawberry.field
    def offboarding_overview(
        self, info: Info, organization_id: Optional[strawberry.ID] = None
    ) -> OffboardingOverviewType:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        qs = EmployeeOffboarding.objects.filter(organization=org)
        counts = qs.aggregate(
            total=Count("id"),
            initiated=Count("id", filter=Q(status="initiated")),
            in_progress=Count("id", filter=Q(status="in_progress")),
            settlement_pending=Count("id", filter=Q(status="settlement_pending")),
            letters_pending=Count("id", filter=Q(status="letters_pending")),
            completed=Count("id", filter=Q(status="completed")),
            cancelled=Count("id", filter=Q(status="cancelled")),
        )
        return OffboardingOverviewType(
            total=counts["total"] or 0,
            initiated=counts["initiated"] or 0,
            in_progress=counts["in_progress"] or 0,
            settlement_pending=counts["settlement_pending"] or 0,
            letters_pending=counts["letters_pending"] or 0,
            completed=counts["completed"] or 0,
            cancelled=counts["cancelled"] or 0,
        )

    @strawberry.field
    def offboardings(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
        status: Optional[str] = None,
    ) -> List[EmployeeOffboardingType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        qs = (
            EmployeeOffboarding.objects.filter(organization=org)
            .select_related("user", "template")
            .prefetch_related("tasks", "letters")
        )
        if status:
            qs = qs.filter(status=status)
        return [_offboarding_type(ob, include_details=False) for ob in qs[:200]]

    @strawberry.field
    def employee_offboarding(
        self, info: Info, offboarding_id: strawberry.ID
    ) -> Optional[EmployeeOffboardingType]:
        user = info.context.request.user
        require_auth(user)
        ob = (
            EmployeeOffboarding.objects.select_related("user", "template", "settlement")
            .prefetch_related("tasks__assignee", "letters__issued_document")
            .filter(id=offboarding_id)
            .first()
        )
        if not ob or not can_view_offboarding(user, ob):
            return None
        ensure_exit_form_upload_on_offboarding(ob)
        return _offboarding_type(ob)

    @strawberry.field
    def my_offboarding(self, info: Info) -> Optional[EmployeeOffboardingType]:
        user = info.context.request.user
        require_auth(user)
        ob = (
            EmployeeOffboarding.objects.select_related("user", "template", "settlement")
            .prefetch_related("tasks__assignee", "letters__issued_document")
            .filter(user=user)
            .exclude(status="cancelled")
            .first()
        )
        if not ob:
            return None
        ensure_exit_form_upload_on_offboarding(ob)
        return _offboarding_type(ob)

    @strawberry.field
    def exit_session(self, info: Info, invite_token: str) -> Optional[ExitSessionType]:
        invite = get_exit_invite_by_token(invite_token)
        if not invite:
            return None
        ob = (
            EmployeeOffboarding.objects.select_related("user", "template", "settlement")
            .prefetch_related("tasks__assignee", "letters__issued_document")
            .get(id=invite.offboarding_id)
        )
        ensure_exit_form_upload_on_offboarding(ob)
        return ExitSessionType(offboarding=_offboarding_type(ob), invite_valid=True)

    @strawberry.field
    def offboarding_templates(
        self, info: Info, organization_id: Optional[strawberry.ID] = None
    ) -> List[OffboardingTemplateType]:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, organization_id)
        qs = OffboardingTemplate.objects.filter(organization=org).prefetch_related(
            "task_definitions"
        )
        return [_template_type(t) for t in qs]
