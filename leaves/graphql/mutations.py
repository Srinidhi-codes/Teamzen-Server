import strawberry
import decimal
from datetime import date
from typing import Optional

from django.db import transaction

from leaves.models import (
    LeaveType,
    LeaveBalance,
    LeaveRequest,
    CompanyHoliday,
)

from leaves.graphql.types import (
    LeaveTypeType,
    LeaveBalanceType,
    LeaveRequestType,
    CompanyHolidayType,
)

from leaves.services import (
    validate_balance,
    get_or_create_balance,
    reserve_balance,
    consume_balance,
    release_balance,
    initialize_leave_type_for_all_users,
)
from notifications.tasks import send_notification

# =====================================================
# CONSTANTS
# =====================================================

class LeaveStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# =====================================================
# UTILITY HELPERS
# =====================================================

def update_instance(instance, data: dict):
    """
    Generic helper to update model instance
    with only non-null values.
    """
    for field, value in data.items():
        if value is not None:
            setattr(instance, field, value)
    instance.save()
    return instance


# =====================================================
# INPUT TYPES
# =====================================================

@strawberry.input
class LeaveRequestInput:
    leave_type_id: strawberry.ID
    from_date: date
    to_date: date
    reason: str
    half_day_period: Optional[str] = "full_day"


@strawberry.input
class LeaveRequestProcessInput:
    request_id: strawberry.ID
    status: str
    comments: str


@strawberry.input
class LeaveBalanceInput:
    user_id: strawberry.ID
    leave_type_id: strawberry.ID
    year: int
    total_entitled: decimal.Decimal


@strawberry.input
class LeaveTypeInput:
    organization_id: strawberry.ID
    name: str
    code: str
    description: Optional[str] = ""
    max_days_per_year: int = 10
    carry_forward_allowed: bool = False
    carry_forward_max_days: int = 0
    accrual_frequency: str = "yearly"
    accrual_days: float = 0
    is_paid_leave: bool = False
    requires_approval: bool = True
    allow_encashment: bool = False
    encashment_rate: Optional[float] = 0
    prorate_on_join: bool = True
    prorate_on_exit: bool = True
    proration_basis: str = "monthly"
    is_active: bool = True


@strawberry.input
class UpdateLeaveTypeInput:
    id: strawberry.ID
    organization_id: strawberry.ID
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    max_days_per_year: Optional[int] = None
    carry_forward_allowed: Optional[bool] = None
    carry_forward_max_days: Optional[int] = None
    accrual_frequency: Optional[str] = None
    accrual_days: Optional[float] = None
    is_paid_leave: Optional[bool] = None
    requires_approval: Optional[bool] = None
    allow_encashment: Optional[bool] = None
    encashment_rate: Optional[float] = None
    prorate_on_join: Optional[bool] = None
    prorate_on_exit: Optional[bool] = None
    proration_basis: Optional[str] = None
    is_active: Optional[bool] = None


@strawberry.input
class UpdateLeaveBalanceInput:
    id: strawberry.ID
    total_entitled: Optional[decimal.Decimal] = None
    used: Optional[decimal.Decimal] = None
    pending_approval: Optional[decimal.Decimal] = None
    is_active: Optional[bool] = None


@strawberry.input
class CompanyHolidayInput:
    organization_id: strawberry.ID
    name: str
    holiday_date: date
    is_optional: bool = False
    description: Optional[str] = ""


@strawberry.input
class UpdateCompanyHolidayInput:
    id: strawberry.ID
    organization_id: strawberry.ID
    name: Optional[str] = None
    holiday_date: Optional[date] = None
    is_optional: Optional[bool] = None
    description: Optional[str] = None


# =====================================================
# MUTATIONS
# =====================================================

