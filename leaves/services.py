import decimal
from datetime import date, timedelta
from django.db.models import F
from leaves.models import LeaveBalance, LeaveType, CustomUser, LeaveRequest, CompanyHoliday, LeaveAuditLog


def round_to_half_day(value) -> decimal.Decimal:
    """
    Round leave days to the nearest 0.5 so balances stay usable
    (full day / half day). Avoids stranded scraps like 0.3.
    """
    d = decimal.Decimal(str(value or 0))
    return (d * 2).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP) / 2


def get_working_days(start_date, end_date, organization):
    """
    Calculate duration excluding organization weekend days and holidays.
    """
    from organizations.workweek import is_org_weekend

    holidays = CompanyHoliday.objects.filter(
        organization=organization,
        holiday_date__range=[start_date, end_date]
    ).values_list('holiday_date', flat=True)
    
    working_days = 0
    curr = start_date
    while curr <= end_date:
        if not is_org_weekend(curr, organization) and curr not in holidays:
            working_days += 1
        curr += timedelta(days=1)
    return working_days

def get_or_create_balance(user, leave_type: LeaveType, year=None):
    year = year or date.today().year

    balance, _ = LeaveBalance.objects.get_or_create(
        user=user,
        leave_type=leave_type,
        year=year,
        defaults={
            'total_entitled': leave_type.max_days_per_year or 0,
            'used': 0,
            'pending_approval': 0,
            'carried_forward': 0,
            'accrued': 0,
            'expired': 0
        }
    )
    return balance


def reserve_balance(balance: LeaveBalance, days: float):
    balance.pending_approval = F('pending_approval') + decimal.Decimal(str(days))
    balance.save(update_fields=['pending_approval'])


def consume_balance(balance: LeaveBalance, days: float):
    balance.pending_approval = F('pending_approval') - decimal.Decimal(str(days))
    balance.used = F('used') + decimal.Decimal(str(days))
    balance.save(update_fields=['pending_approval', 'used'])


def release_balance(balance: LeaveBalance, days: float):
    balance.pending_approval = F('pending_approval') - decimal.Decimal(str(days))
    balance.save(update_fields=['pending_approval'])


def validate_balance(balance: LeaveBalance, days: float):
    available = balance.get_available_balance()
    if available < days:
        raise Exception(f"Insufficient balance. Available: {available}, Required: {days}")

def calculate_initial_entitlement(user, leave_type: LeaveType, year: int):
    full = leave_type.max_days_per_year
    join_date = user.date_joined.date()

    if not leave_type.prorate_on_join:
        return round_to_half_day(full)

    if leave_type.proration_basis == "daily":
        days_in_year = (date(year,12,31) - date(year,1,1)).days + 1
        remaining = (date(year,12,31) - join_date).days + 1
        return round_to_half_day(full * (remaining / days_in_year))

    if leave_type.proration_basis == "monthly":
        months_remaining = 12 - join_date.month + 1
        return round_to_half_day(full * (months_remaining / 12))

    if leave_type.proration_basis == "quarterly":
        quarter = (join_date.month - 1) // 3 + 1
        quarters_remaining = 4 - quarter + 1
        return round_to_half_day(full * (quarters_remaining / 4))

    return round_to_half_day(full)


def initialize_user_leave_balances(user):
    year = date.today().year
    leave_types = LeaveType.objects.filter(is_active=True)

    for lt in leave_types:
        entitlement = calculate_initial_entitlement(user, lt, year)
        LeaveBalance.objects.get_or_create(
            user=user,
            leave_type=lt,
            year=year,
            defaults={
                "total_entitled": entitlement,
                "used": 0,
                "pending_approval": 0,
                "carried_forward": 0,
                "accrued": entitlement if lt.accrual_frequency == "onetime" else 0,
                "expired": 0
            }
        )

def perform_accrual(balance: LeaveBalance):
    lt = balance.leave_type

    if lt.accrual_frequency == "monthly":
        amount = lt.accrual_days

    elif lt.accrual_frequency == "quarterly":
        amount = lt.accrual_days

    elif lt.accrual_frequency == "yearly":
        amount = lt.accrual_days

    else:
        return

    amount = round_to_half_day(amount)
    balance.total_entitled += amount
    balance.accrued += amount
    balance.last_accrued_date = date.today()
    balance.save(update_fields=["total_entitled", "accrued", "last_accrued_date"])

