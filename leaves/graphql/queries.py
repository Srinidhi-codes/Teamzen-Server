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
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[LeaveTypeType]:
        user = info.context.request.user
        queryset = LeaveType.objects.select_related("organization").all()

        if not user.is_authenticated:
            return LeaveType.objects.none()

        if user.role != 'superadmin':
            if user.organization_id:
                queryset = queryset.filter(organization_id=user.organization_id)
            else:
                return LeaveType.objects.none()
        elif organization_id:
            queryset = queryset.filter(organization_id=organization_id)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search) |
                Q(organization__name__icontains=search)
            )

        return queryset

    @strawberry.field
    def leave_balance(
        self,
        info,
        all_org: Optional[bool] = False,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[LeaveBalanceType]:

        user = info.context.request.user
        queryset = LeaveBalance.objects.select_related(
            "user",
            "user__organization",
            "user__department",
            "user__manager",
            "leave_type",
        ).all()

        if not user.is_authenticated:
            return LeaveBalance.objects.none()

        if user.role != 'superadmin':
            if not user.organization_id:
                return LeaveBalance.objects.none()

            # If all_org is True and user has permission, show all in organization
            if all_org:
                if user.role in ['admin', 'hr']:
                    queryset = queryset.filter(user__organization_id=user.organization_id)
                elif user.role == 'manager':
                    queryset = queryset.filter(
                        Q(user=user) | Q(user__manager=user),
                        user__organization_id=user.organization_id
                    )
            else:
                # Default to only returning the current user's balance
                queryset = queryset.filter(user=user)
        elif organization_id:
            queryset = queryset.filter(user__organization_id=organization_id)

        # Current year balances for the admin portfolio (avoid stale years cluttering UI)
        queryset = queryset.filter(year=date.today().year, is_active=True)

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__department__name__icontains=search) |
                Q(user__organization__name__icontains=search)
            )

        return queryset.order_by("user__first_name", "user__last_name", "leave_type__name")

    @strawberry.field
    def leave_requests(
        self,
        info,
        organization_id: Optional[LeaveInput] = None,
        search: Optional[str] = None,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        queryset = LeaveRequest.objects.all()

        if not user.is_authenticated:
            return LeaveRequest.objects.none()

        if user.role == 'superadmin':
            if organization_id:
                queryset = queryset.filter(user__organization_id=organization_id.organization_id)
        else:
            if not user.organization_id:
                return LeaveRequest.objects.none()

            if user.role in ['admin', 'hr']:
                queryset = queryset.filter(user__organization_id=user.organization_id)
            elif user.role == 'manager':
                queryset = queryset.filter(
                    Q(user=user) | Q(user__manager=user),
                    user__organization_id=user.organization_id
                )
            else:
                queryset = queryset.filter(user=user)

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(leave_type__name__icontains=search) |
                Q(_status__icontains=search)
            )

        return queryset

    @strawberry.field
    def getLeaveRequests(
        self,
        info,
        approvals_only: Optional[bool] = False,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[LeaveRequestType]:
        user = info.context.request.user
        queryset = LeaveRequest.objects.select_related(
            "user", "user__organization", "leave_type"
        ).all()

        if not user.is_authenticated:
            return LeaveRequest.objects.none()

        if user.role != 'superadmin':
            if not user.organization_id:
                return LeaveRequest.objects.none()

            if approvals_only:
                if user.role in ['admin', 'hr']:
                    # Admins/HR see everything to approve/review
                    queryset = queryset.filter(user__organization_id=user.organization_id)
                elif user.role == 'manager':
                    # Managers see their direct reports
                    queryset = queryset.filter(
                        user__manager=user,
                        user__organization_id=user.organization_id
                    )
                else:
                    return LeaveRequest.objects.none()
            else:
                # Default: only return current user's leaves
                queryset = queryset.filter(user=user)
        elif organization_id:
            queryset = queryset.filter(user__organization_id=organization_id)

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(leave_type__name__icontains=search) |
                Q(_status__icontains=search) |
                Q(user__organization__name__icontains=search)
            )
        
        return queryset

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
    def company_holidays(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[CompanyHolidayType]:
        user = info.context.request.user
        queryset = CompanyHoliday.objects.select_related("organization").all()

        if not user.is_authenticated:
            return []
        
        if user.role != 'superadmin':
            if not user.organization_id:
                return []
            queryset = queryset.filter(organization_id=user.organization_id)
        elif organization_id:
            queryset = queryset.filter(organization_id=organization_id)
            
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search) |
                Q(organization__name__icontains=search)
            )

        return queryset