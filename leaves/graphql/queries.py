import strawberry
from typing import List, Optional
from datetime import date
from leaves.models import LeaveType, LeaveBalance, LeaveRequest, CompanyHoliday
from leaves.graphql.types import LeaveTypeType, LeaveBalanceType, LeaveRequestType, CompanyHolidayType

@strawberry.input
class LeaveInput:
    organization_id: strawberry.ID

@strawberry.type
class LeaveQuery:
    @strawberry.field
    def leave_types(
        self,
        info,
        organization_id: LeaveInput,
    ) -> List[LeaveTypeType]:
        if organization_id:
            return LeaveType.objects.filter(organization_id=organization_id)
        return LeaveType.objects.all()

    @strawberry.field
    def leave_balance(
        self,
        info,
    ) -> List[LeaveBalanceType]:

        user = info.context.request.user
        if user:
            return LeaveBalance.objects.filter(user=user)
        return LeaveBalance.objects.all()

    @strawberry.field
    def leave_requests(
        self,
        info,
        organization_id: LeaveInput,
    ) -> List[LeaveRequestType]:
        if organization_id:
            return LeaveRequest.objects.filter(organization_id=organization_id)
        return LeaveRequest.objects.all()
