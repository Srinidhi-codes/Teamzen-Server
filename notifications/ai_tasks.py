from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta, date, datetime
from users.models import CustomUser
from attendance.models import AttendanceRecord
from leaves.models import LeaveBalance, LeaveRequest
from notifications.utils import notify_user, notify_management

@shared_task(name="notifications.ai_tasks.notify_expiring_leaves")
def notify_expiring_leaves():
    """
    Notify users of unused leaves expiring at year-end.
    Runs weekly in December.
    """
    today = timezone.localdate()
    if today.month != 12:
        return "Not December, skipping expiring leaves notification."

    year = today.year
    balances = LeaveBalance.objects.filter(
        year=year,
        is_active=True,
        user__is_active=True
    ).select_related('user', 'leave_type')

    count = 0
    for balance in balances:
        available = balance.get_available_balance()
        if available > 0:
            notify_user(
                recipient_id=balance.user.id,
                verb="Unused Leave Expiry",
                message=f"You have {available} days of {balance.leave_type.name} remaining. Use them before they expire on Dec 31st!",
                level="personal"
            )
            count += 1
    
    return f"Notified {count} users about expiring leaves."

@shared_task(name="notifications.ai_tasks.notify_missing_checkout")
def notify_missing_checkout():
    """
    Notify users of missing checkout from yesterday.
    Runs daily in the morning (e.g., 9 AM).
    """
    yesterday = timezone.localdate() - timedelta(days=1)
    
    missing_records = AttendanceRecord.objects.filter(
        attendance_date=yesterday,
        login_time__isnull=False,
        logout_time__isnull=True
    ).select_related('user')

    count = 0
    for record in missing_records:
        notify_user(
            recipient_id=record.user.id,
            verb="Missing Checkout",
            message=f"It looks like you forgot to clock out yesterday ({yesterday}). Please submit a correction request.",
            target_type="Attendance Correction",
            level="personal"
        )
        count += 1
    
    return f"Notified {count} users about missing checkout."

@shared_task(name="notifications.ai_tasks.alert_low_attendance")
def alert_low_attendance():
    """
    Alert users when weekly attendance drops below 80%.
    Runs every Monday morning for the previous week.
    """
    today = timezone.localdate()
    start_date = today - timedelta(days=7)
    end_date = today - timedelta(days=1)
    
    # We assume 5 working days in a week for simplicity
    working_days = 5
    threshold = 0.8 * working_days # 4 days
    
    users = CustomUser.objects.filter(is_active=True, role='employee')
    
    count = 0
    for user in users:
        present_count = AttendanceRecord.objects.filter(
            user=user,
            attendance_date__range=[start_date, end_date],
            status__in=['present', 'late_login', 'early_logout', 'half_day']
        ).count()
        
        if present_count < threshold:
            notify_user(
                recipient_id=user.id,
                verb="Low Weekly Attendance",
                message=f"Your attendance for the last week was {present_count}/{working_days} days. Please ensure you maintain at least 80% attendance.",
                level="personal"
            )
            count += 1
            
    return f"Alerted {count} users regarding low attendance."

@shared_task(name="notifications.ai_tasks.notify_manager_team_absence")
def notify_manager_team_absence():
    """
    Notify managers when 3+ team members are on leave in same week.
    Runs every Sunday for the upcoming week.
    """
    today = timezone.localdate()
    # Start of next week (Monday)
    start_of_week = today + timedelta(days=(7 - today.weekday()))
    end_of_week = start_of_week + timedelta(days=6)
    
    # Find all managers
    managers = CustomUser.objects.filter(is_active=True, role__in=['manager', 'admin', 'hr'])
    
    count = 0
    for manager in managers:
        team_ids = manager.get_subordinates().values_list('id', flat=True)
        if not team_ids:
            continue
            
        # Count unique users on leave in this week
        leaves_this_week = LeaveRequest.objects.filter(
            user_id__in=team_ids,
            _status='approved',
            from_date__lte=end_of_week,
            to_date__gte=start_of_week
        ).values('user').distinct().count()
        
        if leaves_this_week >= 3:
            notify_user(
                recipient_id=manager.id,
                verb="Team Absence Alert",
                message=f"Alert: {leaves_this_week} members of your team are on leave for the upcoming week ({start_of_week} to {end_of_week}).",
                level="admin"
            )
            count += 1
            
    return f"Notified {count} managers about high team absence."
