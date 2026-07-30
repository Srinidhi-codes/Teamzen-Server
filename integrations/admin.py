from django.contrib import admin

from integrations.models import GoogleCalendarConnection


@admin.register(GoogleCalendarConnection)
class GoogleCalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "calendar_id", "connected_at", "updated_at")
    search_fields = ("user__email", "user__first_name")
    readonly_fields = ("connected_at", "updated_at")
