"""Performance access helpers."""

from organizations.plan_entitlements import require_feature


def require_performance_access(user, *, allow_employee: bool = True):
    if not user.is_authenticated:
        raise Exception("Unauthorized")
    allowed = ["superadmin", "admin", "hr", "manager"]
    if allow_employee:
        allowed.append("employee")
    if user.role not in allowed:
        raise Exception("Unauthorized")


def resolve_perf_org(user, organization_id=None):
    from organizations.models import Organization

    if user.role == "superadmin":
        if organization_id:
            org = Organization.objects.filter(id=organization_id).first()
            if not org:
                raise Exception("Organization not found.")
            return org
        if getattr(user, "organization_id", None):
            return user.organization
        org = Organization.objects.order_by("id").first()
        if not org:
            raise Exception("No organization found.")
        return org

    if not getattr(user, "organization_id", None):
        raise Exception("No organization assigned.")
    require_feature(user.organization, "advanced_analytics")
    return user.organization
