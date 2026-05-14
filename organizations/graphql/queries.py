import strawberry
from typing import List, Optional
from datetime import date
from organizations.models import Organization, OfficeLocation, Department, Designation
from organizations.graphql.types import OrganizationType, OfficeLocationType, DepartmentType, DesignationType
from django.db.models import Count, Q

@strawberry.type
class OrganizationQuery:
    @strawberry.field
    def organizations(self, info, search: Optional[str] = None) -> List[OrganizationType]:
        user = info.context.request.user

        queryset = Organization.objects.annotate(
            employee_count=Count('customuser', filter=Q(customuser__is_active=True))
        )

        if search:
            queryset = queryset.filter(name__icontains=search)

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(id=user.organization_id)
        raise Exception("You do not have permission to view organizations")   
    
    @strawberry.field
    def office_locations(self, info, search: Optional[str] = None) -> List[OfficeLocationType]:
        user = info.context.request.user
        queryset = OfficeLocation.objects.all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(address__icontains=search) | 
                Q(city__icontains=search)
            )

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view office locations")

    @strawberry.field
    def departments(self, info, search: Optional[str] = None) -> List[DepartmentType]:
        user = info.context.request.user
        queryset = Department.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:         
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view departments")
    
    @strawberry.field
    def designations(self, info, search: Optional[str] = None) -> List[DesignationType]:
        user = info.context.request.user
        queryset = Designation.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view designations")