from langchain_core.tools import tool
from leaves.models import LeaveBalance, LeaveType, LeaveRequest
from attendance.models import AttendanceRecord
from datetime import date, datetime, timedelta
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
import decimal
import calendar

@tool
def get_leave_balances(user_id: int):
    """
    Fetches the current leave balances for the given user for the current year.
    Returns a list of leave types with their entitled, used, and available days.
    """
    year = date.today().year
    balances = LeaveBalance.objects.filter(user_id=user_id, year=year).select_related('leave_type')
    
    result = []
    for bal in balances:
        result.append({
            "leave_type_id": bal.leave_type.id,
            "leave_type_name": bal.leave_type.name,
            "total_entitled": float(bal.total_entitled),
            "used": float(bal.used),
            "pending_approval": float(bal.pending_approval),
            "available": float(bal.get_available_balance())
        })
    return result

@tool
def get_leave_types(organization_id: int):
    """
    Lists all available leave types for the organization.
    Useful for showing the user what types of leave they can apply for.
    """
    types = LeaveType.objects.filter(organization_id=organization_id, is_active=True)
    return [{"id": t.id, "name": t.name, "description": t.description} for t in types]

@tool
def apply_for_leave(user_id: int, leave_type_id: int, from_date_str: str, to_date_str: str, reason: str):
    """
    Submits a new leave request for the user.
    from_date_str and to_date_str should be in 'YYYY-MM-DD' format.
    """
    from_date = date.fromisoformat(from_date_str)
    to_date = date.fromisoformat(to_date_str)
    duration = (to_date - from_date).days + 1
    
    if duration <= 0:
        return "Error: End date must be after or equal to start date."

    try:
        leave_type = LeaveType.objects.get(id=leave_type_id)
        
        with transaction.atomic():
            from leaves.services import create_leave_request
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            # Use the official service to ensure notifications and activity logs are triggered
            request = create_leave_request(
                user=user,
                leave_type=leave_type,
                from_date=from_date,
                to_date=to_date,
                reason=reason
            )

            return {
                "status": "success",
                "message": f"Successfully submitted pending {leave_type.name} request for {request.duration_days} days.",
                "request_id": request.id
            }
    except Exception as e:
        return f"[ERROR_CARD] title: Leave Application Error | message: {str(e)} [/ERROR_CARD]"

@tool
def list_pending_leaves(user_id: int):
    """
    Lists all pending leave requests for the user.
    Required before cancelling a leave to get the correct ID.
    """
    requests = LeaveRequest.objects.filter(user_id=user_id, _status='pending').order_by('-from_date')
    if not requests:
        return "You have no pending leave requests."
    
    return [
        {
            "id": r.id,
            "leave_type": r.leave_type.name,
            "from_date": str(r.from_date),
            "to_date": str(r.to_date),
            "duration": float(r.duration_days),
            "reason": r.reason
        } for r in requests
    ]

@tool
def cancel_leave(user_id: int, request_id: int):
    """
    Cancels a pending leave request. 
    Can only cancel requests that are in 'pending' status.
    """
    try:
        from leaves.services import cancel_leave_request
        request = LeaveRequest.objects.get(id=request_id, user_id=user_id)
        if request._status == 'cancelled':
            return "Error: This leave request has already been cancelled."
        
        if request._status not in ['pending', 'approved']:
            return f"Error: Only pending or approved requests can be cancelled. Current status: {request._status}"
        
        with transaction.atomic():
            cancel_leave_request(request)
            
            return {
                "status": "success",
                "message": f"Successfully cancelled your {request.leave_type.name} request for {request.from_date}."
            }
    except LeaveRequest.DoesNotExist:
        return f"Error: Leave request with ID {request_id} not found."
    except Exception as e:
        return f"Error cancelling leave: {str(e)}"


