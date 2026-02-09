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
    ) -> List[LeaveTypeType]:
        user = info.context.request.user

        if user.role == 'admin':
            return LeaveType.objects.all()
        if user.is_authenticated and user.organization_id:
            return LeaveType.objects.filter(organization_id=user.organization_id)
        return LeaveType.objects.none()

    @strawberry.field
    def leave_balance(
        self,
        info,
    ) -> List[LeaveBalanceType]:

        user = info.context.request.user
        if user.role == 'admin':
            return LeaveBalance.objects.all()
        elif user.role == 'hr':
            return LeaveBalance.objects.filter(user__organization_id=user.organization_id)
        elif user.role == 'manager':
            return LeaveBalance.objects.filter(user__manager=user)
        if user.is_authenticated:
            return LeaveBalance.objects.filter(user=user)
        return LeaveBalance.objects.none()

    @strawberry.field
    def leave_requests(
        self,
        info,
        organization_id: LeaveInput,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        if user.role == 'admin':
            if organization_id:
                return LeaveRequest.objects.filter(organization_id=organization_id)
            return LeaveRequest.objects.all()
        elif user.role == 'hr':
            return LeaveRequest.objects.filter(user__organization_id=user.organization_id)
        elif user.role == 'manager':
            return LeaveRequest.objects.filter(user__manager=user)
        if user.is_authenticated:
            return LeaveRequest.objects.filter(user=user)
        return LeaveRequest.objects.none()

    @strawberry.field
    def getLeaveRequests(
        self,
        info,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        if user.role == 'admin':
            return LeaveRequest.objects.all()
        elif user.role =='hr':
            return LeaveRequest.objects.filter(user__organization_id=user.organization_id)
        elif user.role =='manager':
            return LeaveRequest.objects.filter(user__manager=user)
        elif user.is_authenticated:
            return LeaveRequest.objects.filter(user=user)
        return LeaveRequest.objects.none()