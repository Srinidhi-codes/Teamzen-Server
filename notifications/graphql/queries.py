import strawberry
from typing import List, Optional
from notifications.models import Notification
from .types import NotificationType

@strawberry.type
class NotificationQuery:
    @strawberry.field
    def my_notifications(self, info, level: Optional[str] = None) -> List[NotificationType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []
        
        queryset = Notification.objects.filter(recipient=user).order_by('-created_at')
        if level:
            queryset = queryset.filter(level=level)
            
        return queryset[:50]

    @strawberry.field
    def unread_notification_count(self, info, level: Optional[str] = None) -> int:
        user = info.context.request.user
        if not user.is_authenticated:
            return 0
        
        queryset = Notification.objects.filter(recipient=user, is_read=False)
        if level:
            queryset = queryset.filter(level=level)
            
        return queryset.count()
