"""GraphQL types + query for First-Day Wizard."""

from __future__ import annotations

from typing import List, Optional

import strawberry
from strawberry.types import Info


@strawberry.type
class FirstDayWizardStepType:
    id: str
    title: str
    summary: str
    route: Optional[str]
    route_label: Optional[str]
    bullets: List[str]


@strawberry.type
class FirstDayWizardProfileType:
    first_name: str
    full_name: str
    role: str
    department: Optional[str]
    designation: Optional[str]
    organization: Optional[str]


@strawberry.type
class FirstDayWizardOnboardingType:
    status: str
    progress_pct: float
    pending_task_count: int
    pending_doc_count: int
    rejected_doc_count: int
    next_task_title: Optional[str]
    next_task_phase: Optional[str]


@strawberry.type
class FirstDayWizardType:
    should_show: bool
    has_seen_ai_onboarding: bool
    onboarding_incomplete: bool
    profile: FirstDayWizardProfileType
    onboarding: Optional[FirstDayWizardOnboardingType]
    steps: List[FirstDayWizardStepType]


@strawberry.type
class AiQuery:
    @strawberry.field
    def first_day_wizard(self, info: Info) -> FirstDayWizardType:
        from ai_engine.first_day import build_first_day_wizard

        request = info.context.request
        user = request.user
        if not user or not user.is_authenticated:
            from graphql import GraphQLError

            raise GraphQLError("Authentication required")

        user = (
            type(user)
            .objects.filter(id=user.id)
            .select_related(
                "organization",
                "department",
                "designation",
                "manager",
            )
            .first()
            or user
        )

        data = build_first_day_wizard(user)
        profile = data["profile"]
        ob = data.get("onboarding")
        return FirstDayWizardType(
            should_show=data["should_show"],
            has_seen_ai_onboarding=data["has_seen_ai_onboarding"],
            onboarding_incomplete=data["onboarding_incomplete"],
            profile=FirstDayWizardProfileType(
                first_name=profile.get("first_name") or "",
                full_name=profile.get("full_name") or "",
                role=profile.get("role") or "employee",
                department=profile.get("department"),
                designation=profile.get("designation"),
                organization=profile.get("organization"),
            ),
            onboarding=(
                FirstDayWizardOnboardingType(
                    status=ob["status"],
                    progress_pct=float(ob["progress_pct"] or 0),
                    pending_task_count=ob["pending_task_count"],
                    pending_doc_count=ob["pending_doc_count"],
                    rejected_doc_count=ob["rejected_doc_count"],
                    next_task_title=ob.get("next_task_title"),
                    next_task_phase=ob.get("next_task_phase"),
                )
                if ob
                else None
            ),
            steps=[
                FirstDayWizardStepType(
                    id=s["id"],
                    title=s["title"],
                    summary=s["summary"],
                    route=s.get("route"),
                    route_label=s.get("route_label"),
                    bullets=list(s.get("bullets") or []),
                )
                for s in data["steps"]
            ],
        )
