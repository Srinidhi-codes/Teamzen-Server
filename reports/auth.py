"""Auth / org scoping for analytics reports."""

from organizations.plan_entitlements import require_feature


def require_reports_access(user):
    if not user.is_authenticated:
        raise Exception("Unauthorized")
    if user.role not in ("superadmin", "admin", "hr"):
        raise Exception("Unauthorized")


def resolve_report_org(user, organization_id=None):
    """
    Resolve organization for report queries.
    Superadmin may pass organization_id; others use their org.
    Enforces Elite advanced_analytics (superadmin bypasses).
    """
    from organizations.models import Organization

    if user.role == "superadmin":
        if organization_id:
            org = Organization.objects.filter(id=organization_id).first()
            if not org:
                raise Exception("Organization not found.")
            return org
        # Prefer assigned org, else first org for platform-wide default view
        if getattr(user, "organization_id", None):
            return user.organization
        org = Organization.objects.order_by("id").first()
        if not org:
            raise Exception("No organization found.")
        return org

    if not getattr(user, "organization_id", None):
        raise Exception("No organization assigned.")
    require_feature(user.organization, "advanced_analytics")
    if organization_id and str(organization_id) != str(user.organization_id):
        raise Exception("Unauthorized to view other organizations")
    return user.organization
