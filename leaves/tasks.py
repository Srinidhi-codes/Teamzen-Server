from celery import shared_task
from leaves.services import run_monthly_accrual, run_carry_forward

@shared_task
def run_monthly_leave_accrual():
    """
    Monthly scheduled task to run leave accruals.
    """
    run_monthly_accrual()

@shared_task
def run_yearly_carry_forward():
    """
    Yearly task to process carry forward balances.
    """
    run_carry_forward()

@shared_task
def detect_ooo_and_prompt_leave():
    """
    Daily scheduled task to check Google Calendars for 'OOO' or 'WFH' events
    without an associated LeaveRequest, and proactively ping the user.
    """
    import logging
    from integrations.google_calendar import list_busy_events
    from integrations.models import GoogleCalendarConnection
    from leaves.models import LeaveRequest
    from notifications.proactive import notify_bot_user
    from django.utils import timezone
    
    logger = logging.getLogger(__name__)
    today = timezone.localdate()
    connections = GoogleCalendarConnection.objects.all().select_related('user')
    
    count = 0
    for conn in connections:
        user = conn.user
        events = list_busy_events(user.id, today, today)
        
        has_ooo_or_wfh = False
        event_summary = ""
        
        for event in events:
            summary = event.get('summary', '').lower()
            if any(keyword in summary for keyword in ['ooo', 'out of office', 'wfh', 'working from home']):
                has_ooo_or_wfh = True
                event_summary = event.get('summary', 'OOO/WFH')
                break
                
        if has_ooo_or_wfh:
            # Check if there is an existing leave request for today
            leave_exists = LeaveRequest.objects.filter(
                user=user,
                start_date__lte=today,
                end_date__gte=today,
                status__in=['approved', 'pending']
            ).exists()
            
            if not leave_exists:
                msg = (
                    f"Hi {user.first_name or 'there'}! I noticed an **'{event_summary}'** event on your calendar today, "
                    f"but I don't see an official leave request in the system.\n\n"
                    f"Would you like me to apply for leave or WFH for you?"
                )
                notify_bot_user(user.id, msg)
                count += 1
                logger.info(f"Proactively notified {user.email} about {event_summary} event.")
                
    return f"Notified {count} users about missing leave requests."
