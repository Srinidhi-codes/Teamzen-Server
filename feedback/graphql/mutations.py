from typing import Optional
import strawberry
from strawberry.types import Info
from graphql import GraphQLError
from django.utils import timezone

from feedback.models import Feedback
from feedback.graphql.types import FeedbackType


def _require_user(info: Info):
    request = getattr(info.context, "request", None)
    user = getattr(request, "user", None) if request is not None else None
    if user is None:
        user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise GraphQLError("Authentication required")
    return user


def _is_admin_role(user) -> bool:
    return getattr(user, "role", None) in ("admin", "superadmin", "hr")


def _is_company_admin(user) -> bool:
    return getattr(user, "role", None) in ("admin", "hr")


def _notify_company_admins(actor, message, target_id):
    from notifications.utils import notify_user
    from users.models import CustomUser

    org_id = getattr(actor, "organization_id", None)
    if not org_id:
        return
    recipients = CustomUser.objects.filter(
        organization_id=org_id,
        role__in=("admin", "hr"),
        is_active=True,
    ).exclude(id=actor.id)
    for recipient in recipients.iterator():
        notify_user(
            recipient_id=recipient.id,
            verb="submitted",
            message=message,
            actor_id=actor.id,
            target_type="Feedback",
            target_id=str(target_id),
            level="admin",
        )


def _notify_superadmins(actor, message, target_id):
    from notifications.utils import notify_user
    from users.models import CustomUser

    recipients = CustomUser.objects.filter(role="superadmin", is_active=True).exclude(id=actor.id)
    for recipient in recipients.iterator():
        notify_user(
            recipient_id=recipient.id,
            verb="escalated",
            message=message,
            actor_id=actor.id,
            target_type="Feedback",
            target_id=str(target_id),
            level="admin",
        )


@strawberry.input
class CreateFeedbackInput:
    title: str
    message: str
    category: Optional[str] = "general"
    visibility: Optional[str] = None  # default derived from category/role
    organization_id: Optional[strawberry.ID] = None  # required for superadmin without org


@strawberry.input
class ReplyFeedbackInput:
    id: strawberry.ID
    reply: str
    status: Optional[str] = None


@strawberry.input
class UpdateFeedbackStatusInput:
    id: strawberry.ID
    status: str


@strawberry.input
class EscalateFeedbackInput:
    id: strawberry.ID
    note: Optional[str] = None


@strawberry.type
class FeedbackPayload:
    success: bool
    error: Optional[str] = None
    feedback: Optional[FeedbackType] = None


