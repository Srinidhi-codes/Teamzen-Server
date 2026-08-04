"""Onboarding access helpers."""


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


def can_view_onboarding(user, onboarding) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.role == "superadmin":
        return True
    if user.role in ("admin", "hr") and onboarding.organization_id == user.organization_id:
        return True
    if onboarding.user_id == user.id:
        return True
    if user.role == "manager" and onboarding.user.manager_id == user.id:
        return True
    if onboarding.tasks.filter(assignee_id=user.id).exists():
        return True
    return False
