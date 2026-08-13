from django.contrib import admin

from documents.models import DocumentRequest, IssuedDocument


@admin.register(IssuedDocument)
class IssuedDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "user", "financial_year", "published_at", "visible_to_employee")
    list_filter = ("category", "visible_to_employee")
    search_fields = ("title", "user__email")


@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "user", "status", "due_at", "created_at")
    list_filter = ("status", "category")
    search_fields = ("title", "user__email")
