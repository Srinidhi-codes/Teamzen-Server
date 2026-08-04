from django.contrib import admin

from onboarding.models import (
    DocumentLetterTemplate,
    EmployeeDocument,
    EmployeeOnboarding,
    OnboardingTaskDefinition,
    OnboardingTaskInstance,
    OnboardingTemplate,
    OfferLetter,
    PreboardingInvite,
)


class OnboardingTaskDefinitionInline(admin.TabularInline):
    model = OnboardingTaskDefinition
    extra = 0


@admin.register(OnboardingTemplate)
class OnboardingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_default", "employment_type")
    list_filter = ("is_default", "organization")
    inlines = [OnboardingTaskDefinitionInline]


@admin.register(EmployeeOnboarding)
class EmployeeOnboardingAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "status", "progress_pct", "join_date")
    list_filter = ("status", "organization")
    search_fields = ("user__email", "user__first_name", "user__last_name")


@admin.register(OnboardingTaskInstance)
class OnboardingTaskInstanceAdmin(admin.ModelAdmin):
    list_display = ("title", "onboarding", "assignee_role", "status", "due_at")
    list_filter = ("status", "phase", "assignee_role")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "verification_status", "created_at")
    list_filter = ("category", "verification_status")


@admin.register(DocumentLetterTemplate)
class DocumentLetterTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "letter_type", "is_default")
    list_filter = ("letter_type", "is_default")


@admin.register(OfferLetter)
class OfferLetterAdmin(admin.ModelAdmin):
    list_display = ("onboarding", "status", "accepted_at")
    list_filter = ("status",)


@admin.register(PreboardingInvite)
class PreboardingInviteAdmin(admin.ModelAdmin):
    list_display = ("onboarding", "expires_at", "used_at", "created_at")