@tool
def mark_attendance(user_id: int, action: str, latitude: float = None, longitude: float = None):
    """
    Marks attendance (check-in or check-out) for the user.
    action: 'check-in' or 'check-out'
    If latitude/longitude are not provided, it uses the office's default coordinates.
    """
    from django.contrib.auth import get_user_model
    from attendance.services import check_in_user, check_out_user
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        if not user.office_location:
            return "Error: You don't have an assigned office location. Please contact HR."

        # Check if coordinates are provided
        if latitude is None or longitude is None:
            return "[ERROR_CARD] title: Location Permission Required | message: I need your exact geolocation to verify that you are within the office premises for check-in/out. Please allow location access in your browser and try again. [/ERROR_CARD]"

        lat = latitude
        lon = longitude
        now_time = timezone.localtime().time().strftime("%H:%M:%S")

        if action.lower() == 'check-in':
            attendance, distance = check_in_user(user, user.office_location.id, lat, lon, now_time)
            return (
                f"[ATTENDANCE_CARD] Action: Check-In | Status: {attendance.status} | "
                f"Time: {now_time} | Office: {user.office_location.name} | "
                f"Distance: {int(distance)}m [/ATTENDANCE_CARD]"
            )
        elif action.lower() == 'check-out':
            attendance, distance = check_out_user(user, lat, lon, now_time)
            return (
                f"[ATTENDANCE_CARD] Action: Check-Out | Status: {attendance.status} | "
                f"Time: {now_time} | Office: {user.office_location.name} | "
                f"Hours: {attendance.worked_hours} [/ATTENDANCE_CARD]"
            )
        else:
            return "[ERROR_CARD] title: Invalid Action | message: Please use 'check-in' or 'check-out'. [/ERROR_CARD]"
    except Exception as e:
        return f"[ERROR_CARD] title: Attendance Error | message: {str(e)} [/ERROR_CARD]"

@tool
def get_attendance_today(user_id: int):
    """
    Checks the user's attendance record for today.
    Returns check-in/out times, current status, and flags missing logouts from yesterday.
    """
    today = date.today()
    record = AttendanceRecord.objects.filter(user_id=user_id, attendance_date=today).first()
    
    # Check for missing logout yesterday
    yesterday = today - timezone.timedelta(days=1)
    yesterday_record = AttendanceRecord.objects.filter(user_id=user_id, attendance_date=yesterday).first()
    missing_yesterday_logout = False
    if yesterday_record and yesterday_record.login_time and not yesterday_record.logout_time:
        missing_yesterday_logout = True

    status_info = {
        "missing_yesterday_logout": missing_yesterday_logout,
        "yesterday_date": str(yesterday) if missing_yesterday_logout else None
    }

    if not record:
        return {
            "message": "You have not checked in yet today.",
            "anomalies": status_info if missing_yesterday_logout else None
        }
    
    return {
        "date": str(record.attendance_date),
        "login_time": str(record.login_time) if record.login_time else "Not checked in",
        "logout_time": str(record.logout_time) if record.logout_time else "Not checked out",
        "status": record.status,
        "worked_hours": float(record.worked_hours) if record.worked_hours else 0,
        "anomalies": status_info if missing_yesterday_logout else None
    }

