import strawberry
from strawberry import auto
from organizations.models import OfficeLocation, Organization

@strawberry.django.type(Organization)
class OrganizationType:
    id: strawberry.ID
    name: auto
    logo: auto
    gst_number: auto
    pan_number: auto
    registration_number: auto
    headquarters_address: auto
    is_active: auto
    created_at: auto
    updated_at: auto

@strawberry.django.type(OfficeLocation)
class OfficeLocationType:
    id: strawberry.ID
    name: auto
    address: auto
    latitude: auto
    longitude: auto
    geo_radius_meters: auto
    is_active: auto
