from __future__ import annotations

from typing import Optional

import strawberry
from django.db import transaction
from django.utils import timezone
from strawberry.types import Info

from onboarding.auth import can_view_onboarding, require_auth, require_hr, resolve_org
from onboarding.graphql.queries import (
    _letter_template_type,
    _onboarding_type,
    _task_def_type,
    _template_type,
)
from onboarding.graphql.types import (
    AcceptOfferInput,
    CreateOnboardingTemplateInput,
    EmployeeOnboardingType,
    GenerateOfferInput,
    LetterTemplateInput,
    LetterTemplateType,
    OnboardingPayload,
    OnboardingTaskDefinitionType,
    OnboardingTemplateType,
    PolishOfferLetterInput,
    PolishOfferLetterPayload,
    StartOnboardingForEmployeeInput,
    StartPreboardingInput,
    SuggestOnboardingTasksInput,
    SuggestOnboardingTasksPayload,
    SuggestedOnboardingTaskType,
    UpdateLetterTemplateInput,
    UpdateOnboardingTemplateInput,
    UpdatePreboardingProfileInput,
    UpsertTaskDefinitionInput,
)
from onboarding.models import (
    DocumentLetterTemplate,
    EmployeeDocument,
    EmployeeOnboarding,
    OnboardingTaskDefinition,
    OnboardingTaskInstance,
    OnboardingTemplate,
)
from onboarding.services import (
    accept_offer,
    activate_onboarding,
    cancel_onboarding,
    complete_task,
    create_preboarding_invite,
    generate_offer_letter,
    get_invite_by_token,
    preboarding_portal_url,
    start_onboarding_for_existing_user,
    start_preboarding,
    verify_document,
)


def _client_ip(request) -> Optional[str]:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _notify_preboarding_invite(onboarding, raw_token: str, actor=None):
    from notifications.utils import notify_user

    url = preboarding_portal_url(raw_token)
    offer = None
    try:
        offer = onboarding.offer_letter
    except Exception:
        offer = None
    if offer is None:
        from onboarding.models import OfferLetter

        offer = OfferLetter.objects.filter(onboarding_id=onboarding.id).first()

    pdf_url = (getattr(offer, "pdf_url", None) or "").strip()
    if not pdf_url:
        print(
            f"WARNING: preboarding invite for onboarding={onboarding.id} "
            "has no offer pdf_url — email will go without PDF attachment"
        )

    notify_user(
        recipient_id=onboarding.user_id,
        verb="Complete your preboarding",
        message=(
            f"Welcome! Complete your documents and offer acceptance before day one. "
            f"Portal: {url}"
        ),
        actor_id=getattr(actor, "id", None),
        target_type="PreboardingInvite",
        target_id=str(onboarding.id),
        level="personal",
        notification_type="BOTH",
        extra_context={
            "invite_url": url,
            "invite_token": raw_token,
            "offer_pdf_url": pdf_url,
            "offer_subject": (offer.subject if offer else "") or "Offer Letter",
        },
    )


def _notify_offer_letter(onboarding, actor=None):
    """Send / resend offer PDF by email (with invite link when possible)."""
    from notifications.utils import notify_user

    offer = getattr(onboarding, "offer_letter", None)
    if not offer or not offer.pdf_url:
        raise ValueError("Generate or upload an offer PDF before emailing.")

    invite_url = ""
    try:
        raw, _invite = create_preboarding_invite(onboarding, created_by=actor)
        invite_url = preboarding_portal_url(raw)
    except Exception:
        invite_url = getattr(
            __import__("django.conf", fromlist=["settings"]).settings,
            "FRONTEND_URL",
            "http://localhost:3000",
        )

    notify_user(
        recipient_id=onboarding.user_id,
        verb="Your offer letter is ready",
        message=(
            f"Your offer letter is attached. Review and accept it in the preboarding portal: "
            f"{invite_url}"
        ),
        actor_id=getattr(actor, "id", None),
        target_type="PreboardingInvite",
        target_id=str(onboarding.id),
        level="personal",
        notification_type="BOTH",
        extra_context={
            "invite_url": invite_url or "#",
            "offer_pdf_url": offer.pdf_url,
            "offer_subject": offer.subject or "Offer Letter",
        },
    )


