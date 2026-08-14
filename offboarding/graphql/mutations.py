from __future__ import annotations

from datetime import date
from typing import List, Optional

import strawberry
from strawberry.types import Info

from offboarding.auth import can_view_offboarding, require_auth, require_hr
from offboarding.graphql.types import OffboardingPayload
from offboarding.letters import generate_exit_letter
from offboarding.models import (
    EmployeeOffboarding,
    OffboardingTaskDefinition,
    OffboardingTaskInstance,
    OffboardingTemplate,
)
from offboarding.services import (
    acknowledge_settlement,
    approve_settlement,
    cancel_offboarding,
    complete_task,
    compute_and_save_settlement,
    create_exit_invite,
    exit_portal_url,
    mark_settlement_paid,
    maybe_complete_letters_task,
    skip_task,
    start_offboarding,
)


@strawberry.input
class StartOffboardingInput:
    user_id: strawberry.ID
    exit_date: date
    last_working_day: Optional[date] = None
    reason: str = "resign"
    template_id: Optional[strawberry.ID] = None
    deactivate_now: bool = True
    send_invite: bool = True
    notes: str = ""


@strawberry.input
class SettlementInput:
    offboarding_id: strawberry.ID
    bonus_gratuity: Optional[float] = None
    recoveries: Optional[float] = None
    other_additions: Optional[float] = None
    other_deductions: Optional[float] = None
    notes: str = ""


@strawberry.input
class OffboardingTaskDefInput:
    title: str
    description: str = ""
    assignee_role: str = "employee"
    phase: str = "clearance"
    due_offset_days: int = 0
    requires_document_category: str = ""
    is_required: bool = True
    sort_order: int = 0


@strawberry.input
class UpsertOffboardingTemplateInput:
    name: str
    description: str = ""
    is_default: bool = False
    template_id: Optional[strawberry.ID] = None
    it_contact_id: Optional[strawberry.ID] = None
    tasks: Optional[List[OffboardingTaskDefInput]] = None


