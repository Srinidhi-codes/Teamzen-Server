from typing import List, Optional
import strawberry
from strawberry import auto
from strawberry.types import Info

from feedback.models import Feedback, FeedbackAttachment
from users.graphql.types import UserType


@strawberry.django.type(FeedbackAttachment)
class FeedbackAttachmentType:
    id: strawberry.ID
    file_name: auto
    created_at: auto

    @strawberry.field
    def file_url(self) -> Optional[str]:
        if self.file:
            try:
                return self.file.url
            except Exception:
                return None
        return None


@strawberry.django.type(Feedback)
class FeedbackType:
    id: strawberry.ID
    title: auto
    message: auto
    category: auto
    status: auto
    visibility: auto
    admin_reply: auto
    replied_at: auto
    escalated_to_platform: auto
    escalated_at: auto
    escalation_note: auto
    created_at: auto
    updated_at: auto
    author: UserType
    replied_by: Optional[UserType]
    escalated_by: Optional[UserType]

    @strawberry.field(name="attachments")
    def resolve_attachments(self) -> List[FeedbackAttachmentType]:
        return list(self.attachments.all())

    @strawberry.field(name="attachmentCount")
    def resolve_attachment_count(self) -> int:
        return self.attachments.count()

    @strawberry.field(name="organizationName")
    def resolve_organization_name(self) -> Optional[str]:
        org = getattr(self, "organization", None)
        return getattr(org, "name", None) if org else None

    @strawberry.field(name="organizationId")
    def resolve_organization_id(self) -> Optional[strawberry.ID]:
        oid = getattr(self, "organization_id", None)
        return strawberry.ID(str(oid)) if oid is not None else None
