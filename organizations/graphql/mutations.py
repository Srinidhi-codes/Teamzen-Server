import strawberry
from typing import List, Optional
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
    tan_number: Optional[str] = None
    cit_tds_office: Optional[str] = None
    registration_number: Optional[str]
    headquarters_address: Optional[str]
    llm_api_key: Optional[str] = None
    accent: Optional[str] = "teal"
    face_attendance_enabled: Optional[bool] = None
    weekend_days: Optional[List[int]] = None
    is_active: bool
    id: strawberry.ID
    
@strawberry.input
class CreateOrganizationInput:
    name: str
    logo: Optional[str]
    gst_number: Optional[str]
    pan_number: Optional[str]
    tan_number: Optional[str] = None
    cit_tds_office: Optional[str] = None
    registration_number: Optional[str]
    headquarters_address: Optional[str]
    llm_api_key: Optional[str] = None
    accent: Optional[str] = "teal"
    face_attendance_enabled: Optional[bool] = False
    weekend_days: Optional[List[int]] = None
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

        payload = vars(input)
        # New orgs start on Free — custom color themes require Pro.
        payload["accent"] = "teal"

        from organizations.workweek import validate_weekend_days_input

        try:
            payload["weekend_days"] = validate_weekend_days_input(
                payload.pop("weekend_days", None)
            )
        except ValueError as e:
            raise GraphQLError(str(e))

        org = Organization.objects.create(**payload)
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
        # Clients often send logo.url (absolute Cloudinary URL) for display.
        # Never write that into ImageField — only accept storage paths / empty clear.
        if input.logo is not None:
            logo_val = (input.logo or "").strip()
            if not logo_val:
                org.logo = None
            elif not logo_val.startswith(("http://", "https://")):
                org.logo = logo_val
        org.gst_number = input.gst_number
        org.pan_number = input.pan_number
        if getattr(input, "tan_number", None) is not None:
            org.tan_number = input.tan_number
        if getattr(input, "cit_tds_office", None) is not None:
            org.cit_tds_office = input.cit_tds_office or ""
        org.registration_number = input.registration_number
        org.headquarters_address = input.headquarters_address
        if input.llm_api_key is not None and input.llm_api_key != org.llm_api_key:
            from organizations.plan_entitlements import require_feature

            require_feature(org, "org_llm_key")
        org.llm_api_key = input.llm_api_key
        if input.accent:
            valid = {c[0] for c in Organization.ACCENT_CHOICES}
            if input.accent not in valid:
                raise GraphQLError("Invalid accent color")
            from organizations.plan_entitlements import org_has_feature

            if org_has_feature(org, "custom_accent"):
                org.accent = input.accent
            # Free orgs keep stored accent but it is not applied until they upgrade.
        if input.face_attendance_enabled is not None:
            if input.face_attendance_enabled:
                from organizations.plan_entitlements import require_feature

                require_feature(
                    org,
                    "face_attendance",
                    "Face attendance requires the Pro plan. Upgrade in Settings → Plan & billing.",
                )
            org.face_attendance_enabled = input.face_attendance_enabled
        if input.weekend_days is not None:
            from organizations.workweek import validate_weekend_days_input

            try:
                org.weekend_days = validate_weekend_days_input(input.weekend_days)
            except ValueError as e:
                raise GraphQLError(str(e))
        org.is_active = input.is_active
        org.save()
        return org

    @strawberry.mutation
    def update_organization_plan(
        self,
        info,
        organization_id: strawberry.ID,
        plan: str,
        duration_days: Optional[int] = 365,
    ) -> OrganizationType:
        """Upgrade or change org plan. Sets expiry for paid plans; clears it for free."""
        from datetime import date, timedelta

        user = info.context.request.user
        if user.is_anonymous or user.role not in ["admin", "superadmin"]:
            raise GraphQLError("Not authorized")

        plan = (plan or "free").lower().strip()
        valid_plans = {c[0] for c in Organization.PLAN_CHOICES}
        if plan not in valid_plans:
            raise GraphQLError("Invalid plan. Choose free, pro, or elite.")

        org = Organization.objects.get(id=organization_id)

        # Org admins can only manage their own org; superadmin can manage any
        if user.role == "admin" and str(user.organization_id) != str(organization_id):
            raise GraphQLError("Not authorized for this organization")

        today = date.today()
        current = (org.plan or "free").lower()
        same_paid_renewal = plan == current and plan != "free"

        if same_paid_renewal:
            # Renew only on expiry day or after — not while the plan is still active
            if org.plan_expires_at and org.plan_expires_at > today:
                raise GraphQLError(
                    "Your plan is still active. You can renew on the expiry date "
                    f"({org.plan_expires_at.strftime('%d %b %Y')})."
                )

        org.plan = plan
        if plan == "free":
            org.plan_expires_at = None
        else:
            days = duration_days if duration_days and duration_days > 0 else 365
            # Always start the new period from today (renew/upgrade), not stacked mid-cycle
            org.plan_expires_at = today + timedelta(days=days)

        org.save(update_fields=["plan", "plan_expires_at", "updated_at"])
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
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
        if user.is_anonymous or user.role not in ["admin", "superadmin", "hr", "manager"]:
            raise Exception("Not authorized")

        designation = Designation.objects.get(id=designation_id)
        designation.is_active = True
        designation.save(update_fields=['is_active'])
        return designation

