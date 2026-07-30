from django.urls import path

from bot_gateway.views import SlackWebhookView, TelegramWebhookView

urlpatterns = [
    path("telegram/", TelegramWebhookView.as_view(), name="bot_telegram_webhook"),
    path("slack/", SlackWebhookView.as_view(), name="bot_slack_webhook"),
]
