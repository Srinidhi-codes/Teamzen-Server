import strawberry
from typing import List, Optional
from notifications.models import Notification
from .types import NotificationType

@strawberry.type
class NotificationQuery:
    @strawberry.field
    def my_notifications(self, info) -> List[NotificationType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []
        return Notification.objects.filter(recipient=user).order_by('-created_at')[:50]

    @strawberry.field
    def unread_notification_count(self, info) -> int:
        user = info.context.request.user
        if not user.is_authenticated:
            return 0
        return Notification.objects.filter(recipient=user, is_read=False).count()
