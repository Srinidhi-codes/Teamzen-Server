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
    is_manager: Optional[bool] = None
    max_hierarchy_level: Optional[int] = None
    roles: Optional[List[str]] = None
    include_admins: Optional[bool] = None


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
    management_chain: List[UserType] = strawberry.field(default_factory=list, name="managementChain")


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
    # PUBLIC USER PROFILE
    # -------------------------
    @strawberry.field
    def public_profile(self, info: Info, id: strawberry.ID) -> Optional[UserType]:
        try:
            uid = int(str(id))
        except (ValueError, TypeError):
            return None
        try:
            return CustomUser.objects.select_related(
                "organization",
                "designation",
                "department",
                "office_location",
            ).get(pk=uid, is_active=True)
        except (CustomUser.DoesNotExist, ValueError):
            return None

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
            raise Exception("Unauthenticated")

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

        # General workforce directory hides platform/org owners unless explicitly requested or filtering for managers/roles
        should_exclude_admins = True
        if filters:
            if filters.include_admins or filters.is_manager or filters.roles or (filters.max_hierarchy_level is not None and filters.max_hierarchy_level <= 3):
                should_exclude_admins = False

        if should_exclude_admins:
            qs = qs.exclude(role__in=["admin", "superadmin"])

        if user.role == "superadmin":
            pass # full queryset
        elif user.role in ["admin", "hr"]:
            qs = qs.filter(organization=user.organization)
        elif user.role == "manager":
            qs = qs.filter(
                manager=user,
                organization=user.organization,
            ).exclude(pk=user.pk)
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

            if filters.is_manager is not None:
                if filters.is_manager:
                    qs = qs.filter(
                        Q(role__in=["superadmin", "admin", "hr", "manager"]) |
                        Q(hierarchy_level__lte=3)
                    )
                else:
                    qs = qs.exclude(
                        role__in=["superadmin", "admin", "hr", "manager"]
                    ).filter(hierarchy_level__gt=3)

            if filters.max_hierarchy_level is not None:
                qs = qs.filter(hierarchy_level__lte=filters.max_hierarchy_level)

            if filters.roles:
                qs = qs.filter(role__in=filters.roles)

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

    @strawberry.field
    def eligible_managers(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
        search: Optional[str] = None,
    ) -> List[UserType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []

        qs = CustomUser.objects.filter(is_active=True).select_related(
            "organization",
            "designation",
            "department",
            "office_location",
        )

        target_org_id = organization_id or user.organization_id
        if user.role != "superadmin":
            qs = qs.filter(organization=user.organization)
        elif target_org_id:
            qs = qs.filter(organization_id=target_org_id)

        # Managers and higher hierarchy: roles superadmin, admin, hr, manager OR hierarchy_level <= 3
        qs = qs.filter(
            Q(role__in=["superadmin", "admin", "hr", "manager"]) |
            Q(hierarchy_level__lte=3)
        )

        if search:
            search = search.strip()
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(designation__name__icontains=search)
            )

        return list(qs.order_by("hierarchy_level", "first_name", "last_name")[:100])

    @strawberry.field
    def directory_users(self, info: Info, search: Optional[str] = None) -> List[UserType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []
        
        qs = CustomUser.objects.filter(
            organization=user.organization,
            is_active=True
        ).exclude(role__in=["admin", "superadmin"])
        
        if search:
            search = search.strip()
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
            
        return qs.order_by('first_name', 'last_name')[:20]

    # -------------------------
    # TEAM HIERARCHY
    # -------------------------
    @strawberry.field
    def team_hierarchy(self, info: Info, user_id: Optional[strawberry.ID] = None) -> TeamHierarchyResponse:
        current_user = info.context.request.user
        if not current_user.is_authenticated:
            raise Exception("Unauthenticated")
            
        target_id = user_id if user_id else current_user.pk
        
        target_user = CustomUser.objects.select_related(
            "manager", "manager__designation", "manager__department", "manager__organization",
            "designation", "department", "organization", "office_location"
        ).get(pk=target_id)
        
        # Security: All authenticated users can view colleagues in their organization (similar to MS Teams).
        # Superadmin can view across organizations; others must belong to the same organization.
        if str(target_id) != str(current_user.pk):
            if current_user.role != "superadmin":
                if target_user.organization_id != current_user.organization_id:
                    raise Exception("Unauthorized to view members of another organization")
            
        manager = target_user.manager
        subordinates = list(target_user.subordinates.all().select_related("designation", "department", "organization", "office_location"))
        
        peers = []
        if manager:
            peers = list(CustomUser.objects.filter(manager=manager).exclude(pk=target_user.pk).select_related("designation", "department", "organization", "office_location"))
            
        # Build management chain all the way up (highest executive down to immediate manager)
        chain_users = []
        visited = {target_user.pk}
        curr = target_user.manager
        while curr and curr.pk not in visited:
            visited.add(curr.pk)
            chain_users.append(curr)
            curr = curr.manager
        
        management_chain = []
        if chain_users:
            chain_pks = [u.pk for u in chain_users]
            chain_users_by_pk = {
                u.pk: u for u in CustomUser.objects.filter(pk__in=chain_pks).select_related(
                    "designation", "department", "organization", "office_location"
                )
            }
            # Ordered from top-level leadership down to immediate manager
            management_chain = [chain_users_by_pk[pk] for pk in reversed(chain_pks) if pk in chain_users_by_pk]

        return TeamHierarchyResponse(
            manager=manager,
            user=target_user,
            subordinates=subordinates,
            peers=peers,
            management_chain=management_chain,
        )

    @strawberry.field(name="globalLoginHistory")
    def global_login_history(
        self,
        info: Info,
        page: int = 1,
        page_size: int = 20,
        organization_id: Optional[strawberry.ID] = None,
        search: Optional[str] = None,
    ) -> PaginatedLoginHistoryResponse:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin', 'hr']:
            raise Exception("Unauthenticated")

        qs = UserLoginHistory.objects.select_related('user', 'user__organization').order_by('-login_time')

        if user.role == "superadmin":
            if organization_id:
                qs = qs.filter(user__organization_id=organization_id)
        else:
            qs = qs.filter(user__organization_id=user.organization_id)

        if search:
            term = search.strip()
            qs = qs.filter(
                Q(user__first_name__icontains=term) |
                Q(user__last_name__icontains=term) |
                Q(user__email__icontains=term) |
                Q(ip_address__icontains=term) |
                Q(location__icontains=term)
            )

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
            raise Exception("Unauthenticated")
        
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
