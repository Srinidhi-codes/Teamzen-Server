from typing import Optional
import strawberry
import strawberry.django
from strawberry import auto
from users.graphql.types import UserType
from organizations.graphql.types import OrganizationType
from leaves.models import LeaveType, LeaveBalance, LeaveRequest, CompanyHoliday

@strawberry.django.type(LeaveType)
class LeaveTypeType:
    id: strawberry.ID
    organization: OrganizationType
    name: auto
    code: auto
    description: auto
    max_days_per_year: auto
    carry_forward_allowed: auto
    carry_forward_max_days: auto
    accrual_frequency: auto
    accrual_days: auto
    is_paid_leave: auto
    requires_approval: auto
    is_active: auto
    allow_encashment: auto
    encashment_rate: auto
    prorate_on_join: auto
    prorate_on_exit: auto
    proration_basis: auto
    created_at: auto
    updated_at: auto

@strawberry.django.type(LeaveBalance)
class LeaveBalanceType:
    id: strawberry.ID
    user: UserType
    leave_type: LeaveTypeType
    year: auto
    total_entitled: auto
    used: auto
    last_accrued_date: auto
    pending_approval: auto
    accrued: auto
    expired: auto
    is_locked: auto
    locked_at: auto
    last_updated: auto
    @strawberry.field
    def available_balance(self) -> float:
        return float(self.get_available_balance())

@strawberry.django.type(LeaveRequest)
class LeaveRequestType:
    id: strawberry.ID
    user: UserType
    leave_type: LeaveTypeType
    from_date: auto
    to_date: auto
    duration_days: auto
    reason: auto
    status: auto
    approved_by: Optional[UserType]
    approval_comments: auto
    approved_at: auto
    created_at: auto

@strawberry.django.type(CompanyHoliday)
class CompanyHolidayType:
    id: strawberry.ID
    organization: OrganizationType
    name: auto
    holiday_date: auto
    is_optional: auto
    description: auto
    created_at: auto

