import strawberry
from notifications.models import Notification
from .types import NotificationType

@strawberry.type
class NotificationMutation:
    @strawberry.mutation
    def mark_notification_as_read(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        try:
            notification = Notification.objects.get(id=id, recipient=user)
            notification.is_read = True
            notification.save()
            return True
        except Notification.DoesNotExist:
            return False

    @strawberry.mutation
    def delete_notification(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        try:
            notification = Notification.objects.get(id=id, recipient=user)
            notification.delete()
            return True
        except Notification.DoesNotExist:
            return False

    @strawberry.mutation
    def delete_all_read_notifications(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        Notification.objects.filter(recipient=user, is_read=True).delete()
        return True

    @strawberry.mutation
    def mark_all_notifications_as_read(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
        return True

    @strawberry.mutation
    def send_custom_notification(
        self, 
        info, 
        recipient_id: strawberry.ID, 
        message: str, 
        verb: str = "announcement",
        notification_type: str = "BOTH"
    ) -> bool:
        user = info.context.request.user
        # In a real app, check if user is admin/hr
        if not user.is_authenticated or user.role not in ['admin', 'hr']:
            return False
        
        from notifications.tasks import send_notification
        send_notification.delay(
            recipient_id=recipient_id,
            verb=verb,
            message=message,
            actor_id=user.id,
            notification_type=notification_type,
            level='personal'
        )
        return True

    @strawberry.mutation
    def send_broadcast_notification(
        self,
        info,
        message: str,
        verb: str = "broadcast",
        notification_type: str = "PUSH"
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role != 'admin':
            return False
        
        from users.models import CustomUser
        from notifications.tasks import send_notification
        
        # In a real large-scale app, this should be a single task that iterates in background
        recipients = CustomUser.objects.filter(organization=user.organization, is_active=True)
        for recipient in recipients:
            send_notification.delay(
                recipient_id=recipient.id,
                verb=verb,
                message=message,
                actor_id=user.id,
                notification_type=notification_type,
                level='personal'
            )
        return True
