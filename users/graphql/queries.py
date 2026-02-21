import strawberry
from typing import Optional, List
from strawberry.types import Info
from django.db.models import Q

from users.models import CustomUser
from users.graphql.types import UserType


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

        if user.role not in ["admin", "hr", "manager"]:
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

        if user.role != "admin":
            qs = qs.filter(organization=user.organization)

        # -------------------------
        # FILTERING
        # -------------------------
        if filters:
            if filters.is_active is not None:
                qs = qs.filter(is_active=filters.is_active)

            if filters.organization_id:
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
