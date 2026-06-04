import strawberry
from typing import Optional
from datetime import date, time
from organizations.models import Organization, OfficeLocation, Department, Designation
from organizations.graphql.types import OrganizationType, OfficeLocationType, DepartmentType, DesignationType
from graphql import GraphQLError

@strawberry.input
class OrganizationInput:
    name: str
    logo: Optional[str]
    gst_number: Optional[str]
    pan_number: Optional[str]
    registration_number: Optional[str]
    headquarters_address: Optional[str]
    llm_api_key: Optional[str] = None
    is_active: bool
    id: strawberry.ID
    
@strawberry.input
class CreateOrganizationInput:
    name: str
    logo: Optional[str]
    gst_number: Optional[str]
    pan_number: Optional[str]
    registration_number: Optional[str]
    headquarters_address: Optional[str]
    llm_api_key: Optional[str] = None
    is_active: bool
    
@strawberry.input
class CreateOfficeLocationInput:
    name: str
    address: str
    city: str
    state: str
    country: str
    zip_code: Optional[str]
    login_time: time
    logout_time: time
    latitude: Optional[str]
    longitude: Optional[str]
    geo_radius_meters: int
    is_active: bool
    organization_id: strawberry.ID

@strawberry.input
class UpdateOfficeLocationInput:
    id: strawberry.ID
    name: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    zip_code: Optional[str]
    login_time: Optional[time]
    logout_time: Optional[time]
    latitude: Optional[str]
    longitude: Optional[str]
    geo_radius_meters: int
    is_active: bool
    organization_id: strawberry.ID

@strawberry.input
class CreateDepartmentInput:
    name: str
    description: Optional[str]
    is_active: bool
    organization_id: strawberry.ID

@strawberry.input
class UpdateDepartmentInput:
    id: strawberry.ID
    name: str
    description: Optional[str]
    is_active: bool
    organization_id: strawberry.ID


@strawberry.input
class CreateDesignationInput:
    name: str
    description: Optional[str]
    is_active: bool
    organization_id: strawberry.ID

@strawberry.input
class UpdateDesignationInput:
    id: strawberry.ID
    name: str
    description: Optional[str]
    is_active: bool
    organization_id: strawberry.ID

# ORGANIZATION MUTATIONS
    
@strawberry.type
class OrganizationMutation:
    @strawberry.mutation
    def create_organization(
        self,
        info,
        input: CreateOrganizationInput,
    ) -> OrganizationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ['admin', 'superadmin']:
            raise GraphQLError("Not authorized")

        org = Organization.objects.create(**vars(input))
        return org

    @strawberry.mutation
    def update_organization(
        self,
        info,
        input: OrganizationInput
    ) -> OrganizationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ['admin', 'superadmin']:
            raise Exception("Not authorized")

        org = Organization.objects.get(id=input.id)
        org.name = input.name
        org.logo = input.logo
        org.gst_number = input.gst_number
        org.pan_number = input.pan_number
        org.registration_number = input.registration_number
        org.headquarters_address = input.headquarters_address
        org.llm_api_key = input.llm_api_key
        org.is_active = input.is_active
        org.save()
        return org

    @strawberry.mutation
    def suspend_organization(
        self,info,organization_id: strawberry.ID
    ) -> OrganizationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ['admin', 'superadmin']:
            raise Exception("Not authorized")

        org = Organization.objects.get(id=organization_id)
        org.is_active = False
        org.save(update_fields=['is_active'])
        return org

    @strawberry.mutation
    def activate_organization(
        self,info,organization_id: strawberry.ID
    ) -> OrganizationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ['admin', 'superadmin']:
            raise Exception("Not authorized")

        org = Organization.objects.get(id=organization_id)
        org.is_active = True
        org.save(update_fields=['is_active'])
        return org

