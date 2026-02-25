import strawberry
from strawberry import auto
from organizations.models import OfficeLocation, Organization, Department, Designation

@strawberry.django.type(Organization)
class OrganizationType:
    id: strawberry.ID
    name: auto
    logo: auto
    gst_number: auto
    pan_number: auto
    registration_number: auto
    headquarters_address: auto
    plan: auto
    employee_count: int
    is_active: auto
    created_at: auto
    updated_at: auto

@strawberry.django.type(OfficeLocation)
class OfficeLocationType:
    id: strawberry.ID
    name: auto
    address: auto
    city: auto
    state: auto
    country: auto
    zip_code: auto
    login_time: auto
    logout_time: auto
    latitude: auto
    longitude: auto
    geo_radius_meters: auto
    organization_id: auto
    is_active: auto
    created_at: auto

@strawberry.django.type(Department)
class DepartmentType:
    id: strawberry.ID
    name: auto
    organization: OrganizationType
    description: auto
    is_active: auto
    created_at: auto

@strawberry.django.type(Designation)
class DesignationType:
    id: strawberry.ID
    name: auto
    organization: OrganizationType
    description: auto
    is_active: auto
    created_at: auto