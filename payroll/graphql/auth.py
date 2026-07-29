"""Shared payroll GraphQL auth / org scoping helpers."""


def require_payroll_admin(user, *, allow_hr: bool = False):
    allowed = ["admin", "superadmin"]
    if allow_hr:
        allowed.append("hr")
    if not user.is_authenticated or user.role not in allowed:
        raise Exception("Unauthorized")


def require_org(user):
    """
    Resolve organization for payroll operations.
    Superadmin without an assigned org falls back to the first organization.
    """
    if getattr(user, "organization_id", None):
        return user.organization
    if user.role == "superadmin":
        from organizations.models import Organization

        org = Organization.objects.order_by("id").first()
        if org:
            return org
        raise Exception("No organization found. Create an organization first.")
    raise Exception("No organization assigned to your account.")


def scoped_qs(qs, user, field="organization"):
    """Filter queryset by org unless superadmin has no org (then return all)."""
    if user.role == "superadmin" and not getattr(user, "organization_id", None):
        return qs
    return qs.filter(**{field: user.organization})
