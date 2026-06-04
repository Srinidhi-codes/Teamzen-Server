import strawberry
from datetime import datetime
from typing import Optional, List
from notifications.models import Notification
from users.graphql.types import UserType

@strawberry.django.type(Notification)
class NotificationType:
    id: strawberry.ID
    recipient: 'UserType'
    actor: Optional['UserType']
    verb: str
    target_type: Optional[str]
    target_id: Optional[str]
    message: str
    notification_type: str
    level: str
    is_read: bool
    created_at: datetime
    updated_at: datetime

@strawberry.type
class PaginatedNotificationResponse:
    results: List[NotificationType]
    total: int
    page: int
    page_size: int

