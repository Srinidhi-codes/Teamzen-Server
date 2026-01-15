from datetime import date
from leaves.models import LeaveBalance, LeaveType

def get_or_create_balance(user, leave_type: LeaveType):
    year = date.today().year

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
    balance.pending_approval += days
    balance.save(update_fields=['pending_approval'])


def consume_balance(balance: LeaveBalance, days: float):
    balance.pending_approval -= days
    balance.used += days
    balance.save(update_fields=['pending_approval', 'used'])


def release_balance(balance: LeaveBalance, days: float):
    balance.pending_approval -= days
    balance.save(update_fields=['pending_approval'])


def validate_balance(balance: LeaveBalance, days: float):
    available = balance.get_available_balance()
    if available < days:
        raise Exception(f"Insufficient balance. Available: {available}, Required: {days}")

def calculate_initial_entitlement(user, leave_type: LeaveType, year: int):
    full = leave_type.max_days_per_year
    join_date = user.date_joined.date()

    if not leave_type.prorate_on_join:
        return full

    if leave_type.proration_basis == "daily":
        days_in_year = (date(year,12,31) - date(year,1,1)).days + 1
        remaining = (date(year,12,31) - join_date).days + 1
        return round(full * (remaining / days_in_year), 2)

    if leave_type.proration_basis == "monthly":
        months_remaining = 12 - join_date.month + 1
        return round(full * (months_remaining / 12), 2)

    if leave_type.proration_basis == "quarterly":
        quarter = (join_date.month - 1) // 3 + 1
        quarters_remaining = 4 - quarter + 1
        return round(full * (quarters_remaining / 4), 2)

    return full


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

    balance.total_entitled += amount
    balance.accrued += amount
    balance.last_accrued_date = date.today()
    balance.save(update_fields=["total_entitled", "accrued", "last_accrued_date"])

def create_leave_request(user, leave_type, from_date, to_date, reason):
    duration = (to_date - from_date).days + 1
    year = from_date.year

    balance = LeaveBalance.objects.get(user=user, leave_type=leave_type, year=year)

    validate_balance(balance, duration)
    reserve_balance(balance, duration)

    return LeaveRequest.objects.create(
        user=user,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        duration_days=duration,
        reason=reason,
        status="pending",
    )

def approve_leave_request(request, approver, comments=None):
    consume_balance(request.leavebalance, request.duration_days)

    request.status = "approved"
    request.approved_by = approver
    request.approval_comments = comments
    request.approved_at = timezone.now()
    request.save(update_fields=["status", "approved_by", "approval_comments", "approved_at"])

def carry_forward(balance):
    lt = balance.leave_type
    if not lt.carry_forward_allowed:
        return

    remaining = balance.get_available_balance()
    cf = min(remaining, lt.carry_forward_max_days)

    return cf

def cancel_leave_request(request):
    release_balance(request.leavebalance, request.duration_days)
    request.status = "cancelled"
    request.save(update_fields=["status"])

def audit_request(request, action, actor, comment=None):
    LeaveAuditLog.objects.create(
        leave_request=request,
        action=action,
        actor=actor,
        comment=comment
    )