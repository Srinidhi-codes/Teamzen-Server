from django.db.models import Q
from users.models import CustomUser
from notifications.tasks import send_notification

def get_management_ids(user):
    """
    Returns a list of unique recipient IDs who should be notified 
    about a user's action (Manager + Admin/HR/Superadmin).
    """
    recipients = []
    
    # 1. Add direct Manager if exists
    if user.manager:
        recipients.append(user.manager.id)
        
    # 2. Add Admins, HR, and Superadmins of the same organization
    # COMMENTED OUT: We only want to notify the direct manager now.
    """
    admins = CustomUser.objects.filter(
        Q(organization=user.organization) | Q(organization__isnull=True),
        role__in=['superadmin', 'admin', 'hr']
    ).exclude(id=user.id).values_list('id', flat=True)
    
    recipients.extend(list(admins))
    """
    
    # Return unique IDs only
    return list(set(recipients))

def notify_user(recipient_id, verb, message, actor_id=None, target_type=None, target_id=None, level='personal'):
    """
    Wrapper for send_notification task.
    """
    send_notification.delay(
        recipient_id=recipient_id,
        verb=verb,
        message=message,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        level=level
    )

def notify_management(user, verb, message, target_type=None, target_id=None):
    """
    Helps notify all relevant management staff about a user's request.
    """
    recipient_ids = get_management_ids(user)
    for recipient_id in recipient_ids:
        notify_user(
            recipient_id=recipient_id,
            verb=verb,
            message=message,
            actor_id=user.id,
            target_type=target_type,
            target_id=target_id,
        )

def notify_self(user, verb, message, target_type=None, target_id=None):
    """
    Sends a PUSH-only notification to the actor themselves.
    Useful for synchronizing UI across multiple tabs/sessions.
    """
    send_notification.delay(
        recipient_id=user.id,
        verb=verb,
        message=message,
        actor_id=user.id,
        target_type=target_type,
        target_id=target_id,
        notification_type='PUSH',
        level='personal'
    )