@strawberry.type
class OffboardingMutation:
    @strawberry.mutation
    def start_offboarding(self, info: Info, input: StartOffboardingInput) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target = User.objects.filter(id=input.user_id).first()
        if not target:
            return OffboardingPayload(error="User not found")
        if actor.role != "superadmin" and target.organization_id != actor.organization_id:
            return OffboardingPayload(error="Not authorized")
        try:
            ob, raw = start_offboarding(
                actor=actor,
                user=target,
                exit_date=input.exit_date,
                last_working_day=input.last_working_day,
                reason=input.reason,
                template_id=input.template_id,
                deactivate_now=input.deactivate_now,
                send_invite=input.send_invite,
                notes=input.notes,
            )
            return OffboardingPayload(
                success=True,
                offboarding_id=strawberry.ID(str(ob.id)),
                invite_token=raw,
                invite_url=exit_portal_url(raw) if raw else None,
            )
        except Exception as e:
            return OffboardingPayload(error=str(e))

    @strawberry.mutation
    def cancel_offboarding(
        self, info: Info, offboarding_id: strawberry.ID
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=offboarding_id).first()
        if not ob:
            return OffboardingPayload(error="Not found")
        if actor.role != "superadmin" and ob.organization_id != actor.organization_id:
            return OffboardingPayload(error="Not authorized")
        cancel_offboarding(ob, actor=actor)
        return OffboardingPayload(success=True, offboarding_id=strawberry.ID(str(ob.id)))

    @strawberry.mutation
    def complete_offboarding_task(
        self,
        info: Info,
        task_id: strawberry.ID,
        notes: str = "",
        invite_token: Optional[str] = None,
    ) -> OffboardingPayload:
        task = OffboardingTaskInstance.objects.select_related("offboarding").filter(
            id=task_id
        ).first()
        if not task:
            return OffboardingPayload(error="Task not found")

        actor = None
        if invite_token:
            from offboarding.services import get_exit_invite_by_token

            invite = get_exit_invite_by_token(invite_token)
            if not invite or invite.offboarding_id != task.offboarding_id:
                return OffboardingPayload(error="Invalid invite")
            actor = invite.offboarding.user
            if task.assignee_role != "employee" and task.assignee_id != actor.id:
                return OffboardingPayload(error="Not your task")
        else:
            actor = info.context.request.user
            require_auth(actor)
            if not can_view_offboarding(actor, task.offboarding):
                return OffboardingPayload(error="Not authorized")

        complete_task(task, completed_by=actor, notes=notes)
        return OffboardingPayload(
            success=True, offboarding_id=strawberry.ID(str(task.offboarding_id))
        )

    @strawberry.mutation
    def skip_offboarding_task(
        self, info: Info, task_id: strawberry.ID, notes: str = ""
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        task = OffboardingTaskInstance.objects.select_related("offboarding").filter(
            id=task_id
        ).first()
        if not task:
            return OffboardingPayload(error="Task not found")
        skip_task(task, actor=actor, notes=notes)
        return OffboardingPayload(
            success=True, offboarding_id=strawberry.ID(str(task.offboarding_id))
        )

    @strawberry.mutation
    def compute_fnf_settlement(
        self, info: Info, input: SettlementInput
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=input.offboarding_id).first()
        if not ob:
            return OffboardingPayload(error="Not found")
        if actor.role != "superadmin" and ob.organization_id != actor.organization_id:
            return OffboardingPayload(error="Not authorized")
        try:
            s = compute_and_save_settlement(
                ob,
                actor=actor,
                bonus_gratuity=input.bonus_gratuity,
                recoveries=input.recoveries,
                other_additions=input.other_additions,
                other_deductions=input.other_deductions,
                notes=input.notes,
            )
            return OffboardingPayload(
                success=True, offboarding_id=strawberry.ID(str(ob.id))
            )
        except Exception as e:
            return OffboardingPayload(error=str(e))

    @strawberry.mutation
    def approve_fnf_settlement(
        self, info: Info, offboarding_id: strawberry.ID
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=offboarding_id).select_related(
            "settlement"
        ).first()
        if not ob:
            return OffboardingPayload(error="Settlement not found")
        try:
            settlement = ob.settlement
        except Exception:
            return OffboardingPayload(error="Settlement not found")
        approve_settlement(settlement, actor=actor)
        return OffboardingPayload(success=True, offboarding_id=strawberry.ID(str(ob.id)))

    @strawberry.mutation
    def acknowledge_fnf_settlement(
        self, info: Info, invite_token: str
    ) -> OffboardingPayload:
        from offboarding.services import get_exit_invite_by_token

        invite = get_exit_invite_by_token(invite_token)
        if not invite:
            return OffboardingPayload(error="Invalid invite")
        ob = invite.offboarding
        try:
            settlement = ob.settlement
        except Exception:
            return OffboardingPayload(error="Settlement not found")
        try:
            acknowledge_settlement(settlement)
            return OffboardingPayload(
                success=True, offboarding_id=strawberry.ID(str(ob.id))
            )
        except Exception as e:
            return OffboardingPayload(error=str(e))

    @strawberry.mutation
    def mark_fnf_paid(
        self, info: Info, offboarding_id: strawberry.ID
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=offboarding_id).select_related(
            "settlement"
        ).first()
        if not ob:
            return OffboardingPayload(error="Settlement not found")
        try:
            settlement = ob.settlement
        except Exception:
            return OffboardingPayload(error="Settlement not found")
        mark_settlement_paid(settlement, actor=actor)
        return OffboardingPayload(success=True, offboarding_id=strawberry.ID(str(ob.id)))

    @strawberry.mutation
    def generate_exit_letter(
        self,
        info: Info,
        offboarding_id: strawberry.ID,
        letter_type: str,
        letter_template_id: Optional[strawberry.ID] = None,
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=offboarding_id).first()
        if not ob:
            return OffboardingPayload(error="Not found")
        try:
            generate_exit_letter(
                ob,
                letter_type=letter_type,
                actor=actor,
                letter_template_id=letter_template_id,
            )
            maybe_complete_letters_task(ob, actor=actor)
            return OffboardingPayload(
                success=True, offboarding_id=strawberry.ID(str(ob.id))
            )
        except Exception as e:
            return OffboardingPayload(error=str(e))

    @strawberry.mutation
    def resend_exit_invite(
        self, info: Info, offboarding_id: strawberry.ID
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        ob = EmployeeOffboarding.objects.filter(id=offboarding_id).first()
        if not ob:
            return OffboardingPayload(error="Not found")
        raw, _ = create_exit_invite(ob, created_by=actor)
        try:
            from notifications.utils import notify_user

            notify_user(
                recipient_id=ob.user_id,
                verb="Exit portal link",
                message=f"Your F&F portal link: {exit_portal_url(raw)}",
                actor_id=actor.id,
                target_type="EmployeeOffboarding",
                target_id=str(ob.id),
                level="personal",
                notification_type="BOTH",
                extra_context={"exit_url": exit_portal_url(raw)},
            )
        except Exception:
            pass
        return OffboardingPayload(
            success=True,
            offboarding_id=strawberry.ID(str(ob.id)),
            invite_token=raw,
            invite_url=exit_portal_url(raw),
        )

    @strawberry.mutation
    def upsert_offboarding_template(
        self, info: Info, input: UpsertOffboardingTemplateInput
    ) -> OffboardingPayload:
        actor = info.context.request.user
        require_hr(actor)
        org = actor.organization
        if not org and actor.role != "superadmin":
            return OffboardingPayload(error="No organization")
        if not org:
            from organizations.models import Organization

            org = Organization.objects.order_by("id").first()

        if input.template_id:
            tpl = OffboardingTemplate.objects.filter(
                id=input.template_id, organization=org
            ).first()
            if not tpl:
                return OffboardingPayload(error="Template not found")
            tpl.name = input.name
            tpl.description = input.description
            tpl.is_default = input.is_default
            if input.it_contact_id:
                tpl.it_contact_id = input.it_contact_id
            tpl.save()
        else:
            tpl = OffboardingTemplate.objects.create(
                organization=org,
                name=input.name,
                description=input.description,
                is_default=input.is_default,
                it_contact_id=input.it_contact_id,
                created_by=actor,
            )

        if input.is_default:
            OffboardingTemplate.objects.filter(organization=org).exclude(id=tpl.id).update(
                is_default=False
            )

        if input.tasks is not None:
            tpl.task_definitions.all().delete()
            for i, t in enumerate(input.tasks):
                OffboardingTaskDefinition.objects.create(
                    template=tpl,
                    title=t.title,
                    description=t.description,
                    assignee_role=t.assignee_role,
                    phase=t.phase,
                    due_offset_days=t.due_offset_days,
                    requires_document_category=t.requires_document_category,
                    is_required=t.is_required,
                    sort_order=t.sort_order if t.sort_order else i * 10,
                )

        return OffboardingPayload(success=True, offboarding_id=strawberry.ID(str(tpl.id)))
