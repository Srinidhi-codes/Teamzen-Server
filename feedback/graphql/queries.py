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

        qs = Feedback.objects.select_related("author", "replied_by", "organization").prefetch_related(
            "attachments"
        )

        if user.role == "superadmin":
            # Platform superadmins can see all orgs (optionally filter)
            if organization_id:
                qs = qs.filter(organization_id=organization_id)
            elif org:
                qs = qs.filter(organization=org)
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
                Feedback.objects.select_related("author", "replied_by", "organization")
                .prefetch_related("attachments")
                .get(id=id)
            )
        except Feedback.DoesNotExist:
            return None

        if user.role != "superadmin" and item.organization_id != getattr(user, "organization_id", None):
            raise GraphQLError("Not authorized")

        if not _is_admin_role(user) and user.role != "superadmin" and item.author_id != user.id and item.visibility != "org":
            raise GraphQLError("Not authorized")

        return item
