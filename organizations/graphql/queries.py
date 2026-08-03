import strawberry
from typing import List, Optional
from organizations.models import Organization, OfficeLocation, Department, Designation
from organizations.graphql.types import OrganizationType, OfficeLocationType, DepartmentType, DesignationType
from django.db.models import Count, Q

@strawberry.type
class OrganizationQuery:
    @strawberry.field
    def organizations(
        self,
        info,
        search: Optional[str] = None,
        plan: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[OrganizationType]:
        user = info.context.request.user

        queryset = Organization.objects.annotate(
            employee_count=Count('customuser', filter=Q(customuser__is_active=True))
        )

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(gst_number__icontains=search) |
                Q(pan_number__icontains=search) |
                Q(registration_number__icontains=search) |
                Q(headquarters_address__icontains=search)
            )

        if plan:
            queryset = queryset.filter(plan=plan.lower())

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view organizations")

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(id=user.organization_id)
        raise Exception("You do not have permission to view organizations")   
    
    @strawberry.field
    def office_locations(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[OfficeLocationType]:
        user = info.context.request.user
        queryset = OfficeLocation.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(address__icontains=search) | 
                Q(city__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view office locations")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view office locations")

    @strawberry.field
    def departments(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[DepartmentType]:
        user = info.context.request.user
        queryset = Department.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view departments")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager", "employee"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view departments")
    
    @strawberry.field
    def designations(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[DesignationType]:
        user = info.context.request.user
        queryset = Designation.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view designations")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager", "employee"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view designations")
