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
def apply_for_leave(
    user_id: int,
    leave_type_id: int,
    from_date_str: str,
    to_date_str: str,
    reason: str,
    half_day_period: str = "full_day",
):
    """
    Submits a new leave request for the user.
    from_date_str and to_date_str should be in 'YYYY-MM-DD' format.
    half_day_period must be one of: full_day, first_half, second_half.
    """
    if not reason or len(reason.strip()) < 5:
        return "[ERROR_CARD] title: Leave reason required | message: Please provide a clear reason for the leave request before I submit it. [/ERROR_CARD]"

    valid_half_day_periods = {"full_day", "first_half", "second_half"}
    if half_day_period not in valid_half_day_periods:
        return "[ERROR_CARD] title: Invalid leave duration | message: half_day_period must be full_day, first_half, or second_half. [/ERROR_CARD]"

    from_date = date.fromisoformat(from_date_str)
    to_date = date.fromisoformat(to_date_str)
    duration = (to_date - from_date).days + 1
    
    if duration <= 0:
        return "Error: End date must be after or equal to start date."

    if from_date == to_date and half_day_period == "full_day":
        inferred_duration = "1 full day"
    elif from_date == to_date:
        inferred_duration = "0.5 day"
    else:
        inferred_duration = f"{duration} days"

    try:
        leave_type = LeaveType.objects.get(id=leave_type_id)
        
        conflict_note = ""
        try:
            from integrations.google_calendar import list_busy_events

            busy = list_busy_events(user_id, from_date, to_date)
            if busy:
                titles = ", ".join(
                    (e.get("summary") or "busy")[:40] for e in busy[:3]
                )
                conflict_note = (
                    f" Note: your Google Calendar shows {len(busy)} event(s) "
                    f"overlapping these dates ({titles}). Leave was still submitted."
                )
        except Exception:
            pass

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
                reason=reason,
                half_day_period=half_day_period,
            )

            return {
                "status": "success",
                "message": (
                    f"Successfully submitted pending {leave_type.name} request "
                    f"for {inferred_duration}.{conflict_note}"
                ),
                "request_id": request.id,
                "calendar_conflicts": bool(conflict_note),
            }
    except Exception as e:
        return f"[ERROR_CARD] title: Leave Application Error | message: {str(e)} [/ERROR_CARD]"


