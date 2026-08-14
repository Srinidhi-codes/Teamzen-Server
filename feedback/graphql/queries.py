from typing import List, Optional
import strawberry
from strawberry.types import Info
from graphql import GraphQLError
from django.db.models import Q

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


@strawberry.type
class FeedbackQuery:
    @strawberry.field
    def feedback_list(
        self,
        info: Info,
        status: Optional[str] = None,
        category: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[FeedbackType]:
        user = _require_user(info)
        org = user.organization

        qs = Feedback.objects.select_related(
            "author", "replied_by", "escalated_by", "organization"
        ).prefetch_related("attachments")

        if user.role == "superadmin":
            # Platform superadmins only see items company admins forwarded,
            # plus org-wide shares and notes they authored themselves.
            if organization_id:
                qs = qs.filter(organization_id=organization_id)
            elif org:
                qs = qs.filter(organization=org)
            qs = qs.filter(
                Q(escalated_to_platform=True)
                | Q(category="admin_share")
                | Q(visibility="org")
                | Q(author=user)
            )
        else:
            if not org:
                return []
            qs = qs.filter(organization=org)

            if not _is_admin_role(user):
                qs = qs.filter(Q(author=user) | Q(visibility="org"))

        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(category=category)

        return list(qs[:200])

    @strawberry.field
    def feedback_item(self, info: Info, id: strawberry.ID) -> Optional[FeedbackType]:
        user = _require_user(info)
        try:
            item = (
                Feedback.objects.select_related("author", "replied_by", "escalated_by", "organization")
                .prefetch_related("attachments")
                .get(id=id)
            )
        except Feedback.DoesNotExist:
            return None

        if user.role != "superadmin" and item.organization_id != getattr(user, "organization_id", None):
            raise GraphQLError("Not authorized")

        if user.role == "superadmin":
            visible_to_platform = (
                item.escalated_to_platform
                or item.category == "admin_share"
                or item.visibility == "org"
                or item.author_id == user.id
            )
            if not visible_to_platform:
                raise GraphQLError("Not authorized")

        if not _is_admin_role(user) and user.role != "superadmin" and item.author_id != user.id and item.visibility != "org":
            raise GraphQLError("Not authorized")

        return item
