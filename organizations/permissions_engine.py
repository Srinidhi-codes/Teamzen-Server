"""
Centralized Permissions & Access Control Engine for Teamzen HRMS
Implements 3-tier hierarchy:
  Tier 1: Platform Plan Entitlements & Organization Overrides (Super Admin)
  Tier 2: Company Admin Capability Delegation (Super Admin)
  Tier 3: Workforce Role Permissions Matrix (Company Admin & Super Admin)
"""
from typing import Dict, Any, List, Optional
from datetime import date
from django.utils import timezone

MODULE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "key": "dashboard",
        "name": "Dashboard & Overview",
        "category": "Core",
        "description": "Personal shift widgets, clock-in status, announcements, and quick metrics.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "view"},
    },
    {
        "key": "attendance",
        "name": "Attendance & Timesheets",
        "category": "Workforce",
        "description": "Daily punch records, timesheets, shift scheduling, and geofencing verification.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "view"},
    },
    {
        "key": "face_attendance",
        "name": "Biometric Face Attendance",
        "category": "Workforce",
        "description": "AI-powered facial recognition verification during check-in/out.",
        "default_plans": ["pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "view"},
    },
    {
        "key": "leaves",
        "name": "Leave Management",
        "category": "Workforce",
        "description": "Leave requests, approval workflows, balance tracking, and holiday calendar.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "view"},
    },
    {
        "key": "payroll",
        "name": "Payroll & Salary Slips",
        "category": "Finance",
        "description": "Salary structures, deductions, payslip generation, and bank disbursement.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "none", "employee": "view"},
    },
    {
        "key": "payroll_auto_run",
        "name": "Automated Monthly Payroll",
        "category": "Finance",
        "description": "Automatic Celery payroll run and payslip dispatch on scheduled cycle day.",
        "default_plans": ["pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "none", "employee": "none"},
    },
    {
        "key": "team",
        "name": "Employee Directory & Org Chart",
        "category": "Organization",
        "description": "Staff profiles, department groupings, reporting hierarchy, and contacts.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "view"},
    },
    {
        "key": "feed",
        "name": "Company Social Feed",
        "category": "Engagement",
        "description": "Internal workplace wall, celebration posts, announcements, and polls.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "full"},
    },
    {
        "key": "performance",
        "name": "Performance & Advanced Analytics",
        "category": "Intelligence",
        "description": "Appraisal cycles, KPI objectives, workforce trends, and productivity reports.",
        "default_plans": ["elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "view"},
    },
    {
        "key": "documents",
        "name": "Document Vault & Form-16",
        "category": "Compliance",
        "description": "Secure file storage, contracts, identity documents, and Form-16 tax certificates.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "view"},
    },
    {
        "key": "policies",
        "name": "Policies & Handbook",
        "category": "Compliance",
        "description": "Company conduct policies, compliance documents, and employee acknowledgments.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "view"},
    },
    {
        "key": "feedback",
        "name": "Feedback & Surveys",
        "category": "Engagement",
        "description": "Anonymous surveys, employee pulse checks, and 1-on-1 manager reviews.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "view"},
    },
    {
        "key": "onboarding",
        "name": "Employee Onboarding",
        "category": "HR Lifecycle",
        "description": "Pre-boarding tasks, welcome kits, document submission, and setup checklist.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "none", "employee": "none"},
    },
    {
        "key": "offboarding",
        "name": "Exit & F&F Clearance",
        "category": "HR Lifecycle",
        "description": "Resignation handling, asset recovery, department clearance, and F&F settlement.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "view", "employee": "none"},
    },
    {
        "key": "ai_assistant",
        "name": "Teamzen AI Copilot",
        "category": "Intelligence",
        "description": "Natural language HR assistance, policy queries, and automated draft writing.",
        "default_plans": ["pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "full", "manager": "full", "employee": "full"},
    },
    {
        "key": "email_templates",
        "name": "Email Automations & Templates",
        "category": "System",
        "description": "Transactional email delivery toggles, custom HTML/JSX templates, and testing.",
        "default_plans": ["free", "pro", "elite"],
        "default_role_levels": {"admin": "full", "hr": "none", "manager": "none", "employee": "none"},
    },
]

MODULE_MAP: Dict[str, Dict[str, Any]] = {m["key"]: m for m in MODULE_DEFINITIONS}


def ensure_plan_feature_defaults():
    """Populate default plan features if database is unseeded."""
    from organizations.models import PlanFeatureDefault
    for module in MODULE_DEFINITIONS:
        for plan in ["free", "pro", "elite"]:
            default_enabled = plan in module["default_plans"]
            PlanFeatureDefault.objects.get_or_create(
                plan=plan,
                module_key=module["key"],
                defaults={"is_enabled": default_enabled}
            )


def get_plan_feature_matrix() -> List[Dict[str, Any]]:
    """Returns the platform-wide feature matrix for all modules across Free, Pro, Elite."""
    from organizations.models import PlanFeatureDefault
    ensure_plan_feature_defaults()

    db_records = {}
    for r in PlanFeatureDefault.objects.all():
        db_records[(r.plan, r.module_key)] = r.is_enabled

    matrix = []
    for m in MODULE_DEFINITIONS:
        k = m["key"]
        matrix.append({
            "key": k,
            "name": m["name"],
            "category": m["category"],
            "description": m["description"],
            "free": db_records.get(("free", k), "free" in m["default_plans"]),
            "pro": db_records.get(("pro", k), "pro" in m["default_plans"]),
            "elite": db_records.get(("elite", k), "elite" in m["default_plans"]),
        })
    return matrix


def get_org_effective_modules(organization) -> Dict[str, bool]:
    """
    Computes effective enabled modules for an organization:
    Plan defaults (taking plan expiry into account) + Super Admin overrides.
    """
    if not organization:
        return {m["key"]: True for m in MODULE_DEFINITIONS}

    from organizations.models import PlanFeatureDefault, OrganizationFeatureOverride
    ensure_plan_feature_defaults()

    # Determine active plan considering expiration
    plan = organization.plan or "free"
    if plan != "free" and organization.plan_expires_at:
        if organization.plan_expires_at < timezone.localdate():
            plan = "free"

    # Base plan defaults
    defaults = {
        m.module_key: m.is_enabled
        for m in PlanFeatureDefault.objects.filter(plan=plan)
    }

    # Apply Organization Feature Overrides (Super Admin customized)
    overrides = {
        o.module_key: o.is_enabled
        for o in OrganizationFeatureOverride.objects.filter(organization=organization)
    }

    effective = {}
    for m in MODULE_DEFINITIONS:
        k = m["key"]
        if k in overrides:
            effective[k] = overrides[k]
        elif k in defaults:
            effective[k] = defaults[k]
        else:
            effective[k] = plan in m["default_plans"]

    return effective


def get_company_admin_delegation(organization) -> Dict[str, bool]:
    """
    Returns the capabilities delegated by Super Admin to the Company Admin for this organization.
    """
    if not organization:
        return {
            "can_manage_payroll": True,
            "can_manage_leaves": True,
            "can_manage_attendance": True,
            "can_manage_employees": True,
            "can_manage_email_templates": True,
            "can_manage_onboarding": True,
            "can_manage_policies": True,
            "can_manage_rbac": True,
        }

    from organizations.models import CompanyAdminDelegation
    delegation, _ = CompanyAdminDelegation.objects.get_or_create(
        organization=organization,
        defaults={
            "can_manage_payroll": True,
            "can_manage_leaves": True,
            "can_manage_attendance": True,
            "can_manage_employees": True,
            "can_manage_email_templates": True,
            "can_manage_onboarding": True,
            "can_manage_policies": True,
            "can_manage_rbac": True,
        }
    )
    return {
        "can_manage_payroll": delegation.can_manage_payroll,
        "can_manage_leaves": delegation.can_manage_leaves,
        "can_manage_attendance": delegation.can_manage_attendance,
        "can_manage_employees": delegation.can_manage_employees,
        "can_manage_email_templates": delegation.can_manage_email_templates,
        "can_manage_onboarding": delegation.can_manage_onboarding,
        "can_manage_policies": delegation.can_manage_policies,
        "can_manage_rbac": delegation.can_manage_rbac,
    }


SYSTEM_ROLES = [
    {"role": "admin", "label": "Company Admin", "is_system": True},
    {"role": "hr", "label": "Human Resources (HR)", "is_system": True},
    {"role": "manager", "label": "Team Manager", "is_system": True},
    {"role": "employee", "label": "Employee / Staff", "is_system": True},
]


def get_organization_roles(organization) -> List[Dict[str, Any]]:
    """Returns list of all active roles (system + custom) for an organization."""
    roles = [dict(r) for r in SYSTEM_ROLES]
    known_keys = {r["role"] for r in roles}
    if organization:
        from organizations.models import OrganizationRole, RoleModulePermission
        for cr in OrganizationRole.objects.filter(organization=organization):
            if cr.role_key not in known_keys:
                roles.append({
                    "role": cr.role_key,
                    "label": cr.role_label,
                    "description": cr.description,
                    "is_system": cr.is_system_role
                })
                known_keys.add(cr.role_key)
        for p in RoleModulePermission.objects.filter(organization=organization).values_list("role", flat=True).distinct():
            if p not in known_keys:
                roles.append({
                    "role": p,
                    "label": p.replace("_", " ").title(),
                    "description": None,
                    "is_system": False
                })
                known_keys.add(p)
    return roles


def get_role_permission_matrix(organization) -> Dict[str, Dict[str, str]]:
    """
    Returns the workforce role permission matrix:
    { role: { module_key: 'full' | 'view' | 'none' } }
    Includes both built-in system roles and any custom organization roles.
    """
    all_roles = get_organization_roles(organization)
    from organizations.models import RoleModulePermission

    db_permissions = {}
    if organization:
        for p in RoleModulePermission.objects.filter(organization=organization):
            db_permissions[(p.role, p.module_key)] = p.access_level

    matrix = {r["role"]: {} for r in all_roles}
    for m in MODULE_DEFINITIONS:
        k = m["key"]
        default_levels = m["default_role_levels"]
        for r_item in all_roles:
            r = r_item["role"]
            level = db_permissions.get((r, k))
            if not level:
                level = default_levels.get(r, "view")
            matrix[r][k] = level

    return matrix


def get_user_effective_access(user, module_key: str) -> str:
    """
    Core security evaluator: returns 'full', 'view', or 'none'.
    Hierarchy:
    1. Superadmin -> always 'full'.
    2. Inactive user or organization -> 'none'.
    3. Plan / Org Feature Check -> if disabled, 'none'.
    4. Company Admin ('admin') -> checks Super Admin delegation.
    5. HR, Manager, Employee -> checks RoleModulePermission matrix.
    """
    if not user or not user.is_authenticated:
        return "none"

    if user.role == "superadmin":
        return "full"

    org = getattr(user, "organization", None)
    if not org or not org.is_active:
        return "none"

    # Step 1: Check if module is enabled in Organization's Plan / Overrides
    org_modules = get_org_effective_modules(org)
    if not org_modules.get(module_key, False):
        return "none"

    # Step 2: If Company Admin, check delegation
    if user.role == "admin":
        delegation = get_company_admin_delegation(org)
        # Check specific delegation restrictions
        if module_key in ("payroll", "payroll_auto_run") and not delegation.get("can_manage_payroll", True):
            return "view"
        if module_key == "leaves" and not delegation.get("can_manage_leaves", True):
            return "view"
        if module_key in ("attendance", "face_attendance") and not delegation.get("can_manage_attendance", True):
            return "view"
        if module_key == "team" and not delegation.get("can_manage_employees", True):
            return "view"
        if module_key == "email_templates" and not delegation.get("can_manage_email_templates", True):
            return "none"
        if module_key in ("onboarding", "offboarding") and not delegation.get("can_manage_onboarding", True):
            return "view"
        if module_key == "policies" and not delegation.get("can_manage_policies", True):
            return "view"
        return "full"

    # Step 3: For other workforce roles, query RoleModulePermission
    matrix = get_role_permission_matrix(org)
    user_role = (user.role or "employee").lower()
    role_permissions = matrix.get(user_role, {})
    return role_permissions.get(module_key, "none")
