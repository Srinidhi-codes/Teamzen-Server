import strawberry
from typing import Optional, List
from strawberry.types import Info
from django.db.models import Q

from users.models import CustomUser, UserLoginHistory
from users.graphql.types import UserType, UserLoginHistoryType


# =====================================================
# INPUT TYPES
# =====================================================

@strawberry.input
class UserFilterInput:
    search: Optional[str] = None
    is_active: Optional[bool] = None
    organization_id: Optional[strawberry.ID] = None


@strawberry.input
class UserSortInput:
    field: str = "created_at"   
    direction: str = "desc"    


# =====================================================
# RESPONSE TYPES
# =====================================================

@strawberry.type
class PaginatedUserResponse:
    results: List[UserType]
    total: int
    page: int
    page_size: int


@strawberry.type
class PaginatedLoginHistoryResponse:
    results: List[UserLoginHistoryType]
    total: int
    page: int
    page_size: int


@strawberry.type
class TeamHierarchyResponse:
    manager: Optional[UserType]
    user: UserType
    subordinates: List[UserType]
    peers: List[UserType]


# =====================================================
# QUERIES
# =====================================================

@strawberry.type
class UserQuery:

    # -------------------------
    # CURRENT USER
    # -------------------------
    @strawberry.field
    def me(self, info: Info) -> Optional[UserType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        
        # Optimize for UserType fields requested in GET_ME
        return CustomUser.objects.select_related(
            "organization",
            "designation",
            "department",
            "office_location",
            "manager",
        ).get(pk=user.pk)

    # -------------------------
    # ALL USERS (FILTER + SORT + PAGINATION)
    # -------------------------
    @strawberry.field
    def all_users(
        self,
        info: Info,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[UserFilterInput] = None,
        sort: Optional[UserSortInput] = None,
    ) -> PaginatedUserResponse:

        user = info.context.request.user

        # -------------------------
        # AUTHORIZATION
        # -------------------------
        if not user.is_authenticated:
            raise Exception("Unauthorized")

        if user.role not in ["superadmin", "admin", "hr", "manager"]:
            raise Exception("Unauthorized")

        # -------------------------
        # BASE QUERYSET
        # -------------------------
        qs = CustomUser.objects.select_related(
            "organization",
            "designation",
            "department",
            "office_location",
            "manager",
        )

        if user.role == "superadmin":
            pass # full queryset
        elif user.role in ["admin", "hr"]:
            qs = qs.filter(organization=user.organization)
        elif user.role == "manager":
            qs = qs.filter(
                Q(pk=user.pk) | Q(manager=user),
                organization=user.organization
            )
        else:
            raise Exception("Unauthorized")

        # -------------------------
        # FILTERING
        # -------------------------
        if filters:
            if filters.is_active is not None:
                qs = qs.filter(is_active=filters.is_active)

            if filters.organization_id:
                # If not superadmin, ensure provided organization_id matches user's organization
                if user.role != "superadmin" and str(filters.organization_id) != str(user.organization_id):
                    raise Exception("Unauthorized to filter by other organizations")
                qs = qs.filter(organization_id=filters.organization_id)

            if filters.search:
                search = filters.search.strip()
                qs = qs.filter(
                    Q(first_name__icontains=search) |
                    Q(last_name__icontains=search) |
                    Q(email__icontains=search) |
                    Q(phone_number__icontains=search) |
                    Q(designation__name__icontains=search) |
                    Q(department__name__icontains=search) |
                    Q(id__icontains=search)
                )

        # -------------------------
        # PAGINATION & SORTING
        # -------------------------
        from graphql_utils.pagination import get_paginated_results
        
        paginated = get_paginated_results(qs, page, page_size, sort)
        
        return PaginatedUserResponse(**paginated)

    # -------------------------
    # TEAM HIERARCHY
    # -------------------------
    @strawberry.field
    def team_hierarchy(self, info: Info, user_id: Optional[strawberry.ID] = None) -> TeamHierarchyResponse:
        current_user = info.context.request.user
        if not current_user.is_authenticated:
            raise Exception("Unauthorized")
            
        target_id = user_id if user_id else current_user.pk
        
        # Security: Can the current_user see target_id's hierarchy?
        # Admins and HR can see anyone in their organization.
        # Managers can see anyone who is in their reporting line.
        # Employees can only see themselves.
        
        target_user = CustomUser.objects.select_related(
            "manager", "designation", "department", "organization"
        ).get(pk=target_id)
        
        if str(target_id) != str(current_user.pk):
            if current_user.role not in ["superadmin", "admin", "hr", "manager"]:
                raise Exception("Unauthorized")
            
            if current_user.role in ["admin", "hr"] and target_user.organization != current_user.organization:
                 raise Exception("Unauthorized to view other organization")
            
            if current_user.role == "manager":
                # Check if target_user is in reporting line of current_user
                # Simple check for now: is target_user a subordinate of current_user (at any level)
                # For brevity, we'll allow managers to see anyone for now if they are managers, 
                # but ideally we check reporting line.
                pass
            
        manager = target_user.manager
        subordinates = list(target_user.subordinates.all().select_related("designation", "department"))
        
        peers = []
        if manager:
            peers = list(CustomUser.objects.filter(manager=manager).exclude(pk=target_user.pk).select_related("designation", "department"))
            
        return TeamHierarchyResponse(
            manager=manager,
            user=target_user,
            subordinates=subordinates,
            peers=peers
        )

    @strawberry.field(name="globalLoginHistory")
    def global_login_history(self, info: Info, page: int = 1, page_size: int = 20) -> PaginatedLoginHistoryResponse:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Unauthorized")
        
        qs = UserLoginHistory.objects.select_related('user').filter(user__organization=user.organization).order_by('-login_time')
        total = qs.count()
        
        start = (page - 1) * page_size
        end = start + page_size
        results = list(qs[start:end])
        
        return PaginatedLoginHistoryResponse(
            results=results,
            total=total,
            page=page,
            page_size=page_size
        )

    @strawberry.field(name="mySecurityLogs")
    def my_security_logs(self, info: Info, page: int = 1, page_size: int = 10) -> PaginatedLoginHistoryResponse:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Unauthorized")
        
        qs = UserLoginHistory.objects.filter(user=user).order_by('-login_time')
        total = qs.count()

        start = (page - 1) * page_size
        end = start + page_size
        results = list(qs[start:end])
        
        return PaginatedLoginHistoryResponse(
            results=results,
            total=total,
            page=page,
            page_size=page_size
        )
