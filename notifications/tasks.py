from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

@shared_task(name="notifications.tasks.send_notification")
def send_notification(recipient_id, verb, message, actor_id=None, notification_type='BOTH', target_type=None, target_id=None, level='personal'):
    """
    Asynchronous task to send notifications via multiple channels.
    """
    try:
        recipient = User.objects.get(id=recipient_id)
        actor = User.objects.get(id=actor_id) if actor_id else None
        
        # 1. Create Notification record in DB for push/tracking
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            verb=verb,
            message=message,
            notification_type=notification_type,
            target_type=target_type,
            target_id=target_id,
            level=level
        )

        # 2. Send Push if requested (Implementation for Channels)
        if notification_type in ['PUSH', 'BOTH']:
            import asyncio
            from channels.layers import get_channel_layer
            
            async def push_to_channel():
                channel_layer = get_channel_layer()
                await channel_layer.group_send(
                    f"user_{recipient_id}",
                    {
                        "type": "send_notification",
                        "message": {
                            "id": str(notification.id),
                            "verb": verb,
                            "message": message,
                            "level": level,
                            "createdAt": notification.created_at.isoformat(),
                            "isRead": notification.is_read,
                            "actor": {
                                "id": str(actor.id) if actor else None,
                                "firstName": actor.first_name if actor else "System",
                                "lastName": actor.last_name if actor else ""
                            }
                        }
                    }
                )
            
            try:
                # Use native asyncio to avoid asgiref thread-deadlocks inside Celery
                asyncio.run(push_to_channel())
            except RuntimeError:
                # If an event loop is already running (e.g., in some test environments or specific worker pools),
                # fallback to asgiref as a last resort.
                from asgiref.sync import async_to_sync
                async_to_sync(push_to_channel)()
                
        # 3. Send Email if requested
        if notification_type in ['EMAIL', 'BOTH']:
            # Dispatch to a separate background worker to prevent slow SMTP connections from blocking this thread
            send_email_notification.delay(recipient_id, "Notification: " + verb, message)
            
        return f"Notification {notification.id} processed for {recipient.email}"
    except Exception as e:
        return f"Error sending notification: {str(e)}"

@shared_task(name="notifications.tasks.send_email_notification")
def send_email_notification(recipient_id, subject, message):
    """
    Dedicated task for sending emails with a strict timeout to prevent SMTP freezes.
    """
    try:
        recipient = User.objects.get(id=recipient_id)
        
        # Free Render IPs are frequently heavily rate-limited or blocked by smtp.gmail.com.
        # We must enforce a strict connection timeout so the Celery worker doesn't hang for 135 seconds.
        from django.core.mail import EmailMessage
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        # 10 second timeout to fail fast if Gmail drops the connection
        import socket
        socket.setdefaulttimeout(10)
        
        email.send(fail_silently=False)
        return f"Email sent successfully to {recipient.email}"
    except socket.timeout:
        return f"CRITICAL: Email to {recipient.email} FAILED. smtp.gmail.com blocked the Render IP (10s Connection Timeout)."
    except Exception as e:
        return f"Error sending email: {str(e)}"

@shared_task(name="notifications.tasks.cleanup_read_notifications")
def cleanup_read_notifications():
    """
    Delete notifications that have been read for more than 24 hours.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    threshold = timezone.now() - timedelta(hours=24)
    # updated_at will change when is_read is set to True
    deleted_count, _ = Notification.objects.filter(is_read=True, updated_at__lte=threshold).delete()
    return f"Deleted {deleted_count} old notifications."
