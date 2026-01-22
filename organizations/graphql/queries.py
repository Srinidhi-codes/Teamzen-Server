import strawberry
from typing import List, Optional
from datetime import date
from organizations.models import Organization, OfficeLocation, Department, Designation
from organizations.graphql.types import OrganizationType, OfficeLocationType, DepartmentType, DesignationType
from django.db.models import Count, Q

@strawberry.type
class OrganizationQuery:
    @strawberry.field
    def organizations(self, info) -> List[OrganizationType]:
        user = info.context.request.user

        queryset = Organization.objects.annotate(
            employee_count=Count('customuser', filter=Q(customuser__is_active=True))
        )

        if user.role == "admin":
            return queryset

        elif user.role in ["hr", "manager"]:
            return queryset.filter(id=user.organization_id)

        raise Exception("You do not have permission to view organizations")   
    
    @strawberry.field
    def office_locations(self, info) -> List[OfficeLocationType]:
        user = info.context.request.user
        if user.role == "admin":
            return OfficeLocation.objects.all()
        elif user.role in ["hr", "manager"]:
            return OfficeLocation.objects.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view office locations")

    @strawberry.field
    def departments(self,info) -> List[DepartmentType]:
        user = info.context.request.user
        if user.role == "admin":
            return Department.objects.all()
        elif user.role in ["hr", "manager"]:         
            return Department.objects.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view departments")
    
    @strawberry.field
    def designations(self,info) -> List[DesignationType]:
        user = info.context.request.user
        if user.role == "admin":
            return Designation.objects.all()
        elif user.role in ["hr", "manager"]:
            return Designation.objects.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view designations")