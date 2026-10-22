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
    tan_number: auto
    cit_tds_office: auto
    registration_number: auto
    headquarters_address: auto
    llm_api_key: auto
    plan: auto
    plan_expires_at: auto
    payroll_cycle_day: auto
    payroll_auto_enabled: auto
    employee_count: int
    is_active: auto
    created_at: auto
    updated_at: auto

    @strawberry.field
    def accent(self) -> str:
        stored = getattr(self, "accent", None)
        return stored or "teal"

    @strawberry.field
    def can_customize_accent(self) -> bool:
        from organizations.plan_entitlements import org_has_feature

        return org_has_feature(self, "custom_accent")

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
    hierarchy_level: auto
    is_active: auto
    created_at: auto


@strawberry.type
class PlanFeatureItemType:
    key: str
    name: str
    category: str
    description: str
    free: bool
    pro: bool
    elite: bool


@strawberry.type
class OrganizationModuleEntitlementType:
    module_key: str
    name: str
    category: str
    description: str
    plan_default: bool
    is_overridden: bool
    is_enabled: bool
    notes: Optional[str] = None


@strawberry.type
class CompanyAdminDelegationType:
    organization_id: strawberry.ID
    organization_name: str
    can_manage_payroll: bool
    can_manage_leaves: bool
    can_manage_attendance: bool
    can_manage_employees: bool
    can_manage_email_templates: bool
    can_manage_onboarding: bool
    can_manage_policies: bool
    can_manage_rbac: bool
    updated_at: Optional[str] = None


@strawberry.type
class RoleModulePermissionItemType:
    module_key: str
    module_name: str
    module_category: str
    access_level: str  # 'full', 'view', 'none'


@strawberry.type
class RolePermissionMatrixType:
    organization_id: strawberry.ID
    organization_name: str
    role: str
    role_label: str
    is_system_role: bool = True
    permissions: List[RoleModulePermissionItemType]


@strawberry.type
class MyEffectivePermissionsType:
    is_superadmin: bool
    role: str
    organization_id: Optional[strawberry.ID] = None
    organization_name: Optional[str] = None
    plan: Optional[str] = None
    permissions_json: str