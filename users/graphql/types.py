from typing import Optional
import strawberry
from strawberry import auto
import strawberry.django
from users.models import CustomUser
from organizations.models import Department, Designation, OfficeLocation
from organizations.graphql.types import OfficeLocationType

@strawberry.django.type(Department)
class DepartmentType:
    id: strawberry.ID
    name: auto

@strawberry.django.type(Designation)
class DesignationType:
    id: strawberry.ID
    name: auto

@strawberry.django.type(CustomUser)
class UserType:
    id: strawberry.ID
    email: auto
    username: auto
    first_name: auto
    last_name: auto
    phone_number: auto
    role: auto
    is_active: auto
    is_verified: auto
    date_of_joining: str | None
    date_of_birth: str | None
    gender: auto
    profile_picture: auto
    
    employee_id: auto
    employment_type: auto
    manager: Optional['UserType']
    
    # Relationships
    department: DepartmentType | None
    designation: DesignationType | None
    office_location: OfficeLocationType | None
    
    # Financial
    bank_account_number: auto
    bank_ifsc_code: auto
    pan_number: auto
    aadhar_number: auto
    uan_number: auto

    created_at: auto
    updated_at: auto

    @strawberry.field
    def profile_picture_url(self) -> str | None:
        if self.profile_picture:
            return self.profile_picture.url
        return None
