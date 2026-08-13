"""Helpers for exited employees who still need F&F / documents access."""


def has_exit_portal_access(user) -> bool:
    """True when the user has a non-cancelled offboarding (F&F) record."""
    if not user or not getattr(user, "id", None):
        return False
    try:
        from offboarding.models import EmployeeOffboarding

        return (
            EmployeeOffboarding.objects.filter(user_id=user.id)
            .exclude(status="cancelled")
            .exists()
        )
    except Exception:
        return False


def can_authenticate_user(user) -> bool:
    """Active staff, or inactive staff with an open F&F portal."""
    if not user:
        return False
    if getattr(user, "is_active", False):
        return True
    return has_exit_portal_access(user)


def inactive_login_blocked_message() -> str:
    return (
        "This account is inactive. If you have an exit / F&F checklist, "
        "use the magic link from HR, or sign in only after F&F has been started."
    )
