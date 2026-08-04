from django.contrib import admin
from .models import Feedback, FeedbackAttachment


class FeedbackAttachmentInline(admin.TabularInline):
    model = FeedbackAttachment
    extra = 0


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "author", "category", "status", "visibility", "created_at")
    list_filter = ("status", "category", "visibility")
    search_fields = ("title", "message", "author__email")
    inlines = [FeedbackAttachmentInline]