@strawberry.type
class OnboardingMutation:
    @strawberry.mutation
    def start_preboarding(
        self, info: Info, input: StartPreboardingInput
    ) -> OnboardingPayload:
        user = info.context.request.user
        require_hr(user)
        try:
            org = resolve_org(user, input.organization_id)
            onboarding, raw_token = start_preboarding(
                actor=user,
                organization=org,
                email=input.email.strip().lower(),
                first_name=input.first_name.strip(),
                last_name=input.last_name.strip(),
                password=input.password,
                department_id=input.department_id,
                designation_id=input.designation_id,
                office_location_id=input.office_location_id,
                manager_id=input.manager_id,
                employment_type=input.employment_type or "full_time",
                date_of_joining=input.date_of_joining,
                phone_number=input.phone_number or "",
                template_id=input.template_id,
                generate_offer=input.generate_offer,
                letter_template_id=input.letter_template_id,
                include_ctc_annexure=input.include_ctc_annexure,
                annual_ctc=input.annual_ctc,
            )
            if input.send_invite and raw_token:
                try:
                    onboarding = EmployeeOnboarding.objects.select_related(
                        "user", "offer_letter", "organization"
                    ).get(id=onboarding.id)
                    _notify_preboarding_invite(onboarding, raw_token, actor=user)
                except Exception:
                    import traceback

                    print("Failed to send preboarding invite email:")
                    print(traceback.format_exc())
            return OnboardingPayload(
                success=True,
                invite_token=raw_token,
                invite_url=preboarding_portal_url(raw_token) if raw_token else None,
                onboarding_id=strawberry.ID(str(onboarding.id)),
            )
        except Exception as e:
            return OnboardingPayload(error=str(e))

    @strawberry.mutation
    def start_onboarding_for_employee(
        self, info: Info, input: StartOnboardingForEmployeeInput
    ) -> OnboardingPayload:
        """Attach onboarding to an existing employee without creating a new user."""
        from django.contrib.auth import get_user_model

        user = info.context.request.user
        require_hr(user)
        User = get_user_model()
        try:
            employee = User.objects.select_related("organization").get(id=input.user_id)
            if user.role != "superadmin":
                if not user.organization_id or employee.organization_id != user.organization_id:
                    return OnboardingPayload(error="Unauthorized")

            existing = (
                EmployeeOnboarding.objects.filter(user_id=employee.id)
                .exclude(status="cancelled")
                .first()
            )
            if existing:
                return OnboardingPayload(
                    success=False,
                    error=(
                        f"Onboarding already exists (status={existing.status}). "
                        "Open it from the Onboarding board."
                    ),
                    onboarding_id=strawberry.ID(str(existing.id)),
                )

            onboarding, raw_token = start_onboarding_for_existing_user(
                actor=user,
                user=employee,
                template_id=input.template_id,
                generate_offer=input.generate_offer,
                letter_template_id=input.letter_template_id,
                include_ctc_annexure=input.include_ctc_annexure,
                annual_ctc=input.annual_ctc,
                send_invite=input.send_invite,
            )
            if input.send_invite and raw_token:
                try:
                    onboarding = EmployeeOnboarding.objects.select_related(
                        "user", "offer_letter", "organization"
                    ).get(id=onboarding.id)
                    _notify_preboarding_invite(onboarding, raw_token, actor=user)
                except Exception:
                    import traceback

                    print("Failed to send preboarding invite email:")
                    print(traceback.format_exc())
            return OnboardingPayload(
                success=True,
                invite_token=raw_token,
                invite_url=preboarding_portal_url(raw_token) if raw_token else None,
                onboarding_id=strawberry.ID(str(onboarding.id)),
            )
        except Exception as e:
            return OnboardingPayload(error=str(e))

    @strawberry.mutation
    def send_preboarding_invite(
        self, info: Info, onboarding_id: strawberry.ID
    ) -> OnboardingPayload:
        user = info.context.request.user
        require_hr(user)
        try:
            ob = EmployeeOnboarding.objects.select_related(
                "user", "offer_letter"
            ).get(id=onboarding_id)
            if user.role != "superadmin" and ob.organization_id != user.organization_id:
                return OnboardingPayload(error="Unauthorized")
            raw, _invite = create_preboarding_invite(ob, created_by=user)
            if ob.status == "invited":
                ob.status = "preboarding"
                ob.save(update_fields=["status", "updated_at"])
            _notify_preboarding_invite(ob, raw, actor=user)
            return OnboardingPayload(
                success=True,
                invite_token=raw,
                invite_url=preboarding_portal_url(raw),
            )
        except Exception as e:
            return OnboardingPayload(error=str(e))

    @strawberry.mutation
    def activate_employee_onboarding(
        self,
        info: Info,
        onboarding_id: strawberry.ID,
        temp_password: Optional[str] = None,
    ) -> EmployeeOnboardingType:
        user = info.context.request.user
        require_hr(user)
        ob = EmployeeOnboarding.objects.select_related(
            "user", "template", "offer_letter"
        ).get(id=onboarding_id)
        if user.role != "superadmin" and ob.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        activate_onboarding(ob, actor=user, temp_password=temp_password)
        ob.refresh_from_db()
        return _onboarding_type(
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .get(id=ob.id)
        )

    @strawberry.mutation
    def cancel_onboarding(
        self, info: Info, onboarding_id: strawberry.ID
    ) -> EmployeeOnboardingType:
        user = info.context.request.user
        require_hr(user)
        ob = EmployeeOnboarding.objects.get(id=onboarding_id)
        if user.role != "superadmin" and ob.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        cancel_onboarding(ob, actor=user)
        return _onboarding_type(ob, include_details=False)

    @strawberry.mutation
    def complete_onboarding_task(
        self,
        info: Info,
        task_id: strawberry.ID,
        notes: Optional[str] = None,
    ) -> EmployeeOnboardingType:
        user = info.context.request.user
        require_auth(user)
        task = OnboardingTaskInstance.objects.select_related(
            "onboarding", "onboarding__user"
        ).get(id=task_id)
        ob = task.onboarding
        allowed = (
            user.role in ("superadmin", "admin", "hr")
            or task.assignee_id == user.id
            or ob.user_id == user.id
        )
        if not allowed:
            raise Exception("Unauthorized")
        if user.role not in ("superadmin", "admin", "hr"):
            if user.organization_id and ob.organization_id != user.organization_id:
                raise Exception("Unauthorized")
        complete_task(task, completed_by=user, notes=notes or "")
        return _onboarding_type(
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .get(id=ob.id)
        )

    @strawberry.mutation
    def verify_employee_document(
        self,
        info: Info,
        document_id: strawberry.ID,
        approve: bool,
        rejection_reason: Optional[str] = None,
    ) -> EmployeeOnboardingType:
        user = info.context.request.user
        require_hr(user)
        doc = EmployeeDocument.objects.select_related("onboarding").get(id=document_id)
        if user.role != "superadmin" and doc.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        verify_document(
            doc,
            verifier=user,
            approve=approve,
            rejection_reason=rejection_reason or "",
        )
        if not approve:
            try:
                from notifications.utils import notify_user

                notify_user(
                    recipient_id=doc.user_id,
                    verb="Document rejected",
                    message=(
                        f"Your {doc.category} document was rejected. "
                        f"{rejection_reason or 'Please re-upload.'}"
                    ),
                    actor_id=user.id,
                    target_type="EmployeeDocument",
                    target_id=str(doc.id),
                    level="personal",
                    extra_context={
                        "category": doc.category,
                        "rejection_reason": rejection_reason or "",
                    },
                )
            except Exception:
                pass

        ob_id = doc.onboarding_id
        if not ob_id:
            raise Exception("Document is not linked to an onboarding")
        return _onboarding_type(
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .get(id=ob_id)
        )

    @strawberry.mutation
    def generate_offer_for_onboarding(
        self,
        info: Info,
        onboarding_id: Optional[strawberry.ID] = None,
        letter_template_id: Optional[strawberry.ID] = None,
        input: Optional[GenerateOfferInput] = None,
    ) -> EmployeeOnboardingType:
        user = info.context.request.user
        require_hr(user)

        include_ctc = False
        annual_ctc = None
        ctc_components = None
        send_email = False
        if input:
            onboarding_id = input.onboarding_id
            letter_template_id = input.letter_template_id or letter_template_id
            include_ctc = bool(input.include_ctc_annexure)
            annual_ctc = input.annual_ctc
            send_email = bool(input.send_email)
            if input.ctc_components:
                ctc_components = [
                    {
                        "name": c.name,
                        "amount": c.amount,
                        "frequency": c.frequency or "monthly",
                    }
                    for c in input.ctc_components
                ]

        if not onboarding_id:
            raise Exception("onboardingId is required")

        ob = EmployeeOnboarding.objects.select_related("user", "organization").get(
            id=onboarding_id
        )
        if user.role != "superadmin" and ob.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        generate_offer_letter(
            ob,
            actor=user,
            letter_template_id=letter_template_id,
            include_ctc_annexure=include_ctc,
            annual_ctc=annual_ctc,
            ctc_components=ctc_components,
        )
        ob = EmployeeOnboarding.objects.select_related(
            "user",
            "user__department",
            "user__designation",
            "template",
            "offer_letter",
        ).prefetch_related("tasks__assignee", "documents").get(id=ob.id)
        if send_email:
            try:
                _notify_offer_letter(ob, actor=user)
            except Exception:
                pass
        return _onboarding_type(ob)

    @strawberry.mutation
    def send_offer_letter_email(
        self, info: Info, onboarding_id: strawberry.ID
    ) -> OnboardingPayload:
        user = info.context.request.user
        require_hr(user)
        try:
            ob = EmployeeOnboarding.objects.select_related(
                "user", "organization", "offer_letter"
            ).get(id=onboarding_id)
            if user.role != "superadmin" and ob.organization_id != user.organization_id:
                return OnboardingPayload(error="Unauthorized")
            _notify_offer_letter(ob, actor=user)
            return OnboardingPayload(success=True)
        except Exception as e:
            return OnboardingPayload(error=str(e))

    @strawberry.mutation
    def accept_offer_letter(
        self, info: Info, input: AcceptOfferInput
    ) -> EmployeeOnboardingType:
        request = info.context.request
        onboarding = None
        if input.invite_token:
            invite = get_invite_by_token(input.invite_token)
            if not invite:
                raise Exception("Invalid or expired invite")
            onboarding = invite.onboarding
            if not invite.used_at:
                invite.used_at = timezone.now()
                invite.save(update_fields=["used_at"])
        else:
            user = request.user
            require_auth(user)
            if input.onboarding_id:
                onboarding = EmployeeOnboarding.objects.get(id=input.onboarding_id)
                if not can_view_onboarding(user, onboarding):
                    raise Exception("Unauthorized")
            else:
                onboarding = EmployeeOnboarding.objects.filter(user=user).first()
        if not onboarding:
            raise Exception("Onboarding not found")
        if not input.accepted_name or len(input.accepted_name.strip()) < 2:
            raise Exception("Please type your full name to accept")
        accept_offer(
            onboarding,
            accepted_name=input.accepted_name,
            ip=_client_ip(request),
            ua=request.META.get("HTTP_USER_AGENT", ""),
        )
        return _onboarding_type(
            EmployeeOnboarding.objects.select_related(
                "user",
                "user__department",
                "user__designation",
                "template",
                "offer_letter",
            )
            .prefetch_related("tasks__assignee", "documents")
            .get(id=onboarding.id)
        )

    @strawberry.mutation
    def update_preboarding_profile(
        self, info: Info, input: UpdatePreboardingProfileInput
    ) -> EmployeeOnboardingType:
        invite = get_invite_by_token(input.invite_token)
        if not invite:
            raise Exception("Invalid or expired invite")
        user = invite.onboarding.user
        fields = [
            "phone_number",
            "date_of_birth",
            "gender",
            "bank_account_number",
            "bank_ifsc_code",
            "pan_number",
            "aadhar_number",
            "uan_number",
        ]
        for field in fields:
            val = getattr(input, field)
            if val is not None:
                setattr(user, field, val)
        user.save()

        # Complete bank details task when key fields present
        if user.bank_account_number and user.bank_ifsc_code and user.pan_number:
            task = invite.onboarding.tasks.filter(
                title__icontains="bank details",
                status__in=["pending", "in_progress"],
            ).first()
            if task:
                complete_task(task, completed_by=user, notes="Profile completed")

        return _onboarding_type(
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

    @strawberry.mutation
    def create_onboarding_template(
        self, info: Info, input: CreateOnboardingTemplateInput
    ) -> OnboardingTemplateType:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, input.organization_id)
        with transaction.atomic():
            if input.is_default:
                OnboardingTemplate.objects.filter(
                    organization=org, is_default=True
                ).update(is_default=False)
            tpl = OnboardingTemplate.objects.create(
                organization=org,
                name=input.name,
                description=input.description or "",
                department_id=input.department_id,
                designation_id=input.designation_id,
                employment_type=input.employment_type or "",
                is_default=input.is_default,
                it_contact_id=input.it_contact_id,
                created_by=user,
            )
            for t in input.tasks or []:
                OnboardingTaskDefinition.objects.create(
                    template=tpl,
                    title=t.title,
                    description=t.description or "",
                    assignee_role=t.assignee_role,
                    phase=t.phase,
                    due_offset_days=t.due_offset_days,
                    requires_document_category=t.requires_document_category or "",
                    is_required=t.is_required,
                    sort_order=t.sort_order,
                )
        return _template_type(
            OnboardingTemplate.objects.prefetch_related("task_definitions").get(id=tpl.id)
        )

    @strawberry.mutation
    def update_onboarding_template(
        self, info: Info, input: UpdateOnboardingTemplateInput
    ) -> OnboardingTemplateType:
        user = info.context.request.user
        require_hr(user)
        tpl = OnboardingTemplate.objects.get(id=input.id)
        if user.role != "superadmin" and tpl.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        if input.is_default:
            OnboardingTemplate.objects.filter(
                organization_id=tpl.organization_id, is_default=True
            ).exclude(id=tpl.id).update(is_default=False)
        for field in (
            "name",
            "description",
            "department_id",
            "designation_id",
            "employment_type",
            "is_default",
            "it_contact_id",
        ):
            val = getattr(input, field)
            if val is not None:
                setattr(tpl, field, val)
        tpl.save()
        return _template_type(
            OnboardingTemplate.objects.prefetch_related("task_definitions").get(id=tpl.id)
        )

    @strawberry.mutation
    def upsert_task_definition(
        self, info: Info, input: UpsertTaskDefinitionInput
    ) -> OnboardingTaskDefinitionType:
        user = info.context.request.user
        require_hr(user)
        tpl = OnboardingTemplate.objects.get(id=input.template_id)
        if user.role != "superadmin" and tpl.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        if input.id:
            d = OnboardingTaskDefinition.objects.get(id=input.id, template=tpl)
        else:
            d = OnboardingTaskDefinition(template=tpl)
        d.title = input.title
        d.description = input.description or ""
        d.assignee_role = input.assignee_role
        d.phase = input.phase
        d.due_offset_days = input.due_offset_days
        d.requires_document_category = input.requires_document_category or ""
        d.is_required = input.is_required
        d.sort_order = input.sort_order
        d.save()
        return _task_def_type(d)

    @strawberry.mutation
    def delete_task_definition(self, info: Info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        require_hr(user)
        d = OnboardingTaskDefinition.objects.select_related("template").get(id=id)
        if user.role != "superadmin" and d.template.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        d.delete()
        return True

    @strawberry.mutation
    def reorder_onboarding_task_definitions(
        self,
        info: Info,
        template_id: strawberry.ID,
        task_ids: list[strawberry.ID],
    ) -> OnboardingTemplateType:
        """Persist a new sort order for template tasks (drag-and-drop)."""
        from django.db import transaction as db_transaction

        user = info.context.request.user
        require_hr(user)
        tpl = OnboardingTemplate.objects.get(id=template_id)
        if user.role != "superadmin" and tpl.organization_id != user.organization_id:
            raise Exception("Unauthorized")

        existing = {
            str(d.id): d
            for d in OnboardingTaskDefinition.objects.filter(template=tpl)
        }
        ordered_ids = [str(tid) for tid in task_ids]
        if set(ordered_ids) != set(existing.keys()):
            raise Exception(
                "task_ids must include every task on this template exactly once"
            )

        with db_transaction.atomic():
            for index, tid in enumerate(ordered_ids):
                d = existing[tid]
                new_order = (index + 1) * 10
                if d.sort_order != new_order:
                    d.sort_order = new_order
                    d.save(update_fields=["sort_order"])

        return _template_type(
            OnboardingTemplate.objects.prefetch_related("task_definitions").get(id=tpl.id)
        )

    @strawberry.mutation
    def create_letter_template(
        self, info: Info, input: LetterTemplateInput
    ) -> LetterTemplateType:
        user = info.context.request.user
        require_hr(user)
        org = resolve_org(user, input.organization_id)
        if input.is_default:
            DocumentLetterTemplate.objects.filter(
                organization=org, letter_type=input.letter_type, is_default=True
            ).update(is_default=False)
        t = DocumentLetterTemplate.objects.create(
            organization=org,
            name=input.name,
            letter_type=input.letter_type or "offer",
            subject=input.subject or "",
            body_html=input.body_html,
            is_default=input.is_default,
            created_by=user,
        )
        return _letter_template_type(t)

    @strawberry.mutation
    def update_letter_template(
        self, info: Info, input: UpdateLetterTemplateInput
    ) -> LetterTemplateType:
        user = info.context.request.user
        require_hr(user)
        t = DocumentLetterTemplate.objects.get(id=input.id)
        if user.role != "superadmin" and t.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        if input.is_default:
            DocumentLetterTemplate.objects.filter(
                organization_id=t.organization_id,
                letter_type=t.letter_type,
                is_default=True,
            ).exclude(id=t.id).update(is_default=False)
        for field in ("name", "subject", "body_html", "is_default"):
            val = getattr(input, field)
            if val is not None:
                setattr(t, field, val)
        t.save()
        return _letter_template_type(t)

    @strawberry.mutation
    def suggest_onboarding_tasks(
        self, info: Info, input: SuggestOnboardingTasksInput
    ) -> SuggestOnboardingTasksPayload:
        user = info.context.request.user
        require_hr(user)
        try:
            org = resolve_org(user, input.organization_id)
            from onboarding.ai_services import suggest_onboarding_tasks as suggest

            raw = suggest(
                org.id,
                input.prompt,
                employment_type=input.employment_type or "",
                department=input.department or "",
            )
            tasks = [
                SuggestedOnboardingTaskType(
                    title=t["title"],
                    description=t["description"],
                    assignee_role=t["assignee_role"],
                    phase=t["phase"],
                    due_offset_days=t["due_offset_days"],
                    requires_document_category=t["requires_document_category"],
                    is_required=t["is_required"],
                    sort_order=t["sort_order"],
                )
                for t in raw
            ]
            applied = 0
            if input.apply_to_template_id and tasks:
                tpl = OnboardingTemplate.objects.get(id=input.apply_to_template_id)
                if (
                    user.role != "superadmin"
                    and tpl.organization_id != user.organization_id
                ):
                    raise Exception("Unauthorized")
                with transaction.atomic():
                    for t in tasks:
                        OnboardingTaskDefinition.objects.create(
                            template=tpl,
                            title=t.title,
                            description=t.description,
                            assignee_role=t.assignee_role,
                            phase=t.phase,
                            due_offset_days=t.due_offset_days,
                            requires_document_category=t.requires_document_category,
                            is_required=t.is_required,
                            sort_order=t.sort_order,
                        )
                        applied += 1
            return SuggestOnboardingTasksPayload(
                success=True, tasks=tasks, applied_count=applied
            )
        except Exception as e:
            return SuggestOnboardingTasksPayload(success=False, error=str(e), tasks=[])

    @strawberry.mutation
    def polish_offer_letter(
        self, info: Info, input: PolishOfferLetterInput
    ) -> PolishOfferLetterPayload:
        user = info.context.request.user
        require_hr(user)
        try:
            org = resolve_org(user, input.organization_id)
            from onboarding.ai_services import polish_offer_letter as polish

            body = polish(
                org.id,
                input.body_html,
                tone=input.tone or "professional",
            )
            if input.save and input.letter_template_id:
                t = DocumentLetterTemplate.objects.get(id=input.letter_template_id)
                if (
                    user.role != "superadmin"
                    and t.organization_id != user.organization_id
                ):
                    raise Exception("Unauthorized")
                t.body_html = body
                t.save(update_fields=["body_html", "updated_at"])
            return PolishOfferLetterPayload(success=True, body_html=body)
        except Exception as e:
            return PolishOfferLetterPayload(success=False, error=str(e), body_html="")
