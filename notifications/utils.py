from django.db.models import Q
from users.models import CustomUser
from notifications.tasks import send_notification


def _dispatch_notification(**payload):
    """
    Prefer Celery for non-blocking delivery, but fall back to an inline call when
    the broker/worker is unavailable so critical leave events are not dropped.
    """
    try:
        send_notification.delay(**payload)
    except Exception:
        send_notification(**payload)

def get_management_ids(user):
    """
    Returns a list of unique recipient IDs who should be notified 
    about a user's action (Manager + Admin/HR/Superadmin).
    """
    recipients = []
    
    # 1. Add direct Manager if exists
    if user.manager:
        recipients.append(user.manager.id)
        
    # 2. Add Admins, HR, and Superadmins of the same organization as a fallback
    admins = CustomUser.objects.filter(
        Q(organization=user.organization) | Q(organization__isnull=True),
        role__in=['superadmin', 'admin', 'hr']
    ).exclude(id=user.id).values_list('id', flat=True)
    
    recipients.extend(list(admins))
    
    # Return unique IDs only
    return list(set(recipients))

def notify_user(recipient_id, verb, message, actor_id=None, target_type=None, target_id=None, level='personal', notification_type='BOTH'):
    """
    Wrapper for send_notification task.
    """
    _dispatch_notification(
        recipient_id=recipient_id,
        verb=verb,
        message=message,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        level=level,
        notification_type=notification_type,
    )

def notify_management(user, verb, message, target_type=None, target_id=None):
    """
    Helps notify all relevant management staff about a user's request.
    """
    recipient_ids = get_management_ids(user)
    for recipient_id in recipient_ids:
        # These are administrative actions, should show up in Admin Panel
        notify_user(
            recipient_id=recipient_id,
            verb=verb,
            message=message,
            actor_id=user.id,
            target_type=target_type,
            target_id=target_id,
            level='admin'
        )

def notify_self(user, verb, message, target_type=None, target_id=None):
    """
    Sends a PUSH-only notification to the actor themselves.
    Useful for synchronizing UI across multiple tabs/sessions.
    """
    _dispatch_notification(
        recipient_id=user.id,
        verb=verb,
        message=message,
        actor_id=user.id,
        target_type=target_type,
        target_id=target_id,
        notification_type='PUSH',
        level='personal'
    )