def create_leave_request(user, leave_type, from_date, to_date, reason, half_day_period="full_day"):
    duration = get_working_days(from_date, to_date, user.organization)
    
    # If same day and half day period selected, set duration to 0.5
    if from_date == to_date and half_day_period != "full_day":
        duration = 0.5

    year = from_date.year

    # --- VALIDATE OVERLAPS ---
    # Check if user already has an approved or pending leave during this period
    overlapping_leaves = LeaveRequest.objects.filter(
        user=user,
        _status__in=['pending', 'approved'],
        from_date__lte=to_date,
        to_date__gte=from_date
    )
    if overlapping_leaves.exists():
        overlap = overlapping_leaves.first()
        raise Exception(
            f"You already have a {overlap._status} {overlap.leave_type.name} request "
            f"from {overlap.from_date} to {overlap.to_date}. "
            "Overlapping leave requests are not allowed."
        )

    balance = get_or_create_balance(user, leave_type, year)

    validate_balance(balance, duration)
    reserve_balance(balance, duration)

    request = LeaveRequest.objects.create(
        user=user,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        duration_days=duration,
        half_day_period=half_day_period,
        reason=reason,
        _status="pending",
    )

    # Log the activity
    audit_request(request, "requested", user, reason)

    # --- NOTIFY ADMINS / MANAGERS ---
    try:
        from notifications.utils import notify_management, notify_self
        message = f"New leave request from {user.first_name} {user.last_name} for {leave_type.name} ({duration} days)."
        notify_management(
            user=user,
            verb="requested",
            message=message,
            target_type="Leave Request",
            target_id=str(request.id)
        )
        # Notify self for multi-tab sync
        notify_self(
            user=user,
            verb="requested_self",
            message="Your leave request has been submitted.",
            target_type="Leave Request",
            target_id=str(request.id)
        )
    except Exception as e:
        import traceback
        print(f"FAILED TO SEND NOTIFICATION: {e}")
        traceback.print_exc()

    # Telegram one-tap approve/reject for managers with an active bot session
    try:
        from bot_gateway.services import BotService
        BotService().notify_managers_of_leave(request)
    except Exception as e:
        print(f"FAILED TO SEND TELEGRAM LEAVE APPROVAL: {e}")

    return request

def approve_leave_request(request, approver, comments=None):
    balance = get_or_create_balance(request.user, request.leave_type, request.from_date.year)
        
    consume_balance(balance, request.duration_days)

    request.approve(approved_by=approver, comments=comments)
    request.save()

    # --- GOOGLE CALENDAR PUSH (soft) ---
    try:
        from integrations.google_calendar import create_leave_event

        event_id = create_leave_event(request)
        if event_id:
            request.google_event_id = event_id
            request.save(update_fields=["google_event_id", "updated_at"])
    except Exception as e:
        print(f"FAILED TO SYNC GOOGLE CALENDAR: {e}")

    # --- NOTIFY USER ---
    try:
        from notifications.utils import notify_user
        message = f"Your leave request for {request.leave_type.name} from {request.from_date.strftime('%b %d, %Y')} to {request.to_date.strftime('%b %d, %Y')} has been APPROVED by {approver.first_name}."
        notify_user(
            recipient_id=request.user.id,
            verb="approved",
            message=message,
            actor_id=approver.id,
            target_type="Leave Request",
            target_id=str(request.id),
            level='personal'
        )
    except Exception as e:
        print(f"FAILED TO SEND APPROVAL NOTIFICATION: {e}")

def carry_forward(balance):
    lt = balance.leave_type
    if not lt.carry_forward_allowed:
        return

    remaining = balance.get_available_balance()
    cf = min(remaining, lt.carry_forward_max_days)
    return round_to_half_day(cf)

def cancel_leave_request(request):
    if request._status == 'cancelled':
        return
        
    balance = get_or_create_balance(request.user, request.leave_type, request.from_date.year)

    if request._status == 'approved':
        balance.used = F('used') - request.duration_days
        balance.save(update_fields=['used'])
        # Remove Google Calendar event if present
        try:
            from integrations.google_calendar import delete_leave_event

            if delete_leave_event(request):
                request.google_event_id = ""
        except Exception as e:
            print(f"FAILED TO REMOVE GOOGLE CALENDAR EVENT: {e}")
    elif request._status == 'pending':
        release_balance(balance, request.duration_days)
        
    request.cancel()
    request.save()

    # Log the activity
    audit_request(request, "cancelled", request.user, comment="Cancelled by employee")

    # --- NOTIFY ADMINS / MANAGERS ---
    try:
        from notifications.utils import notify_management, notify_self
        user = request.user
        message = f"{user.first_name} {user.last_name} has cancelled their leave request for {request.leave_type.name} ({request.from_date.strftime('%b %d, %Y')} to {request.to_date.strftime('%b %d, %Y')})."
        notify_management(
            user=user,
            verb="cancelled",
            message=message,
            target_type="Leave Request",
            target_id=str(request.id)
        )
        # Notify self
        notify_self(
            user=user,
            verb="cancelled_self",
            message="Your leave request has been cancelled.",
            target_type="Leave Request",
            target_id=str(request.id)
        )
    except Exception as e:
        print(f"FAILED TO SEND CANCELLATION NOTIFICATION: {e}")

