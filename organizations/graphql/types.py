import strawberry
from strawberry import auto
from organizations.models import OfficeLocation

@strawberry.django.type(OfficeLocation)
class OfficeLocationType:
    id: strawberry.ID
    name: auto
    address: auto
    latitude: auto
    longitude: auto
    geo_radius_meters: auto
    is_active: auto
