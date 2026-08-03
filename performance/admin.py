from django.contrib import admin
from .models import PerformanceCycle, Goal, PerformanceReview


@admin.register(PerformanceCycle)
class PerformanceCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "status", "start_date", "end_date")
    list_filter = ("status", "organization")


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "progress", "cycle")
    list_filter = ("status", "organization")


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "cycle", "reviewer", "status", "manager_score")
    list_filter = ("status", "organization")
