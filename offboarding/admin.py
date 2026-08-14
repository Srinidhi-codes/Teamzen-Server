from django.contrib import admin

from offboarding.models import (
    EmployeeOffboarding,
    ExitInvite,
    ExitLetter,
    FnfSettlement,
    OffboardingTaskDefinition,
    OffboardingTaskInstance,
    OffboardingTemplate,
)


class TaskDefInline(admin.TabularInline):
    model = OffboardingTaskDefinition
    extra = 0


@admin.register(OffboardingTemplate)
class OffboardingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_default")
    inlines = [TaskDefInline]


@admin.register(EmployeeOffboarding)
class EmployeeOffboardingAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "status", "progress_pct", "exit_date")
    list_filter = ("status",)


@admin.register(OffboardingTaskInstance)
class OffboardingTaskInstanceAdmin(admin.ModelAdmin):
    list_display = ("title", "offboarding", "phase", "status", "assignee_role")


@admin.register(ExitInvite)
class ExitInviteAdmin(admin.ModelAdmin):
    list_display = ("offboarding", "expires_at", "created_at")


@admin.register(FnfSettlement)
class FnfSettlementAdmin(admin.ModelAdmin):
    list_display = ("offboarding", "status", "net_payable", "computed_at")


@admin.register(ExitLetter)
class ExitLetterAdmin(admin.ModelAdmin):
    list_display = ("letter_type", "offboarding", "status", "issued_at")
