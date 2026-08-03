"""Shared payroll GraphQL auth / org scoping helpers."""


def require_payroll_admin(user, *, allow_hr: bool = False):
    allowed = ["admin", "superadmin"]
    if allow_hr:
        allowed.append("hr")
    if not user.is_authenticated or user.role not in allowed:
        raise Exception("Unauthorized")


def require_org(user, organization_id=None):
    """
    Resolve organization for payroll operations.
    Superadmin may pass organization_id explicitly; otherwise falls back to first org.
    """
    if organization_id:
        from organizations.models import Organization

        org = Organization.objects.filter(id=organization_id).first()
        if not org:
            raise Exception("Organization not found.")
        if user.role != "superadmin" and str(user.organization_id) != str(organization_id):
            raise Exception("Unauthorized to access this organization.")
        return org

    if getattr(user, "organization_id", None):
        return user.organization
    if user.role == "superadmin":
        from organizations.models import Organization

        org = Organization.objects.order_by("id").first()
        if org:
            return org
        raise Exception("No organization found. Create an organization first.")
    raise Exception("No organization assigned to your account.")


def scoped_qs(qs, user, field="organization", organization_id=None):
    """
    Filter queryset by org.
    Superadmin without an assigned org sees all unless organization_id is provided.
    """
    if organization_id:
        if user.role != "superadmin" and str(getattr(user, "organization_id", None)) != str(organization_id):
            raise Exception("Unauthorized to filter by other organizations")
        # Support both "organization" and nested "payroll_run__organization"
        if field.endswith("organization"):
            return qs.filter(**{f"{field}_id": organization_id})
        return qs.filter(**{field: organization_id})

    if user.role == "superadmin" and not getattr(user, "organization_id", None):
        return qs
    return qs.filter(**{field: user.organization})
