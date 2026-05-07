import strawberry
from django.db.models import Q
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

        if user.role == 'superadmin':
            return LeaveType.objects.all()
        if user.is_authenticated and user.organization_id:
            return LeaveType.objects.filter(organization_id=user.organization_id)
        return LeaveType.objects.none()

    @strawberry.field
    def leave_balance(
        self,
        info,
        all_org: Optional[bool] = False,
    ) -> List[LeaveBalanceType]:

        user = info.context.request.user
        if user.role == 'superadmin':
            return LeaveBalance.objects.all()
        
        if not user.is_authenticated or not user.organization_id:
            return LeaveBalance.objects.none()

        # If all_org is True and user has permission, show all in organization
        if all_org:
            if user.role in ['admin', 'hr']:
                return LeaveBalance.objects.filter(user__organization_id=user.organization_id)
            elif user.role == 'manager':
                return LeaveBalance.objects.filter(
                    Q(user=user) | Q(user__manager=user),
                    user__organization_id=user.organization_id
                )
        
        # Default to only returning the current user's balance
        return LeaveBalance.objects.filter(user=user)

    @strawberry.field
    def leave_requests(
        self,
        info,
        organization_id: Optional[LeaveInput] = None,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        if user.role == 'superadmin':
            if organization_id:
                return LeaveRequest.objects.filter(user__organization_id=organization_id.organization_id)
            return LeaveRequest.objects.all()
        
        if not user.is_authenticated or not user.organization_id:
            return LeaveRequest.objects.none()

        if user.role in ['admin', 'hr']:
            return LeaveRequest.objects.filter(user__organization_id=user.organization_id)
        elif user.role == 'manager':
            return LeaveRequest.objects.filter(
                Q(user=user) | Q(user__manager=user),
                user__organization_id=user.organization_id
            )
        else:
            return LeaveRequest.objects.filter(user=user)

    @strawberry.field
    def getLeaveRequests(
        self,
        info,
        approvals_only: Optional[bool] = False
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        if user.role == 'superadmin':
            return LeaveRequest.objects.all()
        
        if not user.is_authenticated or not user.organization_id:
            return LeaveRequest.objects.none()

        if approvals_only:
            if user.role in ['admin', 'hr']:
                # Admins/HR see everything to approve/review
                return LeaveRequest.objects.filter(user__organization_id=user.organization_id)
            elif user.role == 'manager':
                # Managers see their direct reports
                return LeaveRequest.objects.filter(
                    user__manager=user,
                    user__organization_id=user.organization_id
                )
            else:
                return LeaveRequest.objects.none()
        
        # Default: only return current user's leaves
        return LeaveRequest.objects.filter(user=user)

    @strawberry.field
    def team_leaves(
        self,
        info,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        if not user.is_authenticated or not user.department:
            return []
        
        # Get approved or pending leaves for users in the same department AND organization, excluding current user
        return LeaveRequest.objects.filter(
            user__organization_id=user.organization_id,
            user__department=user.department,
            _status__in=['approved', 'pending'],
            to_date__gte=date.today()
        ).exclude(user=user).order_by('from_date')

    @strawberry.field
    def company_holidays(self, info) -> List[CompanyHolidayType]:
        user = info.context.request.user
        if not user.is_authenticated or not user.organization_id:
            return []
        return CompanyHoliday.objects.filter(organization_id=user.organization_id)