def reject_leave_request(request, actor, comments=None):
    """
    Reject a pending leave request.
    """
    balance = get_or_create_balance(request.user, request.leave_type, request.from_date.year)
    release_balance(balance, request.duration_days)
    
    request.reject(rejected_by=actor, comments=comments)
    request.save()

    # --- NOTIFY USER ---
    try:
        from notifications.utils import notify_user
        message = f"Your leave request for {request.leave_type.name} from {request.from_date.strftime('%b %d, %Y')} to {request.to_date.strftime('%b %d, %Y')} has been REJECTED by {actor.first_name}."
        if comments:
            message += f" Reason: {comments}"
        notify_user(
            recipient_id=request.user.id,
            verb="rejected",
            message=message,
            actor_id=actor.id,
            target_type="Leave Request",
            target_id=str(request.id),
            level='personal'
        )
    except Exception as e:
        print(f"FAILED TO SEND REJECTION NOTIFICATION: {e}")

def audit_request(request, action, actor, comment=None):
    LeaveAuditLog.objects.create(
        leave_request=request,
        action=action,
        actor=actor,
        comment=comment or "",
    )

def get_balance(user, leave_type: LeaveType, year=None):
    year = year or date.today().year
    return LeaveBalance.objects.filter(
        user=user, leave_type=leave_type, year=year
    ).first()

def add_accrual(balance: LeaveBalance, days):
    amount = round_to_half_day(days)
    balance.accrued += amount
    balance.total_entitled += amount
    balance.save(update_fields=["accrued", "total_entitled"])

def prorate_entitlement(user, leave_type: LeaveType, year):
    join = user.date_joined.date()
    if join.year != year:
        return round_to_half_day(leave_type.max_days_per_year)
    
    total_days = 365
    days_served = (date(year, 12, 31) - join).days + 1
    
    prorated = (leave_type.max_days_per_year * days_served) / total_days
    return round_to_half_day(prorated)

def allocate_entitlement(user, leave_type, year):
    entitlement = leave_type.max_days_per_year

    if leave_type.prorate_on_join:
        entitlement = prorate_entitlement(user, leave_type, year)
    else:
        entitlement = round_to_half_day(entitlement)

    balance = get_or_create_balance(user, leave_type, year)
    balance.total_entitled = entitlement
    balance.save(update_fields=["total_entitled"])

def run_monthly_accrual():
    today = date.today()
    if today.day != 1:
        return  # safety

    active_users = CustomUser.objects.filter(is_active=True)
    leave_types = LeaveType.objects.filter(accrual_frequency="monthly")

    for user in active_users:
        for lt in leave_types:
            if not lt.accrual_days:
                continue

            balance = get_or_create_balance(user, lt, today.year)

            add_accrual(balance, lt.accrual_days)

def run_carry_forward():
    today = date.today()
    if not (today.month == 1 and today.day == 1):
        return

    from leaves.models import LeaveBalance, LeaveType

    prev_year = today.year - 1
    balances = LeaveBalance.objects.filter(year=prev_year)

    for bal in balances:
        lt = bal.leave_type

        if not lt.carry_forward_allowed:
            continue

        cf = max(bal.total_entitled + bal.carried_forward - bal.used, 0)

        if lt.carry_forward_max_days:
            cf = min(cf, lt.carry_forward_max_days)

        cf = round_to_half_day(cf)
        new = get_or_create_balance(bal.user, lt, today.year)
        new.carried_forward = cf
        new.save(update_fields=["carried_forward"])

def apply_leave_policies(user, year):

    for lt in LeaveType.objects.filter(is_active=True):
        if lt.accrual_frequency == "yearly":
            allocate_entitlement(user, lt, year)

        elif lt.accrual_frequency == "onetime":
            allocate_entitlement(user, lt, year)

        # monthly handled by scheduler

def initialize_leave_type_for_all_users(leave_type: LeaveType):
    """
    When a new LeaveType is created, initialize balances for all active users 
    in the organization for the current year.
    """
    year = date.today().year
    users = CustomUser.objects.filter(organization=leave_type.organization, is_active=True)
    
    for user in users:
        entitlement = calculate_initial_entitlement(user, leave_type, year)
        LeaveBalance.objects.get_or_create(
            user=user,
            leave_type=leave_type,
            year=year,
            defaults={
                "total_entitled": entitlement,
                "used": 0,
                "pending_approval": 0,
                "carried_forward": 0,
                "accrued": entitlement if leave_type.accrual_frequency == "onetime" else 0,
                "expired": 0
            }
        )