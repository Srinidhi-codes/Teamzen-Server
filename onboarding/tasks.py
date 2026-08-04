"""Celery tasks for onboarding nudges."""

from celery import shared_task
from django.utils import timezone


@shared_task(name="onboarding.tasks.nudge_overdue_onboarding_tasks")
def nudge_overdue_onboarding_tasks():
    """Notify assignees about overdue onboarding tasks (daily)."""
    from onboarding.models import OnboardingTaskInstance
    from notifications.utils import notify_user

    today = timezone.localdate()
    tasks = (
        OnboardingTaskInstance.objects.filter(
            status__in=["pending", "in_progress"],
            due_at__lt=today,
            onboarding__status__in=["preboarding", "in_progress"],
        )
        .exclude(assignee_id=None)
        .select_related("assignee", "onboarding", "onboarding__user")[:200]
    )

    notified = 0
    for task in tasks:
        hire = task.onboarding.user
        hire_name = f"{hire.first_name} {hire.last_name}".strip() or hire.email
        days = (today - task.due_at).days if task.due_at else 0
        try:
            notify_user(
                recipient_id=task.assignee_id,
                verb="Overdue onboarding task",
                message=(
                    f'"{task.title}" for {hire_name} is {days} day(s) overdue. '
                    f"Please complete it in Onboarding."
                ),
                target_type="Onboarding",
                target_id=str(task.onboarding_id),
                level="admin" if task.assignee_role != "hire" else "personal",
            )
            notified += 1
        except Exception:
            continue
    return f"Nudged {notified} overdue onboarding tasks"
