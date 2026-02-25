from langchain_core.tools import tool
from leaves.models import LeaveBalance, LeaveType, LeaveRequest
from attendance.models import AttendanceRecord
from datetime import date, datetime
from django.db import transaction
from django.utils import timezone
import decimal

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
            # Import services dynamically to avoid circular imports if any
            from leaves.services import get_or_create_balance, validate_balance, reserve_balance
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            balance = get_or_create_balance(user, leave_type)
            validate_balance(balance, duration)
            reserve_balance(balance, duration)

            request = LeaveRequest.objects.create(
                user=user,
                leave_type=leave_type,
                from_date=from_date,
                to_date=to_date,
                duration_days=duration,
                reason=reason,
                _status="pending",
            )

            # --- NOTIFY ADMINS / MANAGERS ---
            from notifications.utils import notify_management
            message = f"New leave request from {user.first_name} {user.last_name} for {leave_type.name} ({duration} days) via AI Assistant."
            notify_management(
                user=user,
                verb="requested",
                message=message,
                target_type="Leave Request",
                target_id=str(request.id)
            )

            return {
                "status": "success",
                "message": f"Successfully submitted pending {leave_type.name} request for {duration} days.",
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
            
            # --- NOTIFY ADMINS / MANAGERS ---
            from notifications.utils import notify_management
            message = f"Leave request for {request.leave_type.name} on {request.from_date} has been CANCELLED by {request.user.first_name} {request.user.last_name} via AI Assistant."
            notify_management(
                user=request.user,
                verb="cancelled",
                message=message,
                target_type="Leave Request",
                target_id=str(request.id)
            )

            return {
                "status": "success",
                "message": f"Successfully cancelled your {request.leave_type.name} request for {request.from_date}."
            }
    except LeaveRequest.DoesNotExist:
        return f"Error: Leave request with ID {request_id} not found."
    except Exception as e:
        return f"Error cancelling leave: {str(e)}"

@tool
def get_attendance_today(user_id: int):
    """
    Checks the user's attendance record for today.
    Returns check-in/out times and current status.
    """
    today = date.today()
    record = AttendanceRecord.objects.filter(user_id=user_id, attendance_date=today).first()
    
    if not record:
        return "You have not checked in yet today."
    
    return {
        "date": str(record.attendance_date),
        "login_time": str(record.login_time) if record.login_time else "Not checked in",
        "logout_time": str(record.logout_time) if record.logout_time else "Not checked out",
        "status": record.status,
        "worked_hours": float(record.worked_hours) if record.worked_hours else 0
    }

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
    
    return {
        "total_employees": total_employees,
        "present_today": present_today,
        "on_leave_today": on_leave_today,
        "attendance_rate_today": f"{(present_today/total_employees*100):.1f}%" if total_employees > 0 else "0%"
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

