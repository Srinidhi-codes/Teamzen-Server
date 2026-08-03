from django.db import models
from django.conf import settings
from organizations.models import Organization


class PerformanceCycle(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("closed", "Closed"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="performance_cycles"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_performance_cycles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class Goal(models.Model):
    STATUS_CHOICES = [
        ("not_started", "Not started"),
        ("in_progress", "In progress"),
        ("at_risk", "At risk"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="goals"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    cycle = models.ForeignKey(
        PerformanceCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goals",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target = models.CharField(max_length=255, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)  # 0-100
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} — {self.user}"


class PerformanceReview(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("self_submitted", "Self submitted"),
        ("completed", "Completed"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="performance_reviews"
    )
    cycle = models.ForeignKey(
        PerformanceCycle, on_delete=models.CASCADE, related_name="reviews"
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="performance_reviews_as_employee",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performance_reviews_as_reviewer",
    )
    self_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    manager_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    self_comments = models.TextField(blank=True)
    manager_comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ("cycle", "employee")

    def __str__(self):
        return f"Review {self.employee} @ {self.cycle.name}"