# OFFICE LOCATION MUTATIONS

    @strawberry.mutation
    def create_office_location(
        self,
        info,
        input: CreateOfficeLocationInput,
    ) -> OfficeLocationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
            raise Exception("Not authorized")
        
        off_loc = OfficeLocation.objects.create(**vars(input))
        return off_loc
    
    @strawberry.mutation
    def update_office_location(
        self,
        info,
        input: UpdateOfficeLocationInput
    ) -> OfficeLocationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")
        
        off_loc = OfficeLocation.objects.get(id=input.id)
        off_loc.name = input.name
        off_loc.address = input.address
        off_loc.city = input.city
        off_loc.state = input.state
        off_loc.country = input.country
        off_loc.zip_code = input.zip_code
        off_loc.login_time = input.login_time
        off_loc.logout_time = input.logout_time
        off_loc.latitude = input.latitude
        off_loc.longitude = input.longitude
        off_loc.geo_radius_meters = input.geo_radius_meters
        off_loc.is_active = input.is_active
        off_loc.save()
        return off_loc
    
    @strawberry.mutation
    def suspend_office_location(
        self,info,office_location_id: strawberry.ID
    ) -> OfficeLocationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        off_loc = OfficeLocation.objects.get(id=office_location_id)
        off_loc.is_active = False
        off_loc.save(update_fields=['is_active'])
        return off_loc
    
    @strawberry.mutation
    def activate_office_location(
        self,info,office_location_id: strawberry.ID
    ) -> OfficeLocationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        off_loc = OfficeLocation.objects.get(id=office_location_id)
        off_loc.is_active = True
        off_loc.save(update_fields=['is_active'])
        return off_loc

    # DEPARTMENT MUTATIONS
    @strawberry.mutation
    def create_department(
        self,
        info,
        input: CreateDepartmentInput,
    ) -> DepartmentType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")
        
        department = Department.objects.create(**vars(input))
        return department
    
    @strawberry.mutation
    def update_department(
        self,
        info,
        input: UpdateDepartmentInput
    ) -> DepartmentType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")
        
        department = Department.objects.get(id=input.id)
        department.name = input.name
        department.description = input.description
        department.organization_id = input.organization_id
        department.is_active = input.is_active
        department.save(update_fields=['name', 'description', 'organization_id', 'is_active'])
        return department

    @strawberry.mutation
    def suspend_department(
        self,info,department_id: strawberry.ID
    ) -> DepartmentType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        department = Department.objects.get(id=department_id)
        department.is_active = False
        department.save(update_fields=['is_active'])
        return department

    @strawberry.mutation
    def activate_department(
        self,info,department_id: strawberry.ID
    ) -> DepartmentType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        department = Department.objects.get(id=department_id)
        department.is_active = True
        department.save(update_fields=['is_active'])
        return department

    # DESIGNATION MUTATIONS

    @strawberry.mutation
    def create_designation(
        self,
        info,
        input: CreateDesignationInput,
    ) -> DesignationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")
        
        designation = Designation.objects.create(**vars(input))
        return designation
    
    @strawberry.mutation
    def update_designation(
        self,
        info,
        input: UpdateDesignationInput
    ) -> DesignationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")
        
        designation = Designation.objects.get(id=input.id)
        designation.name = input.name
        designation.description = input.description
        designation.organization_id = input.organization_id
        designation.is_active = input.is_active
        designation.save()
        return designation

    @strawberry.mutation
    def suspend_designation(
        self,info,designation_id: strawberry.ID
    ) -> DesignationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        designation = Designation.objects.get(id=designation_id)
        designation.is_active = False
        designation.save(update_fields=['is_active'])
        return designation

    @strawberry.mutation
    def activate_designation(
        self,info,designation_id: strawberry.ID
    ) -> DesignationType:
        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin","hr", "manager"]:
            raise Exception("Not authorized")

        designation = Designation.objects.get(id=designation_id)
        designation.is_active = True
        designation.save(update_fields=['is_active'])
        return designation

