import strawberry
from typing import List, Optional
from strawberry import auto
from organizations.models import OfficeLocation, Organization, Department, Designation
from organizations.workweek import normalize_weekend_days

@strawberry.django.type(Organization)
class OrganizationType:
    id: strawberry.ID
    name: auto
    logo: auto
    gst_number: auto
    pan_number: auto
    registration_number: auto
    headquarters_address: auto
    llm_api_key: auto
    plan: auto
    plan_expires_at: auto
    payroll_cycle_day: auto
    payroll_auto_enabled: auto
    accent: auto
    employee_count: int
    is_active: auto
    created_at: auto
    updated_at: auto

    @strawberry.field
    def face_attendance_enabled(self) -> bool:
        """Off for Free plan even if the org setting is still stored as on."""
        from organizations.plan_entitlements import org_has_feature

        if not org_has_feature(self, "face_attendance"):
            return False
        return bool(getattr(self, "face_attendance_enabled", False))

    @strawberry.field
    def weekend_days(self) -> List[int]:
        return normalize_weekend_days(getattr(self, "weekend_days", None))

    @strawberry.field
    def can_enable_payroll_auto(self) -> bool:
        from organizations.plan_entitlements import org_has_feature

        return org_has_feature(self, "payroll_auto_run")

    @strawberry.field
    def can_enable_face_attendance(self) -> bool:
        from organizations.plan_entitlements import org_has_feature

        return org_has_feature(self, "face_attendance")

    @strawberry.field
    def days_until_plan_expiry(self) -> Optional[int]:
        expires = getattr(self, "plan_expires_at", None)
        if not expires:
            return None
        from datetime import date

        return (expires - date.today()).days

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
    organization: OrganizationType
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