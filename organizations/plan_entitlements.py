"""Plan entitlement helpers for feature gating."""

from datetime import date
from typing import Optional

PLAN_RANK = {"free": 0, "pro": 1, "elite": 2}

# Feature -> minimum plan required
FEATURE_MIN_PLAN = {
    "payroll_basic": "free",
    "ai_assistant": "free",
    "policies": "free",
    "payroll_auto_run": "pro",
    "salary_advances": "pro",
    "org_llm_key": "elite",
    "advanced_analytics": "elite",
}


def effective_plan(org) -> str:
    """Return active plan; expired paid plans fall back to free."""
    if not org:
        return "free"
    plan = (getattr(org, "plan", None) or "free").lower()
    if plan not in PLAN_RANK:
        plan = "free"
    if plan == "free":
        return "free"
    expires = getattr(org, "plan_expires_at", None)
    if expires and expires < date.today():
        return "free"
    return plan


def org_has_feature(org, feature: str) -> bool:
    required = FEATURE_MIN_PLAN.get(feature, "elite")
    return PLAN_RANK[effective_plan(org)] >= PLAN_RANK.get(required, 2)


def require_feature(org, feature: str, message: Optional[str] = None) -> None:
    from graphql import GraphQLError

    if org_has_feature(org, feature):
        return
    required = FEATURE_MIN_PLAN.get(feature, "elite")
    raise GraphQLError(
        message
        or f"This feature requires the {required.title()} plan. Upgrade in Settings → Plan & billing."
    )