@tool
def check_team_availability(user_id: int, start_date_str: str, end_date_str: str):
    """
    Checks how many people in the user's department are on leave during a given date range.
    Helps the AI give advice on applying for leave.
    start_date_str and end_date_str should be 'YYYY-MM-DD'.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        if not user.department:
            return "No department assigned. Cannot check team availability."
        
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        
        # Find leaves in the same department (Approved & Pending)
        conflicting_leaves = LeaveRequest.objects.filter(
            user__department=user.department,
            _status__in=['approved', 'pending'],
            from_date__lte=end_date,
            to_date__gte=start_date
        ).select_related('user')
        
        team_size = User.objects.filter(department=user.department, is_active=True).count()
        
        # Group by date for more granular insight if needed, but summary is fine for now
        summary = []
        for leave in conflicting_leaves:
            if leave.user_id != user_id:
                summary.append({
                    "name": f"{leave.user.first_name} {leave.user.last_name}",
                    "from": str(leave.from_date),
                    "to": str(leave.to_date),
                    "status": leave._status
                })
        
        return {
            "department": user.department.name,
            "team_size": team_size,
            "on_leave_count": len(summary),
            "colleagues_on_leave": summary
        }
    except Exception as e:
        return f"Error checking team availability: {str(e)}"

@tool
def get_team_stats(organization_id: int):
    """
    Fetches high-level attendance and leave stats for the whole organization.
    Useful for managers and admins to get a quick summary.
    """
    from attendance.models import AttendanceRecord
    from leaves.models import LeaveRequest
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    today = date.today()
    total_employees = User.objects.filter(organization_id=organization_id, is_active=True).count()
    present_today = AttendanceRecord.objects.filter(
        user__organization_id=organization_id, 
        attendance_date=today,
        status='present'
    ).count()
    
    on_leave_today = LeaveRequest.objects.filter(
        user__organization_id=organization_id,
        _status='approved',
        from_date__lte=today,
        to_date__gte=today
    ).count()

    # Extension: Find low attendance employees (last 30 days)
    start_date = today - timedelta(days=30)
    employees = User.objects.filter(organization_id=organization_id, is_active=True, role='employee')
    low_attendance_list = []
    
    for emp in employees:
        records = AttendanceRecord.objects.filter(
            user=emp, 
            attendance_date__range=[start_date, today]
        )
        total_work_days = 22 # Approx working days in a month
        present_count = records.filter(status__in=['present', 'late_login', 'early_logout', 'half_day']).count()
        rate = (present_count / total_work_days) * 100
        
        if rate < 85: # Threshold
            low_attendance_list.append({
                "name": f"{emp.first_name} {emp.last_name}",
                "rate": f"{rate:.1f}%",
                "days": present_count
            })
    
    return {
        "total_employees": total_employees,
        "present_today": present_today,
        "on_leave_today": on_leave_today,
        "attendance_rate_today": f"{(present_today/total_employees*100):.1f}%" if total_employees > 0 else "0%",
        "low_attendance_alerts": low_attendance_list[:5] # Return top 5 for brevity
    }

@tool
def search_policies(query: str, organization_id: int):
    """
    Searches the company policy documents (RAG) for the given query.
    Use this when the user asks about rules, policies, or handbook information.
    """
    from langchain_openai import OpenAIEmbeddings
    from django.conf import settings
    from .models import PolicyDocument
    from pgvector.django import L2Distance
    
    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    query_embedding = embeddings.embed_query(query)
    
    search_qs = PolicyDocument.objects.filter(policy_file__organization_id=organization_id)
    similar_docs = search_qs.annotate(
        distance=L2Distance('embedding', query_embedding)
    ).filter(distance__lt=0.6).order_by('distance')[:4]
    
    if not similar_docs:
        return "No policy documents found for your organization."
        
    results = []
    for doc in similar_docs:
        results.append(f"Source: {doc.title}\nContent: {doc.content}")
    return "\n\n---\n\n".join(results)
        
@tool
def suggest_leave_window(user_id: int, month: int = None):
    """
    Analyzes and suggests the best time for the user to take a leave in a specific month (defaults to current month).
    Factors in: remaining leave balance, team availability, company holidays, and user history.
    month: 1-12. If not provided, defaults to the current month.
    Returns a suggestion with reasoning formatted as an INSIGHT_CARD.
    """
    from django.contrib.auth import get_user_model
    from leaves.models import CompanyHoliday, LeaveBalance, LeaveRequest
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        today = date.today()
        target_month = month if month else today.month
        target_year = today.year
        
        # 1. Check Leave Balance
        balances = LeaveBalance.objects.filter(user=user, year=target_year)
        available_days = sum(float(bal.get_available_balance()) for bal in balances)
        
        if available_days <= 0:
            return "[INSIGHT_CARD] title: Leave Recommendation | message: You don't have any leave balance remaining for this year. You might want to wait for the next accrual cycle. | type: warning [/INSIGHT_CARD]"

        # 2. Get Company Holidays for the month
        holidays = CompanyHoliday.objects.filter(
            organization=user.organization,
            holiday_date__year=target_year,
            holiday_date__month=target_month
        ).order_by('holiday_date')
        
        holiday_dates = [h.holiday_date for h in holidays]
        
        # 3. Analyze Team Availability for each day in the month
        _, last_day = calendar.monthrange(target_year, target_month)
        start_date = date(target_year, target_month, 1)
        end_date = date(target_year, target_month, last_day)
        
        daily_absence = {}
        if user.department:
            team_leaves = LeaveRequest.objects.filter(
                user__department=user.department,
                _status__in=['approved', 'pending'],
                from_date__lte=end_date,
                to_date__gte=start_date
            ).values('from_date', 'to_date')
            
            for d in range(1, last_day + 1):
                curr_date = date(target_year, target_month, d)
                count = 0
                for leave in team_leaves:
                    if leave['from_date'] <= curr_date <= leave['to_date']:
                        count += 1
                daily_absence[curr_date] = count

        # 4. Find the "Best Window"
        best_window = None
        window_score = -100
        
        for d in range(1, last_day + 1):
            curr_date = date(target_year, target_month, d)
            # Skip if it's a weekend (Sat=5, Sun=6)
            if curr_date.weekday() >= 5:
                continue
            # Skip if it's already a holiday
            if curr_date in holiday_dates:
                continue
            # Skip past days
            if curr_date <= today:
                continue
                
            # Score this day
            score = 0
            # Higher score if next to a holiday
            prev_day = curr_date - timedelta(days=1)
            next_day = curr_date + timedelta(days=1)
            if prev_day in holiday_dates or next_day in holiday_dates:
                score += 15
            
            # Higher score if next to a weekend
            if curr_date.weekday() == 0 or curr_date.weekday() == 4: # Mon or Fri
                score += 10
            
            # Lower score if team absence is high
            absence_count = daily_absence.get(curr_date, 0)
            score -= (absence_count * 5)
            
            if score > window_score:
                window_score = score
                best_window = curr_date

        if not best_window:
            return "[INSIGHT_CARD] title: Leave Recommendation | message: No ideal leave windows found for this month. All weekdays seem equally busy or you have already taken significant time off. | type: info [/INSIGHT_CARD]"
        
        holiday_context = ""
        if holiday_dates:
            nearby_holiday_name = None
            for h in holidays:
                if abs((h.holiday_date - best_window).days) <= 2:
                    nearby_holiday_name = h.name
                    break
            if nearby_holiday_name:
                holiday_context = f" since it's close to the '{nearby_holiday_name}' holiday"

        message = (
            f"I recommend taking a leave on **{best_window.strftime('%A, %b %d')}**{holiday_context}. "
            f"Team absence in your department is low on this day ({daily_absence.get(best_window, 0)} people out), "
            f"and you still have {available_days} days of leave remaining for the year."
        )
        
        return (
            f"[INSIGHT_CARD] title: Leave Recommendation | "
            f"message: {message} | "
            f"type: stats | "
            f"stats: Recommended Date:{best_window.strftime('%Y-%m-%d')}, Remaining Balance:{available_days} days [/INSIGHT_CARD]"
        )

    except Exception as e:
        return f"Error calculating leave recommendation: {str(e)}"

@tool
def get_attendance_trends(user_id: int, days: int = 30):
    """
    Analyzes historical attendance data for the user to detect anomalies and trends.
    Detects: Repeated late arrivals (e.g., 3+ same-day-of-week lateness),
    Repeated no-checkout pattern, and overall attendance rate drops.
    Returns findings as an INSIGHT_CARD.
    """
    from attendance.models import AttendanceRecord
    from collections import Counter
    
    try:
        today = date.today()
        start_date = today - timedelta(days=days)
        records = AttendanceRecord.objects.filter(
            user_id=user_id, 
            attendance_date__range=[start_date, today]
        ).order_by('attendance_date')

        if not records.exists():
            return "No attendance records found for the specified period."

        total_days = days
        present_count = records.filter(status__in=['present', 'late_login', 'early_logout', 'half_day']).count()
        rate = (present_count / total_days) * 100
        
        # 1. Detect Repeated Laters
        late_days = records.filter(status='late_login')
        late_dow_counts = Counter([r.attendance_date.strftime("%A") for r in late_days])
        repeated_late_day = None
        for day, count in late_dow_counts.items():
            if count >= 3:
                repeated_late_day = day
                break

        # 2. Detect No-Checkout pattern
        no_checkout_count = records.filter(login_time__isnull=False, logout_time__isnull=True).count()

        # 3. Generate Insight
        findings = []
        severity = "info"
        
        if rate < 85:
            findings.append(f"Your attendance rate ({rate:.1f}%) is below the company target of 85%.")
            severity = "warning"
        
        if repeated_late_day:
            findings.append(f"You've been late on {late_dow_counts[repeated_late_day]} {repeated_late_day}s recently. Is everything okay?")
            severity = "warning"
            
        if no_checkout_count >= 2:
            findings.append(f"I noticed you missed checking out {no_checkout_count} times this month. Don't forget to clock out!")
            severity = "warning"

        if not findings:
            return (
                f"[INSIGHT_CARD] title: Attendance Trends | "
                f"message: Great job! Your attendance is very consistent. You have a {rate:.1f}% presence rate over the last {days} days. | "
                f"type: stats | stats: Period:{days} Days, Presence Rate:{rate:.1f}% [/INSIGHT_CARD]"
            )

        message = " ".join(findings)
        return (
            f"[INSIGHT_CARD] title: Attendance Insights | "
            f"message: {message} | "
            f"type: {severity} | "
            f"stats: Presence Rate:{rate:.1f}%, Incomplete Logs:{no_checkout_count} [/INSIGHT_CARD]"
        )

    except Exception as e:
        return f"Error analyzing attendance trends: {str(e)}"

@tool
def generate_monthly_summary(organization_id: int, month: int, year: int):
    """
    Generates a high-level executive summary of an organization's performance for a specific month.
    Aggregates attendance rates, leave trends, and departmental activity.
    Returns a human-readable professional summary paragraph.
    Only available for Managers and Admins.
    """
    from attendance.models import AttendanceRecord
    from leaves.models import LeaveRequest
    from organizations.models import Department
    from django.contrib.auth import get_user_model
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    from django.conf import settings
    
    User = get_user_model()
    try:
        # 1. Gather Data
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        
        # Attendance Data
        records = AttendanceRecord.objects.filter(
            user__organization_id=organization_id,
            attendance_date__range=[start_date, end_date]
        )
        total_present = records.filter(status__in=['present', 'late_login', 'early_logout', 'half_day']).count()
        total_late = records.filter(status='late_login').count()
        
        # Leave Data
        leaves = LeaveRequest.objects.filter(
            user__organization_id=organization_id,
            _status='approved',
            from_date__lte=end_date,
            to_date__gte=start_date
        )
        total_leaves = leaves.count()
        top_leave_type = leaves.values('leave_type__name').annotate(count=Count('id')).order_by('-count').first()
        
        # Department Activity
        depts = Department.objects.filter(organization_id=organization_id)
        dept_data = []
        for d in depts:
            emp_count = User.objects.filter(department=d, is_active=True).count()
            dept_leaves = leaves.filter(user__department=d).count()
            dept_data.append(f"{d.name}: {emp_count} employees, {dept_leaves} leaves approved")

        # 2. Synthesize with LLM
        summary_model = ChatOpenAI(model="gpt-4o", temperature=0.7, openai_api_key=settings.OPENAI_API_KEY)
        
        data_payload = (
            f"Month: {calendar.month_name[month]} {year}\n"
            f"Total Attendance Logs: {records.count()}\n"
            f"Total Present: {total_present}\n"
            f"Total Late Logins: {total_late}\n"
            f"Total Approved Leaves: {total_leaves}\n"
            f"Most Frequent Leave Type: {top_leave_type['leave_type__name'] if top_leave_type else 'N/A'}\n"
            f"Departmental Context: {', '.join(dept_data)}\n"
        )
        
        system_msg = "You are a senior HR Analyst. Compose a professional, concise executive summary (1 paragraph) based on the provided monthly data. Focus on trends, productivity, and any potential burnout signals (high leave usage). Do not use bullet points."
        human_msg = f"Data for the report:\n{data_payload}"
        
        response = summary_model.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=human_msg)
        ])
        
        return {
            "month": calendar.month_name[month],
            "year": year,
            "summary": response.content,
            "raw_stats": {
                "attendance_rate": f"{(total_present/records.count()*100):.1f}%" if records.count() > 0 else "0%",
                "late_percentage": f"{(total_late/total_present*100):.1f}%" if total_present > 0 else "0%",
                "leave_count": total_leaves
            }
        }

    except Exception as e:
        return f"Error generating monthly summary: {str(e)}"

