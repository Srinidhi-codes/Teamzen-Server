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
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
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
        notification_type: str = "PUSH",
        send_to_bots: bool = False,
        image_base64: str | None = None
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            return False
        
        from users.models import CustomUser
        from notifications.tasks import send_notification
        
        image_url = None
        if image_base64:
            import base64
            import re
            import uuid
            import cloudinary.uploader
            
            # Extract base64 data
            raw = image_base64
            match = re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,(.+)$", raw, re.I | re.S)
            if match:
                ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
                raw = match.group(2)
            else:
                ext = "jpg"
            
            try:
                data = base64.b64decode(raw)
                public_id = f"broadcast_{user.id}_{uuid.uuid4().hex[:8]}"
                upload_result = cloudinary.uploader.upload(
                    data,
                    public_id=public_id,
                    folder="media/broadcasts",
                    resource_type="image",
                    overwrite=True,
                    format=ext,
                )
                image_url = upload_result.get("secure_url")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Cloudinary upload failed: {e}")
        
        # In a real large-scale app, this should be a single task that iterates in background
        recipients = CustomUser.objects.filter(organization=user.organization, is_active=True) if user.organization_id else CustomUser.objects.filter(is_active=True)
        for recipient in recipients:
            send_notification.delay(
                recipient_id=recipient.id,
                verb=verb,
                message=message,
                actor_id=user.id,
                notification_type=notification_type,
                level='personal',
                extra_context={"image_url": image_url} if image_url else None
            )
            
        if send_to_bots:
            from notifications.tasks import broadcast_to_bots
            html_message = f"<b>{verb.title()}</b>\n\n{message}"
            broadcast_to_bots.delay(html_message=html_message, image_url=image_url)
            
        return True
