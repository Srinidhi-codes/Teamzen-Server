"""Offboarding access helpers."""


def require_auth(user):
    if not user or not user.is_authenticated:
        raise Exception("Unauthorized")


def require_hr(user):
    require_auth(user)
    if user.role not in ("superadmin", "admin", "hr"):
        raise Exception("Only admin/HR can perform this action")


def resolve_org(user, organization_id=None):
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
    return user.organization


def can_view_offboarding(user, offboarding) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.role == "superadmin":
        return True
    if user.role in ("admin", "hr") and offboarding.organization_id == user.organization_id:
        return True
    if offboarding.user_id == user.id:
        return True
    if user.role == "manager" and offboarding.user.manager_id == user.id:
        return True
    if offboarding.tasks.filter(assignee_id=user.id).exists():
        return True
    return False
