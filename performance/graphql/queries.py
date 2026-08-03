import strawberry
from typing import Optional, List
from collections import defaultdict
from django.db.models import Count, Q, Avg

from performance.auth import require_performance_access, resolve_perf_org
from performance.models import PerformanceCycle, Goal, PerformanceReview
from performance.graphql.types import (
    PerformanceCycleType,
    GoalType,
    PerformanceReviewType,
    PerformanceOverviewType,
    NamedCountType,
)


def _cycle_type(c: PerformanceCycle) -> PerformanceCycleType:
    reviews = c.reviews.all()
    completed = reviews.filter(status="completed").count()
    return PerformanceCycleType(
        id=str(c.id),
        name=c.name,
        description=c.description or "",
        start_date=c.start_date,
        end_date=c.end_date,
        status=c.status,
        organization_id=str(c.organization_id),
        review_count=reviews.count(),
        completed_reviews=completed,
        goal_count=c.goals.count(),
    )


def _goal_type(g: Goal) -> GoalType:
    return GoalType(
        id=str(g.id),
        title=g.title,
        description=g.description or "",
        target=g.target or "",
        progress=g.progress,
        status=g.status,
        due_date=g.due_date,
        user_id=str(g.user_id),
        user_name=f"{g.user.first_name} {g.user.last_name}".strip() or g.user.email,
        department=g.user.department.name if g.user.department_id else None,
        cycle_id=str(g.cycle_id) if g.cycle_id else None,
        cycle_name=g.cycle.name if g.cycle_id else None,
    )


def _review_type(r: PerformanceReview) -> PerformanceReviewType:
    return PerformanceReviewType(
        id=str(r.id),
        cycle_id=str(r.cycle_id),
        cycle_name=r.cycle.name,
        employee_id=str(r.employee_id),
        employee_name=f"{r.employee.first_name} {r.employee.last_name}".strip()
        or r.employee.email,
        reviewer_id=str(r.reviewer_id) if r.reviewer_id else None,
        reviewer_name=(
            f"{r.reviewer.first_name} {r.reviewer.last_name}".strip()
            if r.reviewer_id
            else None
        ),
        self_score=float(r.self_score) if r.self_score is not None else None,
        manager_score=float(r.manager_score) if r.manager_score is not None else None,
        self_comments=r.self_comments or "",
        manager_comments=r.manager_comments or "",
        status=r.status,
        department=r.employee.department.name if r.employee.department_id else None,
    )


def _scope_goals(qs, user):
    if user.role in ("superadmin", "admin", "hr"):
        return qs
    if user.role == "manager":
        return qs.filter(Q(user=user) | Q(user__manager=user))
    return qs.filter(user=user)


def _scope_reviews(qs, user):
    if user.role in ("superadmin", "admin", "hr"):
        return qs
    if user.role == "manager":
        return qs.filter(
            Q(employee=user) | Q(employee__manager=user) | Q(reviewer=user)
        )
    return qs.filter(employee=user)


@strawberry.type
class PerformanceQuery:
    @strawberry.field
    def performance_cycles(
        self,
        info,
        organization_id: Optional[strawberry.ID] = None,
        status: Optional[str] = None,
    ) -> List[PerformanceCycleType]:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        org = resolve_perf_org(user, organization_id)
        qs = PerformanceCycle.objects.filter(organization=org).prefetch_related(
            "reviews", "goals"
        )
        if status:
            qs = qs.filter(status=status)
        return [_cycle_type(c) for c in qs]

    @strawberry.field
    def performance_goals(
        self,
        info,
        organization_id: Optional[strawberry.ID] = None,
        cycle_id: Optional[strawberry.ID] = None,
        user_id: Optional[strawberry.ID] = None,
        search: Optional[str] = None,
    ) -> List[GoalType]:
        user = info.context.request.user
        require_performance_access(user)
        org = resolve_perf_org(user, organization_id)
        qs = Goal.objects.filter(organization=org).select_related(
            "user", "user__department", "cycle"
        ).exclude(user__role__in=["admin", "superadmin"])
        qs = _scope_goals(qs, user)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        if user_id and user.role in ("superadmin", "admin", "hr", "manager"):
            qs = qs.filter(user_id=user_id)
        if search:
            qs = qs.filter(title__icontains=search)
        return [_goal_type(g) for g in qs]

    @strawberry.field
    def performance_reviews(
        self,
        info,
        organization_id: Optional[strawberry.ID] = None,
        cycle_id: Optional[strawberry.ID] = None,
        status: Optional[str] = None,
    ) -> List[PerformanceReviewType]:
        user = info.context.request.user
        require_performance_access(user)
        org = resolve_perf_org(user, organization_id)
        qs = PerformanceReview.objects.filter(organization=org).select_related(
            "cycle", "employee", "employee__department", "reviewer"
        ).exclude(employee__role__in=["admin", "superadmin"])
        qs = _scope_reviews(qs, user)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        if status:
            qs = qs.filter(status=status)
        return [_review_type(r) for r in qs]

    @strawberry.field
    def performance_overview(
        self, info, organization_id: Optional[strawberry.ID] = None
    ) -> PerformanceOverviewType:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        org = resolve_perf_org(user, organization_id)

        cycles = PerformanceCycle.objects.filter(organization=org)
        reviews = PerformanceReview.objects.filter(organization=org).exclude(
            employee__role__in=["admin", "superadmin"]
        )
        goals = Goal.objects.filter(organization=org).exclude(
            user__role__in=["admin", "superadmin"]
        ).select_related("user", "user__department")

        if user.role == "manager":
            reviews = _scope_reviews(reviews, user)
            goals = _scope_goals(goals, user)

        pending = reviews.filter(status__in=["pending", "self_submitted"]).count()
        completed = reviews.filter(status="completed").count()
        total_reviews = reviews.count()
        completion = round((completed / total_reviews) * 100, 1) if total_reviews else 0.0

        on_track = goals.filter(status="in_progress", progress__gte=50).count() + goals.filter(
            status="completed"
        ).count()
        at_risk = goals.filter(status="at_risk").count()
        g_completed = goals.filter(status="completed").count()

        # Rating distribution (manager scores buckets)
        dist = defaultdict(int)
        for score in reviews.filter(manager_score__isnull=False).values_list(
            "manager_score", flat=True
        ):
            s = float(score)
            if s >= 4.5:
                dist["Excellent (4.5+)"] += 1
            elif s >= 3.5:
                dist["Good (3.5–4.4)"] += 1
            elif s >= 2.5:
                dist["Average (2.5–3.4)"] += 1
            else:
                dist["Needs improvement (<2.5)"] += 1
        rating_distribution = [
            NamedCountType(name=k, value=float(v)) for k, v in dist.items()
        ]

        dept_map = defaultdict(lambda: {"done": 0, "total": 0})
        for g in goals:
            dept = g.user.department.name if g.user.department_id else "Unassigned"
            dept_map[dept]["total"] += 1
            if g.status == "completed" or g.progress >= 80:
                dept_map[dept]["done"] += 1
        goal_by_department = [
            NamedCountType(
                name=n,
                value=round((v["done"] / v["total"]) * 100, 1) if v["total"] else 0.0,
            )
            for n, v in sorted(dept_map.items())
        ]

        return PerformanceOverviewType(
            active_cycles=cycles.filter(status="active").count(),
            pending_reviews=pending,
            completed_reviews=completed,
            completion_rate=completion,
            goals_total=goals.count(),
            goals_on_track=on_track,
            goals_at_risk=at_risk,
            goals_completed=g_completed,
            rating_distribution=rating_distribution,
            goal_by_department=goal_by_department,
        )
