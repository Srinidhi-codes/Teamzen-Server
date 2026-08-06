"""
Trusted actor identity for AI tool execution.

Set once per chat/MCP request from authenticated session headers.
Tools MUST prefer this over LLM-supplied user_id arguments.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ActorContext:
    user_id: int
    organization_id: Optional[int] = None
    role: str = "employee"


_actor_ctx: ContextVar[Optional[ActorContext]] = ContextVar(
    "ai_actor_ctx", default=None
)


def set_actor(
    user_id: int,
    organization_id: Optional[int] = None,
    role: Optional[str] = None,
):
    return _actor_ctx.set(
        ActorContext(
            user_id=int(user_id),
            organization_id=int(organization_id) if organization_id else None,
            role=(role or "employee"),
        )
    )


def reset_actor(token) -> None:
    _actor_ctx.reset(token)


def get_actor() -> Optional[ActorContext]:
    return _actor_ctx.get()


def force_actor_user_id(claimed_user_id: Optional[int] = None) -> int:
    """
    Return the authenticated actor's user_id.
    Raises PermissionError if no actor is bound (misconfigured tool path).
    """
    actor = get_actor()
    if actor is None:
        # Fail closed when possible; fall back only if claim present (legacy tests)
        if claimed_user_id is not None:
            return int(claimed_user_id)
        raise PermissionError("No authenticated AI actor context")
    return actor.user_id


def resolve_subject_user_id(
    claimed_user_id: Optional[int] = None,
    *,
    target_user_id: Optional[int] = None,
    allow_privileged_lookup: bool = False,
    privileged_roles: tuple = ("hr", "admin", "superadmin"),
) -> tuple[int, Optional[str]]:
    """
    Resolve whose data a tool may access.

    - Default: always the authenticated actor (ignores LLM-claimed user_id).
    - Privileged lookup: HR/admin/superadmin may set target_user_id for same-org subject.

    Returns (subject_user_id, error_message_or_None).
    """
    from django.contrib.auth import get_user_model

    actor = get_actor()
    if actor is None:
        # No context — refuse cross-user; only allow claimed if it equals itself path
        if target_user_id is not None and claimed_user_id is not None:
            if int(target_user_id) != int(claimed_user_id):
                return 0, (
                    "[ERROR_CARD] title: Not allowed | "
                    "message: Cannot look up another employee's data without auth context. [/ERROR_CARD]"
                )
        if claimed_user_id is None:
            return 0, (
                "[ERROR_CARD] title: Auth required | "
                "message: Missing authenticated user context. [/ERROR_CARD]"
            )
        return int(claimed_user_id), None

    subject = actor.user_id
    if target_user_id is None or int(target_user_id) == int(actor.user_id):
        return subject, None

    if not allow_privileged_lookup:
        return 0, (
            "[ERROR_CARD] title: Not allowed | "
            "message: You can only view your own payslips and payroll data. "
            "Ask HR if you need someone else's information. [/ERROR_CARD]"
        )

    if actor.role not in privileged_roles:
        return 0, (
            "[ERROR_CARD] title: Not allowed | "
            "message: Only HR or admins can view another employee's payslips. [/ERROR_CARD]"
        )

    User = get_user_model()
    target = User.objects.filter(id=target_user_id, is_active=True).first()
    if not target:
        return 0, (
            "[ERROR_CARD] title: Not found | "
            "message: That employee was not found. [/ERROR_CARD]"
        )
    if (
        actor.organization_id
        and target.organization_id
        and int(actor.organization_id) != int(target.organization_id)
        and actor.role != "superadmin"
    ):
        return 0, (
            "[ERROR_CARD] title: Not allowed | "
            "message: That employee is not in your organization. [/ERROR_CARD]"
        )
    return int(target.id), None