@strawberry.type
class LeaveMutation:

    # ----------------------------
    # LEAVE TYPE
    # ----------------------------

    @strawberry.mutation
    def create_leave_type(
        self, info, input: LeaveTypeInput
    ) -> LeaveTypeType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        leave_type = LeaveType.objects.create(**input.__dict__)

        # Initialize balances for all users
        initialize_leave_type_for_all_users(leave_type)

        return leave_type

    @strawberry.mutation
    def update_leave_type(
        self, info, input: UpdateLeaveTypeInput
    ) -> LeaveTypeType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        leave_type = LeaveType.objects.get(organization_id=input.organization_id, id=input.id)

        update_data = {
            k: v for k, v in input.__dict__.items()
            if k != "organization_id" and k != "id"
        }

        return update_instance(leave_type, update_data)

    @strawberry.mutation
    def delete_leave_type(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        LeaveType.objects.filter(id=id).delete()
        return True

    # ----------------------------
    # LEAVE BALANCE
    # ----------------------------

    @strawberry.mutation
    def create_leave_balance(
        self, info, input: LeaveBalanceInput
    ) -> LeaveBalanceType:
        return LeaveBalance.objects.create(**input.__dict__)

    @strawberry.mutation
    def update_leave_balance(
        self, info, input: UpdateLeaveBalanceInput
    ) -> LeaveBalanceType:
        balance = LeaveBalance.objects.get(id=input.id)

        update_data = {
            k: v for k, v in input.__dict__.items()
            if k != "id"
        }

        return update_instance(balance, update_data)

    @strawberry.mutation
    def delete_leave_balance(self, info, id: strawberry.ID) -> bool:
        LeaveBalance.objects.filter(id=id).delete()
        return True

    # ----------------------------
    # LEAVE REQUEST
    # ----------------------------

    @strawberry.mutation
    def create_leave_request(
        self, info, input: LeaveRequestInput
    ) -> LeaveRequestType:
        user = info.context.request.user
        leave_type = LeaveType.objects.get(id=input.leave_type_id)

        from leaves.services import create_leave_request as create_request_service
        
        with transaction.atomic():
            req = create_request_service(
                user=user,
                leave_type=leave_type,
                from_date=input.from_date,
                to_date=input.to_date,
                reason=input.reason,
                half_day_period=input.half_day_period
            )
            duration = req.duration_days # get calculated duration

            return req

    @strawberry.mutation
    def leave_request_process(
        self, info, input: LeaveRequestProcessInput
    ) -> LeaveRequestType:
        with transaction.atomic():
            req = LeaveRequest.objects.select_for_update().select_related(
                "leave_type", "user"
            ).get(id=input.request_id)

            from leaves.services import (
                get_or_create_balance,
                consume_balance,
                release_balance
            )
            balance = get_or_create_balance(req.user, req.leave_type, req.from_date.year)
            admin_user = info.context.request.user
            if not admin_user.is_authenticated or admin_user.role not in ['admin', 'superadmin', 'hr', 'manager']:
                raise Exception("Not authorized")

            if input.status == LeaveStatus.APPROVED:
                from leaves.services import approve_leave_request
                approve_leave_request(req, admin_user, comments=input.comments)
            elif input.status == LeaveStatus.REJECTED:
                from leaves.services import reject_leave_request
                reject_leave_request(req, admin_user, comments=input.comments)
            
            req.save()
            
            req.save()

        return req

    @strawberry.mutation
    def cancel_leave_request(
        self, info, requestId: strawberry.ID
    ) -> LeaveRequestType:
        from leaves.services import cancel_leave_request as cancel_service
        with transaction.atomic():
            # Use select_for_update to handle race conditions during cancellation
            req = LeaveRequest.objects.select_for_update().get(id=requestId)
            cancel_service(req)
            
            return req

    # ----------------------------
    # COMPANY HOLIDAY
    # ----------------------------

    @strawberry.mutation
    def create_company_holiday(
        self, info, input: CompanyHolidayInput
    ) -> CompanyHolidayType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        return CompanyHoliday.objects.create(**input.__dict__)

    @strawberry.mutation
    def update_company_holiday(
        self, info, input: UpdateCompanyHolidayInput
    ) -> CompanyHolidayType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        holiday = CompanyHoliday.objects.get(
            organization_id=input.organization_id, id=input.id
        )

        update_data = {
            k: v for k, v in input.__dict__.items()
            if k != "organization_id" and k != "id"
        }

        return update_instance(holiday, update_data)

    @strawberry.mutation
    def delete_company_holiday(self, info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Not authorized")
        CompanyHoliday.objects.filter(id=id).delete()
        return True