@strawberry.type
class FeedbackMutation:
    @strawberry.mutation
    def create_feedback(self, info: Info, input: CreateFeedbackInput) -> FeedbackPayload:
        user = _require_user(info)

        title = (input.title or "").strip()
        message = (input.message or "").strip()
        if len(title) < 3:
            return FeedbackPayload(success=False, error="Title must be at least 3 characters")
        if len(message) < 10:
            return FeedbackPayload(success=False, error="Message must be at least 10 characters")

        category = (input.category or "general").strip().lower()
        valid_cats = {c[0] for c in Feedback.CATEGORY_CHOICES}
        if category not in valid_cats:
            return FeedbackPayload(success=False, error="Invalid category")

        # Only admins may post org-wide admin shares
        if category == "admin_share" and not _is_admin_role(user):
            return FeedbackPayload(success=False, error="Only admins can post organization shares")

        # Resolve target organization
        org_id = getattr(user, "organization_id", None)
        if input.organization_id:
            if user.role != "superadmin" and str(input.organization_id) != str(org_id):
                return FeedbackPayload(success=False, error="Not authorized for that organization")
            org_id = input.organization_id
        if not org_id:
            return FeedbackPayload(
                success=False,
                error="Select an organization to share with (superadmin has no default org)",
            )

        visibility = (input.visibility or "").strip().lower()
        if not visibility:
            visibility = "org" if category == "admin_share" else "private"
        if visibility not in {v[0] for v in Feedback.VISIBILITY_CHOICES}:
            return FeedbackPayload(success=False, error="Invalid visibility")
        if visibility == "org" and not _is_admin_role(user) and category != "admin_share":
            visibility = "private"

        item = Feedback.objects.create(
            organization_id=org_id,
            author=user,
            title=title[:255],
            message=message,
            category=category,
            visibility=visibility,
            status="open",
        )

        try:
            from notifications.utils import notify_user
            from users.models import CustomUser

            if category != "admin_share":
                # Employee / internal notes go to company admin & HR only — not platform superadmin.
                _notify_company_admins(
                    user,
                    f"New feedback from {user.first_name or user.email}: {item.title}",
                    item.id,
                )
            else:
                recipients = CustomUser.objects.filter(
                    organization_id=org_id,
                    is_active=True,
                ).exclude(id=user.id)
                for recipient in recipients.iterator():
                    notify_user(
                        recipient_id=recipient.id,
                        verb="shared",
                        message=f"New update from admin: {item.title}",
                        actor_id=user.id,
                        target_type="Feedback",
                        target_id=str(item.id),
                        level="personal",
                    )
        except Exception:
            pass

        return FeedbackPayload(success=True, feedback=item)

    @strawberry.mutation
    def reply_to_feedback(self, info: Info, input: ReplyFeedbackInput) -> FeedbackPayload:
        user = _require_user(info)
        if not _is_admin_role(user):
            return FeedbackPayload(success=False, error="Not authorized")

        try:
            item = Feedback.objects.get(id=input.id)
        except Feedback.DoesNotExist:
            return FeedbackPayload(success=False, error="Feedback not found")

        if user.role != "superadmin" and item.organization_id != user.organization_id:
            return FeedbackPayload(success=False, error="Not authorized")
        if user.role == "superadmin" and not item.escalated_to_platform and item.category != "admin_share":
            return FeedbackPayload(success=False, error="This feedback has not been forwarded by the company admin")

        reply = (input.reply or "").strip()
        if len(reply) < 2:
            return FeedbackPayload(success=False, error="Reply is too short")

        item.admin_reply = reply
        item.replied_by = user
        item.replied_at = timezone.now()
        if input.status:
            valid = {s[0] for s in Feedback.STATUS_CHOICES}
            if input.status in valid:
                item.status = input.status
        elif item.status == "open":
            item.status = "in_progress"
        item.save()

        try:
            from notifications.utils import notify_user

            notify_user(
                recipient_id=item.author_id,
                verb="replied",
                message=f"Admin replied to your feedback: {item.title}",
                actor_id=user.id,
                target_type="Feedback",
                target_id=str(item.id),
                level="personal",
            )
        except Exception:
            pass

        return FeedbackPayload(success=True, feedback=item)

    @strawberry.mutation
    def update_feedback_status(self, info: Info, input: UpdateFeedbackStatusInput) -> FeedbackPayload:
        user = _require_user(info)
        if not _is_admin_role(user):
            return FeedbackPayload(success=False, error="Not authorized")

        try:
            item = Feedback.objects.get(id=input.id)
        except Feedback.DoesNotExist:
            return FeedbackPayload(success=False, error="Feedback not found")

        if user.role != "superadmin" and item.organization_id != user.organization_id:
            return FeedbackPayload(success=False, error="Not authorized")
        if user.role == "superadmin" and not item.escalated_to_platform and item.category != "admin_share":
            return FeedbackPayload(success=False, error="This feedback has not been forwarded by the company admin")

        valid = {s[0] for s in Feedback.STATUS_CHOICES}
        if input.status not in valid:
            return FeedbackPayload(success=False, error="Invalid status")

        item.status = input.status
        item.save(update_fields=["status", "updated_at"])
        return FeedbackPayload(success=True, feedback=item)

    @strawberry.mutation
    def escalate_feedback(self, info: Info, input: EscalateFeedbackInput) -> FeedbackPayload:
        """Company admin/HR forwards a reviewed item to platform superadmin."""
        user = _require_user(info)
        if not _is_company_admin(user):
            return FeedbackPayload(success=False, error="Only company admins can forward feedback to Teamzen")

        try:
            item = Feedback.objects.select_related("author", "organization").get(id=input.id)
        except Feedback.DoesNotExist:
            return FeedbackPayload(success=False, error="Feedback not found")

        if item.organization_id != user.organization_id:
            return FeedbackPayload(success=False, error="Not authorized")
        if item.category == "admin_share":
            return FeedbackPayload(success=False, error="Organization shares stay inside the company")
        if item.escalated_to_platform:
            return FeedbackPayload(success=False, error="This feedback was already sent to Teamzen")

        note = (input.note or "").strip()
        item.escalated_to_platform = True
        item.escalated_by = user
        item.escalated_at = timezone.now()
        item.escalation_note = note
        if item.status == "open":
            item.status = "in_progress"
        item.save()

        try:
            author_name = item.author.first_name or item.author.email
            org_name = getattr(item.organization, "name", "") or "an organization"
            extra = f" Note: {note}" if note else ""
            _notify_superadmins(
                user,
                f"{user.first_name or user.email} forwarded feedback from {author_name} ({org_name}): {item.title}.{extra}",
                item.id,
            )
        except Exception:
            pass

        return FeedbackPayload(success=True, feedback=item)
