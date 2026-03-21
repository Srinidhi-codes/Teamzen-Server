from datetime import date, timedelta
from typing import List
from django.db.models import Count, Q
from django.utils import timezone
from users.models import CustomUser
from leaves.models import LeaveRequest, LeaveBalance, CompanyHoliday
from attendance.models import AttendanceRecord

def generate_user_insights(user) -> List:
    insights = []
    today = date.today()
    this_year = today.year

    # 1. Attendance Insight
    total_recs = AttendanceRecord.objects.filter(user=user).count()
    present_recs = AttendanceRecord.objects.filter(user=user, status__in=['present', 'late_login', 'early_logout', 'half_day']).count()
    rate = (present_recs / total_recs * 100) if total_recs > 0 else 0
    
    if rate < 85:
        insights.append({
            "title": "Attendance Alert",
            "message": f"Your attendance rate ({rate:.1f}%) is below the company benchmark. Improving this ensures better team coordination.",
            "type": "warning",
            "query": "How can I improve my attendance and what are the policies for late logins?"
        })
    else:
        insights.append({
            "title": "Consistency Bonus",
            "message": f"You've maintained a {rate:.1f}% attendance rate recently! Excellent consistency.",
            "type": "stats",
            "query": "How is my attendance compared to last month?"
        })

    # 2. Leave Balance Insight
    balances = LeaveBalance.objects.filter(user=user, year=this_year)
    for bal in balances:
        available = float(bal.get_available_balance())
        if available > 8 and today.month >= 11: # High balance late in the year
            insights.append({
                "title": "Use Your Leaves",
                "message": f"You still have {available} days of {bal.leave_type.name} left. Don't forget that these might expire!",
                "type": "info",
                "query": f"Can you suggest a good time to take my {bal.leave_type.name} based on team schedule?"
            })
            break # Just one for brevity

    # 3. Upcoming Long Weekend
    next_holiday = CompanyHoliday.objects.filter(
        organization=user.organization, 
        holiday_date__gte=today
    ).order_by('holiday_date').first()
    
    if next_holiday:
        days_diff = (next_holiday.holiday_date - today).days
        if days_diff <= 14: # Holiday soon
            # Check if it's near weekend
            dow = next_holiday.holiday_date.weekday()
            if dow in [0, 4]: # Mon or Fri
                insights.append({
                    "title": "Long Weekend Ahead!",
                    "message": f"{next_holiday.name} falls on a {next_holiday.holiday_date.strftime('%A')}. Perfect for a mini-vacation.",
                    "type": "info",
                    "query": "What's the best way to apply for leave around the upcoming holiday?"
                })

    return insights

def generate_admin_insights(user) -> List:
    insights = []
    today = date.today()
    org = user.organization

    # 1. Organization Attendance
    active_emps = CustomUser.objects.filter(organization=org, is_active=True).count()
    if active_emps > 0:
        present_today = AttendanceRecord.objects.filter(
            attendance_date=today,
            user__organization=org,
            status__in=['present', 'late_login', 'early_logout', 'half_day']
        ).count()
        rate = (present_today / active_emps * 100)
        
        if rate < 75:
            insights.append({
                "title": "High Absence Today",
                "message": f"Only {rate:.0f}% of your team is present today ({present_today}/{active_emps}). Check if there's a common event.",
                "type": "warning",
                "query": "Which departments have the lowest attendance today and why?"
            })

    # 2. Leave Overlap Alert
    next_week = today + timedelta(days=7)
    overlaps = LeaveRequest.objects.filter(
        user__organization=org,
        _status='approved',
        from_date__lte=next_week,
        to_date__gte=today
    ).values('user__department__name').annotate(count=Count('id')).filter(count__gt=3)
    
    for o in overlaps:
        insights.append({
            "title": f"Resource Alert: {o['user__department__name']}",
            "message": f"{o['count']} employees in this department are on leave next week. Ensure coverage is planned.",
            "type": "anomaly",
            "query": f"Provide a detailed report of overlapping leaves in {o['user__department__name']} and suggest alternates."
        })

    return insights
