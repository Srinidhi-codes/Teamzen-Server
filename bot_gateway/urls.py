from django.urls import path

from bot_gateway.views import TelegramWebhookView

urlpatterns = [
    path("telegram/", TelegramWebhookView.as_view(), name="bot_telegram_webhook"),
]
