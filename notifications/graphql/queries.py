import strawberry
from typing import List, Optional
from strawberry.types import Info
from notifications.models import Notification
from .types import NotificationType, PaginatedNotificationResponse
from graphql_utils.pagination import get_paginated_results

@strawberry.type
class NotificationQuery:
    @strawberry.field
    def my_notifications(
        self, 
        info: Info, 
        level: Optional[str] = None,
        is_read: Optional[bool] = None,
        page: int = 1,
        page_size: int = 10
    ) -> PaginatedNotificationResponse:
        user = info.context.request.user
        if not user.is_authenticated:
            return PaginatedNotificationResponse(results=[], total=0, page=page, page_size=page_size)
        
        queryset = Notification.objects.filter(recipient=user).order_by('-created_at')
        if level:
            queryset = queryset.filter(level=level)
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read)
            
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedNotificationResponse(**paginated)


    @strawberry.field
    def unread_notification_count(self, info, level: Optional[str] = None) -> int:
        user = info.context.request.user
        if not user.is_authenticated:
            return 0
        
        queryset = Notification.objects.filter(recipient=user, is_read=False)
        if level:
            queryset = queryset.filter(level=level)
            
        return queryset.count()
