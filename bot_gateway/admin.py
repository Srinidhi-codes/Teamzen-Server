from django.contrib import admin

from bot_gateway.models import BotSession


@admin.register(BotSession)
class BotSessionAdmin(admin.ModelAdmin):
    list_display = (
        "platform",
        "chat_id",
        "user",
        "auth_state",
        "is_verified",
        "expires_at",
        "updated_at",
    )
    list_filter = ("platform", "auth_state", "is_verified")
    search_fields = ("chat_id", "pending_identity", "user__email", "user__first_name")
    raw_id_fields = ("user",)
