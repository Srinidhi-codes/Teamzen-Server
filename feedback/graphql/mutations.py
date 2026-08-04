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

        # Notify management for employee feedback
        try:
            from notifications.utils import notify_management, notify_user
            from users.models import CustomUser

            if category != "admin_share":
                notify_management(
                    user=user,
                    verb="submitted",
                    message=f"New feedback from {user.first_name or user.email}: {item.title}",
                    target_type="Feedback",
                    target_id=str(item.id),
                )
            else:
                # Notify org employees about admin share
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

        valid = {s[0] for s in Feedback.STATUS_CHOICES}
        if input.status not in valid:
            return FeedbackPayload(success=False, error="Invalid status")

        item.status = input.status
        item.save(update_fields=["status", "updated_at"])
        return FeedbackPayload(success=True, feedback=item)
