import strawberry
from typing import Optional, List
from strawberry.types import Info

from performance.auth import require_performance_access, resolve_perf_org
from performance.models import PerformanceCycle, Goal, PerformanceReview
from performance.graphql.types import (
    PerformanceCycleType,
    GoalType,
    PerformanceReviewType,
    CycleInput,
    UpdateCycleInput,
    GoalInput,
    UpdateGoalInput,
    ReviewInput,
    UpdateReviewInput,
)
from performance.graphql.queries import _cycle_type, _goal_type, _review_type
from users.models import CustomUser


@strawberry.type
class PerformanceMutation:
    @strawberry.mutation
    def create_performance_cycle(self, info: Info, input: CycleInput) -> PerformanceCycleType:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        if user.role not in ("superadmin", "admin", "hr"):
            raise Exception("Only admin/HR can create cycles")
        org = resolve_perf_org(user, input.organization_id)
        cycle = PerformanceCycle.objects.create(
            organization=org,
            name=input.name,
            description=input.description or "",
            start_date=input.start_date,
            end_date=input.end_date,
            status=input.status or "draft",
            created_by=user,
        )
        return _cycle_type(cycle)

    @strawberry.mutation
    def update_performance_cycle(
        self, info: Info, input: UpdateCycleInput
    ) -> PerformanceCycleType:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        if user.role not in ("superadmin", "admin", "hr"):
            raise Exception("Only admin/HR can update cycles")
        cycle = PerformanceCycle.objects.get(id=input.id)
        if user.role != "superadmin" and cycle.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        for field in ("name", "description", "start_date", "end_date", "status"):
            val = getattr(input, field)
            if val is not None:
                setattr(cycle, field, val)
        cycle.save()
        return _cycle_type(cycle)

    @strawberry.mutation
    def delete_performance_cycle(self, info: Info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        if user.role not in ("superadmin", "admin", "hr"):
            raise Exception("Unauthorized")
        cycle = PerformanceCycle.objects.get(id=id)
        if user.role != "superadmin" and cycle.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        cycle.delete()
        return True

    @strawberry.mutation
    def create_goal(self, info: Info, input: GoalInput) -> GoalType:
        user = info.context.request.user
        require_performance_access(user)
        org = resolve_perf_org(user, input.organization_id)
        if not input.user_id and user.role in ("superadmin", "admin", "hr", "manager"):
            raise Exception("Select an employee for this goal")
        target_user_id = input.user_id or user.id
        if str(target_user_id) != str(user.id) and user.role not in (
            "superadmin",
            "admin",
            "hr",
            "manager",
        ):
            raise Exception("Unauthorized")
        target = CustomUser.objects.filter(id=target_user_id, organization=org).first()
        if not target:
            raise Exception("Employee not found")
        if target.role in ("admin", "superadmin"):
            raise Exception("Cannot assign goals to organization admins")
        if user.role == "manager" and str(target_user_id) != str(user.id):
            if not CustomUser.objects.filter(id=target_user_id, manager=user).exists():
                raise Exception("Unauthorized")
        cycle = None
        if input.cycle_id:
            cycle = PerformanceCycle.objects.get(id=input.cycle_id, organization=org)
        goal = Goal.objects.create(
            organization=org,
            user_id=target_user_id,
            cycle=cycle,
            title=input.title,
            description=input.description or "",
            target=input.target or "",
            progress=min(100, max(0, input.progress or 0)),
            status=input.status or "not_started",
            due_date=input.due_date,
        )
        return _goal_type(goal)

    @strawberry.mutation
    def update_goal(self, info: Info, input: UpdateGoalInput) -> GoalType:
        user = info.context.request.user
        require_performance_access(user)
        goal = Goal.objects.select_related("user").get(id=input.id)
        can_edit = (
            str(goal.user_id) == str(user.id)
            or user.role in ("superadmin", "admin", "hr")
            or (user.role == "manager" and goal.user.manager_id == user.id)
        )
        if not can_edit:
            raise Exception("Unauthorized")
        for field in ("title", "description", "target", "status", "due_date"):
            val = getattr(input, field)
            if val is not None:
                setattr(goal, field, val)
        if input.progress is not None:
            goal.progress = min(100, max(0, input.progress))
        goal.save()
        return _goal_type(goal)

    @strawberry.mutation
    def delete_goal(self, info: Info, id: strawberry.ID) -> bool:
        user = info.context.request.user
        require_performance_access(user)
        goal = Goal.objects.select_related("user").get(id=id)
        can_edit = (
            str(goal.user_id) == str(user.id)
            or user.role in ("superadmin", "admin", "hr")
            or (user.role == "manager" and goal.user.manager_id == user.id)
        )
        if not can_edit:
            raise Exception("Unauthorized")
        goal.delete()
        return True

    @strawberry.mutation
    def create_performance_review(
        self, info: Info, input: ReviewInput
    ) -> PerformanceReviewType:
        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        if user.role not in ("superadmin", "admin", "hr", "manager"):
            raise Exception("Unauthorized")
        org = resolve_perf_org(user, input.organization_id)
        cycle = PerformanceCycle.objects.get(id=input.cycle_id, organization=org)
        reviewer_id = input.reviewer_id or user.id
        review, _ = PerformanceReview.objects.get_or_create(
            cycle=cycle,
            employee_id=input.employee_id,
            defaults={
                "organization": org,
                "reviewer_id": reviewer_id,
                "status": "pending",
            },
        )
        return _review_type(review)

    @strawberry.mutation
    def update_performance_review(
        self, info: Info, input: UpdateReviewInput
    ) -> PerformanceReviewType:
        user = info.context.request.user
        require_performance_access(user)
        review = PerformanceReview.objects.select_related(
            "employee", "reviewer", "cycle"
        ).get(id=input.id)

        is_employee = str(review.employee_id) == str(user.id)
        is_reviewer = review.reviewer_id and str(review.reviewer_id) == str(user.id)
        is_admin = user.role in ("superadmin", "admin", "hr")
        is_manager = user.role == "manager" and (
            review.employee.manager_id == user.id or is_reviewer
        )

        if not (is_employee or is_reviewer or is_admin or is_manager):
            raise Exception("Unauthorized")

        # Reviewee (e.g. Arjun): self-assessment only — cannot rate their manager
        if is_employee and not is_admin and not (is_reviewer or is_manager):
            if input.self_score is not None:
                review.self_score = input.self_score
            if input.self_comments is not None:
                review.self_comments = input.self_comments
            if input.status == "self_submitted":
                review.status = "self_submitted"
        # Reviewer / reporting manager (e.g. Sandhya on Arjun): manager feedback only
        elif (is_reviewer or is_manager) and not is_employee and not is_admin:
            if input.manager_score is not None:
                review.manager_score = input.manager_score
            if input.manager_comments is not None:
                review.manager_comments = input.manager_comments
            if input.status == "completed":
                review.status = "completed"
        else:
            # Admin/HR (or dual role) can update all fields
            if input.self_score is not None:
                review.self_score = input.self_score
            if input.manager_score is not None:
                review.manager_score = input.manager_score
            if input.self_comments is not None:
                review.self_comments = input.self_comments
            if input.manager_comments is not None:
                review.manager_comments = input.manager_comments
            if input.status is not None:
                review.status = input.status
            if input.reviewer_id is not None:
                review.reviewer_id = input.reviewer_id

        review.save()
        return _review_type(review)

    @strawberry.mutation
    def seed_cycle_reviews(
        self, info: Info, cycle_id: strawberry.ID
    ) -> List[PerformanceReviewType]:
        """Create pending reviews for all active employees in the cycle's org."""
        from typing import List as TypingList

        user = info.context.request.user
        require_performance_access(user, allow_employee=False)
        if user.role not in ("superadmin", "admin", "hr"):
            raise Exception("Unauthorized")
        cycle = PerformanceCycle.objects.select_related("organization").get(id=cycle_id)
        if user.role != "superadmin" and cycle.organization_id != user.organization_id:
            raise Exception("Unauthorized")
        employees = CustomUser.objects.filter(
            organization=cycle.organization,
            is_active=True,
            role="employee",
        )
        created = []
        for emp in employees:
            # Manager reviews the employee — never self as reviewer
            reviewer = emp.manager if emp.manager_id and emp.manager_id != emp.id else None
            review, _ = PerformanceReview.objects.get_or_create(
                cycle=cycle,
                employee=emp,
                defaults={
                    "organization": cycle.organization,
                    "reviewer": reviewer,
                    "status": "pending",
                },
            )
            created.append(_review_type(review))
        return created