@tool
def check_calendar_conflicts(user_id: int, start_date_str: str, end_date_str: str):
    """
    Checks the user's connected Google Calendar for events overlapping a date range.
    start_date_str and end_date_str must be 'YYYY-MM-DD'.
    Soft advisory only — does not block leave. Returns conflicts or a not-connected message.
    """
    try:
        start = date.fromisoformat(start_date_str)
        end = date.fromisoformat(end_date_str)
        if end < start:
            return "Error: end date must be on or after start date."

        from integrations.google_calendar import get_connection, list_busy_events

        if not get_connection(user_id):
            return (
                "Google Calendar is not connected. "
                "Connect it from Profile → Integrations to check conflicts."
            )

        events = list_busy_events(user_id, start, end)
        if not events:
            return (
                f"No Google Calendar events found between {start} and {end}. "
                "Looks clear from a calendar perspective."
            )

        lines = [
            f"Found {len(events)} Google Calendar event(s) overlapping "
            f"{start} → {end}:"
        ]
        for e in events[:10]:
            lines.append(
                f"- {e.get('summary', '(busy)')}: {e.get('start', '?')} → {e.get('end', '?')}"
            )
        if len(events) > 10:
            lines.append(f"...and {len(events) - 10} more.")
        lines.append("This is advisory only — you can still apply for leave.")
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking calendar conflicts: {str(e)}"

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
    latitude and longitude are REQUIRED for geofence verification.
    """
    from django.contrib.auth import get_user_model
    from attendance.services import check_in_user, check_out_user
    
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        if not user.office_location:
            return "Error: You don't have an assigned office location. Please contact HR."

        from attendance.services import org_requires_face
        if org_requires_face(user):
            return (
                "[ERROR_CARD] title: Face Attendance Required | message: "
                "Your organization requires face verification for attendance. "
                "Please check in or out from the Teamzen web app or mobile app. [/ERROR_CARD]"
            )

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
def get_latest_payslip(user_id: int):
    """
    Returns the user's most recent published/paid payslip with gross, net, deductions,
    worked days, LOP, and component breakdown. Use this whenever the user asks about
    their salary, payslip, net pay, or last month's payroll without naming a month.
    """
    payslip = _fetch_payslip(user_id)
    if not payslip:
        return "No payslip found for this employee yet."
    return _format_payslip_card(payslip)


@tool
def get_payslip(user_id: int, month: int, year: int):
    """
    Fetch the user's payslip for a specific month and year.
    month: 1–12 (e.g. 1 = January). year: e.g. 2026.
    Use when the user names a month: "Show me my January 2026 salary slip".
    """
    if month < 1 or month > 12:
        return "[ERROR_CARD] title: Invalid Month | message: Month must be between 1 and 12. [/ERROR_CARD]"
    payslip = _fetch_payslip(user_id, month=month, year=year)
    if not payslip:
        return (
            f"No payslip found for {month}/{year}. "
            "It may not be published yet — try get_payroll_history or get_latest_payslip."
        )
    return _format_payslip_card(payslip)


@tool
def explain_deduction(user_id: int, month: int = None, year: int = None, component_name: str = None):
    """
    Explain deduction lines on a payslip (PF, PT, LOP, TDS, etc.).
    If month/year omitted, uses the latest payslip.
    Optional component_name filters to one deduction (e.g. 'PF', 'LOP', 'Professional Tax').
    Use for: "Why was my PF higher this month?" or "Explain my deductions".
    """
    payslip = _fetch_payslip(user_id, month=month, year=year)
    if not payslip:
        return "No payslip found to explain deductions."

    run = payslip.payroll_run
    deductions = [
        c for c in payslip.components.all()
        if not str(c.component_type).lower().startswith("earn")
    ]
    if component_name:
        needle = component_name.strip().lower()
        deductions = [
            c for c in deductions
            if needle in c.component_name.lower() or needle in (c.component_code or "").lower()
        ]
        if not deductions:
            return (
                f"No deduction matching '{component_name}' on payslip {run.month}/{run.year}. "
                "Try without a component name to see all deductions."
            )

    if not deductions:
        return f"No deductions on payslip {run.month}/{run.year}."

    stats_parts = []
    detail_notes = []
    for c in deductions:
        stats_parts.append(f"{c.component_name}:{c.amount}")
        code = (c.component_code or "").upper()
        name_l = c.component_name.lower()
        if code == "LOP" or "loss of pay" in name_l or name_l == "lop":
            detail_notes.append(
                f"{c.component_name} (Rs {c.amount}): Loss of Pay for {payslip.lop_days} day(s) — "
                "salary reduced for unpaid absence / unpaid leave."
            )
        elif "pf" in name_l or code in ("PF", "EPF"):
            detail_notes.append(
                f"{c.component_name} (Rs {c.amount}): Provident Fund statutory contribution "
                "(typically a % of basic / PF wages)."
            )
        elif "pt" in name_l or "professional tax" in name_l or code == "PT":
            detail_notes.append(
                f"{c.component_name} (Rs {c.amount}): Professional Tax — state statutory deduction."
            )
        elif "tds" in name_l or "tax" in name_l:
            detail_notes.append(
                f"{c.component_name} (Rs {c.amount}): Tax withholding based on taxable earnings."
            )
        else:
            detail_notes.append(
                f"{c.component_name} (Rs {c.amount}): Recorded as a {c.component_type} on this payslip."
            )

    stats = ", ".join(stats_parts)
    message_extra = " ".join(detail_notes)
    return (
        f"[INSIGHT_CARD] title: Deduction Breakdown ({run.month}/{run.year}) | "
        f"message: {message_extra} | type: info | topic: Payroll | "
        f"stats: Gross:{payslip.gross_earnings}, Net:{payslip.net_pay}, "
        f"Total Deductions:{payslip.total_deductions}, LOP Days:{payslip.lop_days}, {stats} "
        f"[/INSIGHT_CARD]"
    )


@tool
def salary_forecast(user_id: int, unpaid_days: float, month: int = None, year: int = None):
    """
    Estimate how much net/CTC the employee would lose if they take unpaid_days of LOP.
    Use for: "If I take 3 unpaid days, how much do I lose?"
    Optional month/year sets the calendar-days basis (defaults to current month).
    Does NOT modify payroll — read-only estimate from active CTC.
    """
    from django.contrib.auth import get_user_model
    from payroll.services import PayrollService

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return "[ERROR_CARD] title: User Not Found | message: Invalid user id. [/ERROR_CARD]"

    result = PayrollService.estimate_lop_cost(user, unpaid_days, year=year, month=month)
    if result.get("error"):
        return f"[ERROR_CARD] title: Salary Forecast | message: {result['error']} [/ERROR_CARD]"

    return (
        f"[INSIGHT_CARD] title: Salary Forecast | "
        f"message: Taking {result['unpaid_days']} unpaid day(s) in {result['month']}/{result['year']} "
        f"is estimated to reduce pay by Rs {result['estimated_loss']} "
        f"(Rs {result['per_day_rate']} per day × {result['unpaid_days']} days). "
        f"Reference monthly CTC Rs {result['monthly_ctc']} → approx Rs {result['estimated_monthly_after_lop']} "
        f"before other statutory deductions. {result['note']} | "
        f"type: warning | topic: Payroll | "
        f"stats: Unpaid Days:{result['unpaid_days']}, Per Day:₹{result['per_day_rate']}, "
        f"Estimated Loss:₹{result['estimated_loss']}, Monthly CTC:₹{result['monthly_ctc']}, "
        f"After LOP (CTC basis):₹{result['estimated_monthly_after_lop']} "
        f"[/INSIGHT_CARD]"
    )


@tool
def compare_payslips(
    user_id: int,
    month1: int,
    year1: int,
    month2: int,
    year2: int,
):
    """
    Compare two payslips for the same employee across months.
    Use for: "Compare my last 2 salary slips" (resolve months first via get_payroll_history)
    or explicit "Compare March 2026 vs April 2026".
    """
    a = _fetch_payslip(user_id, month=month1, year=year1)
    b = _fetch_payslip(user_id, month=month2, year=year2)
    if not a and not b:
        return f"No payslips found for {month1}/{year1} or {month2}/{year2}."
    if not a:
        return f"No payslip for {month1}/{year1}. Found the other month only."
    if not b:
        return f"No payslip for {month2}/{year2}. Found the other month only."

    def _ded_map(p):
        return {
            c.component_name: float(c.amount)
            for c in p.components.all()
            if not str(c.component_type).lower().startswith("earn")
        }

    da, db = _ded_map(a), _ded_map(b)
    all_names = sorted(set(da) | set(db))
    changes = []
    for name in all_names:
        va, vb = da.get(name, 0.0), db.get(name, 0.0)
        if abs(va - vb) > 0.009:
            changes.append(f"{name}: {va} → {vb} (Δ {round(vb - va, 2)})")

    net_delta = float(b.net_pay) - float(a.net_pay)
    gross_delta = float(b.gross_earnings) - float(a.gross_earnings)
    change_text = "; ".join(changes) if changes else "No material deduction line changes."

    return (
        f"[INSIGHT_CARD] title: Payslip Comparison | "
        f"message: {month1}/{year1} vs {month2}/{year2}. "
        f"Net {a.net_pay} → {b.net_pay} (Δ {round(net_delta, 2)}). "
        f"Gross {a.gross_earnings} → {b.gross_earnings} (Δ {round(gross_delta, 2)}). "
        f"LOP {a.lop_days} → {b.lop_days}. Changes: {change_text} | "
        f"type: stats | topic: Payroll | "
        f"stats: Net Δ:{round(net_delta, 2)}, Gross Δ:{round(gross_delta, 2)}, "
        f"LOP {month1}/{year1}:{a.lop_days}, LOP {month2}/{year2}:{b.lop_days} "
        f"[/INSIGHT_CARD]\n"
        f"{_format_payslip_card(a)}\n{_format_payslip_card(b)}"
    )


@tool
def get_payroll_history(user_id: int, limit: int = 6):
    """
    List recent payslips for the employee (month, year, net, status).
    Use to discover which months exist before get_payslip or compare_payslips.
    """
    from payroll.models import Payslip

    limit = max(1, min(int(limit or 6), 24))
    slips = (
        Payslip.objects.filter(user_id=user_id)
        .select_related("payroll_run")
        .order_by("-payroll_run__year", "-payroll_run__month", "-created_at")[:limit]
    )
    if not slips:
        return "No payroll history found for this employee."

    rows = []
    for p in slips:
        r = p.payroll_run
        rows.append(
            f"{r.month}/{r.year}: net Rs {p.net_pay}, gross Rs {p.gross_earnings}, "
            f"LOP {p.lop_days}, status {p.status}"
        )
    return (
        f"[INSIGHT_CARD] title: Payroll History | "
        f"message: Last {len(rows)} payslip(s): " + " | ".join(rows) + " | "
        f"type: info | topic: Payroll | stats: Count:{len(rows)} [/INSIGHT_CARD]"
    )


def _fetch_payslip(user_id: int, month: int = None, year: int = None):
    from payroll.models import Payslip

    qs = Payslip.objects.filter(user_id=user_id).select_related("payroll_run").prefetch_related(
        "components"
    )
    if month is not None and year is not None:
        qs = qs.filter(payroll_run__month=month, payroll_run__year=year)
        published = qs.filter(status__in=["published", "paid"]).first()
        return published or qs.first()

    published = (
        qs.filter(status__in=["published", "paid"])
        .order_by("-payroll_run__year", "-payroll_run__month", "-created_at")
        .first()
    )
    if published:
        return published
    return qs.order_by("-payroll_run__year", "-payroll_run__month", "-created_at").first()


def _format_payslip_card(payslip) -> str:
    run = payslip.payroll_run
    earnings = []
    deductions = []
    for c in payslip.components.all():
        item = f"{c.component_name}:{c.amount}"
        if str(c.component_type).lower().startswith("earn"):
            earnings.append(item)
        else:
            deductions.append(item)

    earnings_str = "{" + ", ".join(earnings) + "}" if earnings else "{}"
    deductions_str = "{" + ", ".join(deductions) + "}" if deductions else "{}"

    return (
        f"[PAYROLL_CARD] month: {run.month} | year: {run.year} | "
        f"gross: {payslip.gross_earnings} | net: {payslip.net_pay} | "
        f"deductions: {payslip.total_deductions} | worked_days: {payslip.worked_days} | "
        f"lop: {payslip.lop_days} | status: {payslip.status} | "
        f"earnings_breakdown: {earnings_str} | deductions_breakdown: {deductions_str} "
        f"[/PAYROLL_CARD]"
    )


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

def _serialize_user_details(user) -> dict:
    """Safe profile payload — no bank/tax/2FA secrets."""
    manager = getattr(user, "manager", None)
    org = getattr(user, "organization", None)
    dept = getattr(user, "department", None)
    desig = getattr(user, "designation", None)
    office = getattr(user, "office_location", None)
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email,
        "employee_id": user.employee_id,
        "role": user.role,
        "employment_type": user.employment_type,
        "phone_number": user.phone_number,
        "date_of_joining": user.date_of_joining.isoformat() if user.date_of_joining else None,
        "date_of_exit": user.date_of_exit.isoformat() if user.date_of_exit else None,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "organization_id": user.organization_id,
        "organization_name": getattr(org, "name", None) if org else None,
        "department_id": user.department_id,
        "department_name": getattr(dept, "name", None) if dept else None,
        "designation_id": user.designation_id,
        "designation_name": getattr(desig, "name", None) if desig else None,
        "office_location_id": user.office_location_id,
        "office_location_name": getattr(office, "name", None) if office else None,
        "manager_id": user.manager_id,
        "manager_name": (
            f"{manager.first_name or ''} {manager.last_name or ''}".strip() or manager.email
            if manager
            else None
        ),
        "manager_email": manager.email if manager else None,
    }


@tool
def get_user_details(
    user_id: int,
    lookup_email: str = None,
    lookup_employee_id: str = None,
    lookup_user_id: int = None,
):
    """
    Returns HR profile details for a user (name, email, role, department, designation, manager, org).
    Without lookup_* args, returns the authenticated user's own profile (whoami).
    Managers/HR/admins can look up another person in the same organization via
    lookup_email, lookup_employee_id, or lookup_user_id.
    Does not return bank, PAN, Aadhaar, or other sensitive tax/identity fields.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    actor = (
        User.objects.filter(id=user_id, is_active=True)
        .select_related(
            "organization", "department", "designation", "office_location", "manager"
        )
        .first()
    )
    if not actor:
        return "Error: Authenticated user not found or inactive."

    target = actor
    looking_up = any([lookup_email, lookup_employee_id, lookup_user_id])
    if looking_up:
        privileged = actor.role in ("superadmin", "admin", "hr", "manager")
        qs = User.objects.filter(is_active=True).select_related(
            "organization", "department", "designation", "office_location", "manager"
        )
        if actor.organization_id:
            qs = qs.filter(organization_id=actor.organization_id)
        elif actor.role != "superadmin":
            return "Error: Your account has no organization."

        if lookup_user_id is not None:
            target = qs.filter(id=lookup_user_id).first()
        elif lookup_employee_id:
            target = qs.filter(employee_id__iexact=lookup_employee_id.strip()).first()
        elif lookup_email:
            target = qs.filter(email__iexact=lookup_email.strip()).first()

        if not target:
            return "Error: User not found in your organization."

        if target.id != actor.id and not privileged:
            return "Error: Only managers, HR, or admins can look up other users."

    return _serialize_user_details(target)


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
    Searches the company policy documents (RAG) for the given query using hybrid
    vector + full-text retrieval. Use this when the user asks about rules,
    policies, or handbook information. Results include page numbers for citations.
    """
    from .retrieval import format_hits_for_llm, hybrid_search

    hits = hybrid_search(query, organization_id)
    return format_hits_for_llm(hits)
        
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

        # Optional: Google Calendar busy days (soft boost for free days)
        busy_dates = set()
        try:
            from integrations.google_calendar import list_busy_events

            for ev in list_busy_events(user_id, start_date, end_date):
                raw = (ev.get("start") or "")[:10]
                try:
                    busy_dates.add(date.fromisoformat(raw))
                except Exception:
                    pass
        except Exception:
            pass

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

            # Prefer days free of personal Google Calendar busy blocks
            if curr_date in busy_dates:
                score -= 8
            
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
            f"I recommend taking a leave on {best_window.strftime('%A, %b %d')}{holiday_context}. "
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


@tool
def get_team_pulse(organization_id: int, user_id: int = None):
    """
    Returns a Team Pulse brief for managers: prior-week attendance rate,
    pending leaves, and top late offenders. Use when a manager asks for
    team pulse, weekly team summary, or attendance digest.
    """
    from django.contrib.auth import get_user_model
    from notifications.proactive import build_team_pulse

    User = get_user_model()
    manager = None
    if user_id:
        try:
            manager = User.objects.get(id=user_id)
        except User.DoesNotExist:
            manager = None

    pulse = build_team_pulse(organization_id, manager=manager)
    stats = (
        f"{{Attendance: {pulse['attendance_rate']}%, "
        f"Headcount: {pulse['headcount']}, "
        f"Pending Leaves: {pulse['pending_leaves']}}}"
    )
    return (
        f"[INSIGHT_CARD] title: Team Pulse | message: {pulse['message']} | "
        f"type: stats | topic: Team Pulse | stats: {stats} [/INSIGHT_CARD]"
    )


@tool
def list_pending_corrections(user_id: int):
    """
    Lists pending attendance corrections for the user (missed checkout drafts).
    Always call this before confirming a correction. Returns CORRECTION_CARD tags.
    """
    from attendance.models import AttendanceCorrection

    corrections = (
        AttendanceCorrection.objects.filter(
            requested_by_id=user_id,
            _status="pending",
        )
        .select_related("attendance_record")
        .order_by("-created_at")[:10]
    )
    if not corrections:
        return "You have no pending attendance corrections."

    cards = []
    for c in corrections:
        rec = c.attendance_record
        suggested = (
            c.corrected_logout_time.strftime("%H:%M")
            if c.corrected_logout_time
            else "—"
        )
        login = rec.login_time.strftime("%H:%M") if rec.login_time else "—"
        cards.append(
            f"[CORRECTION_CARD] id: {c.id} | date: {rec.attendance_date} | "
            f"login: {login} | suggested_logout: {suggested} | "
            f"record_id: {rec.id} | reason: {(c.reason or '')[:120]} [/CORRECTION_CARD]"
        )
    return "\n".join(cards)


@tool
def confirm_attendance_correction(user_id: int, correction_id: int, logout_time: str = None):
    """
    Employee confirms a pending attendance correction.
    logout_time optional HH:MM — if omitted, keeps the suggested corrected_logout_time.
    Does not auto-approve; keeps status pending for manager review unless org auto-applies.
    Updates the correction draft so HR can approve the confirmed times.
    """
    from attendance.models import AttendanceCorrection
    from datetime import time as dt_time

    try:
        correction = AttendanceCorrection.objects.select_related(
            "attendance_record"
        ).get(id=correction_id, requested_by_id=user_id)
    except AttendanceCorrection.DoesNotExist:
        return f"Error: Correction #{correction_id} not found for this user."

    if correction._status != "pending":
        return f"Error: Correction is already {correction._status}."

    if logout_time:
        try:
            parts = logout_time.strip().split(":")
            hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            correction.corrected_logout_time = dt_time(hour, minute, 0)
        except (ValueError, IndexError):
            return "Error: logout_time must be HH:MM (e.g. 18:30)."
    elif not correction.corrected_logout_time:
        return "Error: No suggested logout time. Provide logout_time as HH:MM."

    correction.reason = (
        f"{correction.reason}\n[Confirmed by employee via AI assistant "
        f"at {timezone.now().isoformat()}]"
    ).strip()
    correction.save()

    suggested = correction.corrected_logout_time.strftime("%H:%M")
    date_str = correction.attendance_record.attendance_date
    return (
        f"[INSIGHT_CARD] title: Correction Confirmed | "
        f"message: Confirmed logout {suggested} for {date_str}. "
        f"Pending manager/HR approval. | type: info | topic: Attendance [/INSIGHT_CARD]"
    )


@tool
def review_attendance_correction(
    approver_id: int, correction_id: int, decision: str, comments: str = ""
):
    """
    Manager/HR/admin approves or rejects a pending attendance correction.
    decision: 'approved' or 'rejected'.
    """
    from django.contrib.auth import get_user_model
    from attendance.models import AttendanceCorrection
    from django.db import transaction as db_transaction

    User = get_user_model()
    try:
        approver = User.objects.get(id=approver_id)
    except User.DoesNotExist:
        return "Error: Approver not found."

    if approver.role not in ("admin", "superadmin", "hr", "manager"):
        return "Error: Not authorized to review corrections."

    try:
        correction = AttendanceCorrection.objects.select_related(
            "attendance_record", "requested_by"
        ).get(id=correction_id)
    except AttendanceCorrection.DoesNotExist:
        return f"Error: Correction #{correction_id} not found."

    if correction._status != "pending":
        return f"Error: Correction already {correction._status}."

    decision_l = (decision or "").lower().strip()
    if decision_l not in ("approved", "rejected"):
        return "Error: decision must be 'approved' or 'rejected'."

    with db_transaction.atomic():
        if decision_l == "approved":
            correction.approve(approver, comments or None)
        else:
            correction.reject(approver, comments or None)
        correction.save()

        from notifications.utils import notify_user

        notify_user(
            recipient_id=correction.requested_by_id,
            verb=decision_l,
            message=(
                f"Your attendance correction for "
                f"{correction.attendance_record.attendance_date} was {decision_l.upper()}."
            ),
            actor_id=approver.id,
            target_type="Attendance Correction",
            target_id=str(correction.id),
            level="personal",
        )

    return (
        f"[INSIGHT_CARD] title: Correction {decision_l.title()} | "
        f"message: Correction #{correction_id} for "
        f"{correction.attendance_record.attendance_date} marked {decision_l}. | "
        f"type: info | topic: Attendance [/INSIGHT_CARD]"
    )


@tool
def check_payroll_anomalies(organization_id: int, month: int, year: int):
    """
    Scan a completed payroll run for anomalies (high LOP, net pay swings,
    double deductions, zero net, missing salary structures, new-joiner pro-rata).
    Returns a structured insight card with the anomaly digest.
    """
    from payroll.models import PayrollRun
    from payroll.anomaly import scan_payroll_anomalies, format_anomaly_digest

    run = PayrollRun.objects.filter(
        organization_id=organization_id,
        month=month,
        year=year,
        status="completed",
    ).order_by("-created_at").first()

    if not run:
        return (
            "[INSIGHT_CARD] title: No Payroll Run | "
            f"message: No completed payroll run found for {month}/{year}. | "
            "type: info | topic: Payroll [/INSIGHT_CARD]"
        )

    flags = scan_payroll_anomalies(run.id)
    digest = format_anomaly_digest(flags, run)

    card_type = "warning" if flags else "info"
    return (
        f"[INSIGHT_CARD] title: Payroll Anomaly Scan | "
        f"message: {digest} | "
        f"type: {card_type} | topic: Payroll [/INSIGHT_CARD]"
    )



@tool
def get_my_onboarding_status(user_id: int):
    """
    Returns the current onboarding status for the user: status, progress percent,
    join date, pending task count, and next recommended task.
    Use when a new hire asks what is left in onboarding or their onboarding progress.
    """
    from onboarding.models import EmployeeOnboarding

    ob = (
        EmployeeOnboarding.objects.filter(user_id=user_id)
        .exclude(status="cancelled")
        .prefetch_related("tasks")
        .first()
    )
    if not ob:
        return (
            "[INSIGHT_CARD] title: No Onboarding | "
            "message: No active onboarding record found for this user. | "
            "type: info | topic: Onboarding [/INSIGHT_CARD]"
        )

    pending = [t for t in ob.tasks.all() if t.status in ("pending", "in_progress")]
    pending_sorted = sorted(pending, key=lambda t: (t.sort_order, t.id))
    nxt = pending_sorted[0] if pending_sorted else None
    if nxt:
        due = nxt.due_at or "n/a"
        next_line = f"Next: {nxt.title} ({nxt.phase}, due {due})"
    else:
        next_line = "All required tasks are done."
    return (
        f"[INSIGHT_CARD] title: Onboarding Progress | "
        f"message: Status {ob.status}, {ob.progress_pct}% complete. "
        f"{len(pending_sorted)} pending task(s). {next_line} | "
        f"type: info | topic: Onboarding | "
        f"stats: Status:{ob.status}, Progress:{ob.progress_pct}%, Pending:{len(pending_sorted)} "
        f"[/INSIGHT_CARD]"
    )


@tool
def list_pending_onboarding_tasks(user_id: int, for_assignee_only: bool = False):
    """
    Lists pending onboarding tasks for the user (as the hire) or assigned to them
    (manager/IT/HR). Set for_assignee_only=True to only show tasks assigned to this user.
    """
    from onboarding.models import OnboardingTaskInstance

    if for_assignee_only:
        qs = OnboardingTaskInstance.objects.filter(
            assignee_id=user_id, status__in=["pending", "in_progress"]
        )
    else:
        qs = OnboardingTaskInstance.objects.filter(
            onboarding__user_id=user_id, status__in=["pending", "in_progress"]
        )
    qs = qs.select_related("onboarding", "onboarding__user").order_by("sort_order", "id")[:20]
    if not qs.exists():
        return (
            "[INSIGHT_CARD] title: Onboarding Tasks | "
            "message: No pending onboarding tasks. | "
            "type: info | topic: Onboarding [/INSIGHT_CARD]"
        )

    lines_out = []
    for t in qs:
        hire = t.onboarding.user
        hire_name = f"{hire.first_name} {hire.last_name}".strip() or hire.email
        due = t.due_at or "n/a"
        lines_out.append(
            f"- {t.title} [{t.phase}/{t.assignee_role}] status={t.status} "
            f"due={due} hire={hire_name}"
        )
    body = " | ".join(lines_out)
    return (
        f"[INSIGHT_CARD] title: Pending Onboarding Tasks | "
        f"message: {body} | type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


@tool
def explain_onboarding_task(user_id: int, task_id: int = None, task_title: str = None):
    """
    Explains a specific onboarding task for the user by task_id or title search.
    """
    from onboarding.models import OnboardingTaskInstance

    task = None
    if task_id:
        task = OnboardingTaskInstance.objects.filter(
            id=task_id, onboarding__user_id=user_id
        ).first()
    elif task_title:
        task = (
            OnboardingTaskInstance.objects.filter(
                onboarding__user_id=user_id, title__icontains=task_title
            )
            .order_by("sort_order")
            .first()
        )
    if not task:
        return (
            "[ERROR_CARD] title: Task not found | "
            "message: Could not find that onboarding task. List pending tasks first. "
            "[/ERROR_CARD]"
        )

    doc_hint = (
        f" Requires document category: {task.requires_document_category}."
        if task.requires_document_category
        else ""
    )
    due = task.due_at or "n/a"
    desc = task.description or "No extra instructions."
    return (
        f"[INSIGHT_CARD] title: {task.title} | "
        f"message: Phase {task.phase}. Assigned to {task.assignee_role}. "
        f"Status {task.status}. Due {due}. {desc}{doc_hint} | "
        f"type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


@tool
def get_required_documents(user_id: int):
    """
    Lists required onboarding document categories and their verification status for the hire.
    """
    from onboarding.models import EmployeeOnboarding

    ob = (
        EmployeeOnboarding.objects.filter(user_id=user_id)
        .exclude(status="cancelled")
        .prefetch_related("tasks", "documents")
        .first()
    )
    if not ob:
        return (
            "[INSIGHT_CARD] title: Required Documents | "
            "message: No onboarding record found. | type: info | topic: Onboarding [/INSIGHT_CARD]"
        )

    needed = sorted(
        {
            t.requires_document_category
            for t in ob.tasks.all()
            if t.requires_document_category
        }
    )
    docs = {d.category: d.verification_status for d in ob.documents.all()}
    parts = []
    for cat in needed:
        parts.append(f"{cat}: {docs.get(cat, 'missing')}")
    for cat, status in docs.items():
        if cat not in needed:
            parts.append(f"{cat}: {status}")
    msg = ", ".join(parts) if parts else "No document requirements configured."
    return (
        f"[INSIGHT_CARD] title: Required Documents | "
        f"message: {msg} | type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


@tool
def complete_onboarding_task_tool(user_id: int, task_id: int, notes: str = ""):
    """
    Marks an onboarding task complete for the authenticated user when they are the assignee
    or the hire. Managers/HR completing tasks for others should pass their own user_id
    (must be the assignee).
    """
    from django.contrib.auth import get_user_model

    from onboarding.models import OnboardingTaskInstance
    from onboarding.services import complete_task

    User = get_user_model()
    task = OnboardingTaskInstance.objects.select_related("onboarding").filter(id=task_id).first()
    if not task:
        return "[ERROR_CARD] title: Task not found | message: Invalid task_id. [/ERROR_CARD]"

    user = User.objects.filter(id=user_id).first()
    if not user:
        return "[ERROR_CARD] title: User not found | message: Invalid user_id. [/ERROR_CARD]"

    allowed = (
        task.assignee_id == user_id
        or task.onboarding.user_id == user_id
        or getattr(user, "role", None) in ("admin", "hr", "superadmin")
    )
    if not allowed:
        return (
            "[ERROR_CARD] title: Not allowed | "
            "message: You cannot complete this onboarding task. [/ERROR_CARD]"
        )

    complete_task(task, completed_by=user, notes=notes or "")
    return (
        f"[INSIGHT_CARD] title: Task Completed | "
        f"message: Marked '{task.title}' as completed. "
        f"Onboarding progress is now {task.onboarding.progress_pct}%. | "
        f"type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


@tool
def suggest_onboarding_checklist(
    user_id: int,
    organization_id: int,
    prompt: str,
    employment_type: str = "",
    department: str = "",
):
    """
    HR/Admin: AI template copilot. Propose an onboarding checklist for a hiring scenario.
    Returns a preview of suggested tasks (does not save). Tell HR to review in Templates UI.
    """
    from django.contrib.auth import get_user_model
    from onboarding.ai_services import suggest_onboarding_tasks

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    if not user or getattr(user, "role", None) not in ("admin", "hr", "superadmin"):
        return (
            "[ERROR_CARD] title: Not allowed | "
            "message: Only HR/Admin can generate onboarding checklists. [/ERROR_CARD]"
        )
    if not prompt or len(prompt.strip()) < 5:
        return (
            "[ERROR_CARD] title: Prompt required | "
            "message: Describe the role (e.g. remote engineering intern). [/ERROR_CARD]"
        )

    try:
        tasks = suggest_onboarding_tasks(
            organization_id,
            prompt,
            employment_type=employment_type or "",
            department=department or "",
        )
    except Exception as e:
        return (
            f"[ERROR_CARD] title: Suggestion failed | message: {e} [/ERROR_CARD]"
        )

    if not tasks:
        return (
            "[INSIGHT_CARD] title: Onboarding Copilot | "
            "message: No tasks generated. Try a clearer scenario. | "
            "type: warning | topic: Onboarding [/INSIGHT_CARD]"
        )

    lines = [
        f"{i + 1}. {t['title']} [{t['phase']}/{t['assignee_role']}]"
        for i, t in enumerate(tasks[:14])
    ]
    body = " | ".join(lines)
    return (
        f"[INSIGHT_CARD] title: Suggested Checklist ({len(tasks)} tasks) | "
        f"message: {body}. Open Admin → Onboarding → Templates to apply with AI Copilot. | "
        f"type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


@tool
def polish_offer_letter_draft(
    user_id: int,
    organization_id: int,
    body_html: str,
    tone: str = "professional",
):
    """
    HR/Admin: Polish an offer letter HTML draft while preserving {{merge_fields}}.
    Returns rewritten HTML for the user to review before saving.
    """
    from django.contrib.auth import get_user_model
    from onboarding.ai_services import polish_offer_letter

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    if not user or getattr(user, "role", None) not in ("admin", "hr", "superadmin"):
        return (
            "[ERROR_CARD] title: Not allowed | "
            "message: Only HR/Admin can polish offer letters. [/ERROR_CARD]"
        )
    if not body_html or len(body_html.strip()) < 20:
        return (
            "[ERROR_CARD] title: Body required | "
            "message: Provide offer letter HTML to polish. [/ERROR_CARD]"
        )

    try:
        polished = polish_offer_letter(
            organization_id, body_html, tone=tone or "professional"
        )
    except Exception as e:
        return f"[ERROR_CARD] title: Polish failed | message: {e} [/ERROR_CARD]"

    preview = polished[:1200] + ("…" if len(polished) > 1200 else "")
    return (
        f"[INSIGHT_CARD] title: Offer Letter Draft | "
        f"message: Polished draft ready. Preview: {preview} | "
        f"type: info | topic: Onboarding [/INSIGHT_CARD]"
    )


# ---------------------------------------------------------------------------
# In-app navigation (ROUTE_CARD)
# ---------------------------------------------------------------------------
_EMPLOYEE_ROUTES = {
    "/dashboard": "Dashboard",
    "/leaves": "Leaves",
    "/leaves/approvals": "Leave Approvals",
    "/attendance": "Attendance",
    "/attendance/attendance-correction": "Attendance Correction",
    "/payroll": "Payroll",
    "/onboarding": "My Onboarding",
    "/policies": "Policies",
    "/profile": "Profile",
    "/team": "Team",
    "/notifications": "Notifications",
    "/feedback": "Feedback",
}

_ADMIN_ROUTES = {
    "/dashboard": "Dashboard",
    "/employees": "Employees",
    "/onboarding": "Onboarding Board",
    "/onboarding/templates": "Onboarding Templates",
    "/onboarding/letters": "Offer Letters",
    "/leaves": "Leaves",
    "/attendance": "Attendance",
    "/payroll": "Payroll",
    "/policies": "Policies",
    "/settings": "Settings",
    "/notifications": "Notifications",
    "/feedback": "Feedback",
    "/reports": "Reports",
    "/performance": "Performance",
}

# Allowed query keys for deep-links (path must still be allowlisted)
_ALLOWED_QUERY_KEYS = frozenset({"action", "tab", "highlight", "from"})


def _normalize_route_path(path: str) -> tuple[str, str]:
    """Return (pathname, full_href_with_safe_query)."""
    raw = (path or "").strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    if "?" in raw:
        pathname, query = raw.split("?", 1)
    else:
        pathname, query = raw, ""
    pathname = pathname.rstrip("/") or "/"
    if not query:
        return pathname, pathname

    from urllib.parse import parse_qsl, urlencode

    safe_pairs = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=False)
        if k in _ALLOWED_QUERY_KEYS and v
    ]
    if not safe_pairs:
        return pathname, pathname
    return pathname, f"{pathname}?{urlencode(safe_pairs)}"


@tool
def suggest_route(
    user_id: int,
    path: str,
    label: str = "",
    reason: str = "",
    context: str = "user",
):
    """
    Suggest an in-app page the user should open (never auto-redirects).
    Use when they need a form, upload, camera/geofence punch, or full page UI —
    not when an in-chat tool can finish the task alone.

    path: allowlisted app path, optionally with query.
      Employee examples: /leaves?action=apply, /attendance,
        /attendance/attendance-correction, /payroll, /onboarding, /policies
      Admin examples: /onboarding, /onboarding/templates, /leaves?tab=requests,
        /employees, /payroll
    label: button text (defaults to route name).
    reason: short why they should go there (shown on the card).
    context: 'user' (employee app) or 'admin' (admin app).
    Returns a [ROUTE_CARD] for the UI Go button.
    """
    catalog = _ADMIN_ROUTES if (context or "user").lower() == "admin" else _EMPLOYEE_ROUTES
    pathname, href = _normalize_route_path(path)

    # Admin detail routes like /onboarding/123
    if pathname not in catalog:
        if pathname.startswith("/onboarding/") and pathname.count("/") == 2:
            if (context or "user").lower() == "admin":
                default_label = "Onboarding Detail"
            else:
                return (
                    "[ERROR_CARD] title: Unknown route | "
                    "message: That path is not available in the employee app. [/ERROR_CARD]"
                )
        elif pathname.startswith("/payroll/") and pathname.count("/") == 2:
            default_label = "Payroll Detail"
        else:
            return (
                "[ERROR_CARD] title: Unknown route | "
                f"message: Path '{pathname}' is not in the allowlist. "
                "Use a known app route. [/ERROR_CARD]"
            )
    else:
        default_label = catalog[pathname]

    btn = (label or "").strip() or default_label
    why = (reason or "").strip() or f"Open {default_label} to continue."
    # Pipe separators must not appear in free text fields
    btn = btn.replace("|", "-")
    why = why.replace("|", "-")
    href_safe = href.replace("|", "")

    return (
        f"[ROUTE_CARD] path: {href_safe} | label: {btn} | "
        f"reason: {why} [/ROUTE_CARD]"
    )
