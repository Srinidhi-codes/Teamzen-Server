import strawberry
from typing import List, Optional
from organizations.models import Organization, OfficeLocation, Department, Designation
from organizations.graphql.types import (
    OrganizationType,
    OfficeLocationType,
    DepartmentType,
    DesignationType,
    PlanFeatureItemType,
    OrganizationModuleEntitlementType,
    CompanyAdminDelegationType,
    RolePermissionMatrixType,
    RoleModulePermissionItemType,
    MyEffectivePermissionsType,
)
from django.db.models import Count, Q

@strawberry.type
class OrganizationQuery:
    @strawberry.field
    def organizations(
        self,
        info,
        search: Optional[str] = None,
        plan: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[OrganizationType]:
        user = info.context.request.user

        queryset = Organization.objects.annotate(
            employee_count=Count('customuser', filter=Q(customuser__is_active=True))
        )

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(gst_number__icontains=search) |
                Q(pan_number__icontains=search) |
                Q(registration_number__icontains=search) |
                Q(headquarters_address__icontains=search)
            )

        if plan:
            queryset = queryset.filter(plan=plan.lower())

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view organizations")

        if user.role == "superadmin":
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(id=user.organization_id)
        raise Exception("You do not have permission to view organizations")   
    
    @strawberry.field
    def office_locations(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[OfficeLocationType]:
        user = info.context.request.user
        queryset = OfficeLocation.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(address__icontains=search) | 
                Q(city__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view office locations")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view office locations")

    @strawberry.field
    def departments(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[DepartmentType]:
        user = info.context.request.user
        queryset = Department.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view departments")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager", "employee"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view departments")
    
    @strawberry.field
    def designations(
        self,
        info,
        search: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
        is_active: Optional[bool] = None,
    ) -> List[DesignationType]:
        user = info.context.request.user
        queryset = Designation.objects.select_related("organization").all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(organization__name__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if not user.is_authenticated:
            raise Exception("You do not have permission to view designations")

        if user.role == "superadmin":
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)
            return queryset
        elif user.role in ["admin", "hr", "manager", "employee"]:
            return queryset.filter(organization_id=user.organization_id)
        else:
            raise Exception("You do not have permission to view designations")

    @strawberry.field
    def plan_feature_matrix(self, info) -> List[PlanFeatureItemType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role != "superadmin":
            raise Exception("Only Super Admin can view subscription plan feature defaults.")

        from organizations.permissions_engine import get_plan_feature_matrix
        raw = get_plan_feature_matrix()
        return [PlanFeatureItemType(**item) for item in raw]

    @strawberry.field
    def organization_entitlements(
        self, info, organization_id: strawberry.ID
    ) -> List[OrganizationModuleEntitlementType]:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")

        if user.role != "superadmin" and str(user.organization_id) != str(organization_id):
            raise Exception("Unauthorized to view organization entitlements")

        from organizations.models import Organization, PlanFeatureDefault, OrganizationFeatureOverride
        from organizations.permissions_engine import MODULE_DEFINITIONS, ensure_plan_feature_defaults
        ensure_plan_feature_defaults()

        org = Organization.objects.filter(id=organization_id).first()
        if not org:
            raise Exception("Organization not found")

        plan = org.plan or "free"
        defaults = {
            m.module_key: m.is_enabled
            for m in PlanFeatureDefault.objects.filter(plan=plan)
        }
        overrides = {
            o.module_key: (o.is_enabled, o.notes)
            for o in OrganizationFeatureOverride.objects.filter(organization=org)
        }

        results = []
        for m in MODULE_DEFINITIONS:
            k = m["key"]
            p_default = defaults.get(k, plan in m["default_plans"])
            if k in overrides:
                is_overridden = True
                is_enabled, notes = overrides[k]
            else:
                is_overridden = False
                is_enabled = p_default
                notes = None

            results.append(OrganizationModuleEntitlementType(
                module_key=k,
                name=m["name"],
                category=m["category"],
                description=m["description"],
                plan_default=p_default,
                is_overridden=is_overridden,
                is_enabled=is_enabled,
                notes=notes
            ))

        return results

    @strawberry.field
    def company_admin_delegation(
        self, info, organization_id: strawberry.ID
    ) -> CompanyAdminDelegationType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")

        if user.role != "superadmin" and str(user.organization_id) != str(organization_id):
            raise Exception("Unauthorized to view company admin delegation")

        from organizations.models import Organization
        from organizations.permissions_engine import get_company_admin_delegation

        org = Organization.objects.filter(id=organization_id).first()
        if not org:
            raise Exception("Organization not found")

        delegation = get_company_admin_delegation(org)
        from organizations.models import CompanyAdminDelegation
        record = CompanyAdminDelegation.objects.filter(organization=org).first()

        return CompanyAdminDelegationType(
            organization_id=strawberry.ID(str(org.id)),
            organization_name=org.name,
            can_manage_payroll=delegation["can_manage_payroll"],
            can_manage_leaves=delegation["can_manage_leaves"],
            can_manage_attendance=delegation["can_manage_attendance"],
            can_manage_employees=delegation["can_manage_employees"],
            can_manage_email_templates=delegation["can_manage_email_templates"],
            can_manage_onboarding=delegation["can_manage_onboarding"],
            can_manage_policies=delegation["can_manage_policies"],
            can_manage_rbac=delegation["can_manage_rbac"],
            updated_at=record.updated_at.isoformat() if record and record.updated_at else None,
        )

    @strawberry.field
    def role_permission_matrix(
        self, info, organization_id: strawberry.ID
    ) -> List[RolePermissionMatrixType]:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")

        if user.role != "superadmin":
            if str(user.organization_id) != str(organization_id):
                raise Exception("Unauthorized to view role permissions")
            if user.role != "admin":
                raise Exception("Only Admin or Super Admin can view workforce role permissions")

        from organizations.models import Organization
        from organizations.permissions_engine import MODULE_DEFINITIONS, get_role_permission_matrix, get_organization_roles

        org = Organization.objects.filter(id=organization_id).first()
        if not org:
            raise Exception("Organization not found")

        matrix = get_role_permission_matrix(org)
        roles_meta = {r["role"]: r for r in get_organization_roles(org)}

        results = []
        for role, perm_dict in matrix.items():
            meta = roles_meta.get(role, {})
            role_label = meta.get("label") or role.replace("_", " ").title()
            is_system_role = meta.get("is_system", role in ("admin", "hr", "manager", "employee"))

            items = []
            for m in MODULE_DEFINITIONS:
                k = m["key"]
                items.append(RoleModulePermissionItemType(
                    module_key=k,
                    module_name=m["name"],
                    module_category=m["category"],
                    access_level=perm_dict.get(k, "view")
                ))
            results.append(RolePermissionMatrixType(
                organization_id=strawberry.ID(str(org.id)),
                organization_name=org.name,
                role=role,
                role_label=role_label,
                is_system_role=is_system_role,
                permissions=items
            ))

        return results

    @strawberry.field
    def my_effective_permissions(self, info) -> MyEffectivePermissionsType:
        user = info.context.request.user
        import json
        from organizations.permissions_engine import MODULE_DEFINITIONS, get_user_effective_access

        if not user or not user.is_authenticated:
            empty_perms = {m["key"]: "none" for m in MODULE_DEFINITIONS}
            return MyEffectivePermissionsType(
                is_superadmin=False,
                role="anonymous",
                organization_id=None,
                organization_name=None,
                plan=None,
                permissions_json=json.dumps(empty_perms)
            )

        perms = {}
        for m in MODULE_DEFINITIONS:
            k = m["key"]
            perms[k] = get_user_effective_access(user, k)

        org = getattr(user, "organization", None)
        return MyEffectivePermissionsType(
            is_superadmin=(user.role == "superadmin"),
            role=user.role,
            organization_id=strawberry.ID(str(org.id)) if org else None,
            organization_name=org.name if org else None,
            plan=org.plan if org else None,
            permissions_json=json.dumps(perms)
        )

