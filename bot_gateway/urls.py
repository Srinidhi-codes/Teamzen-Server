from django.urls import path

from bot_gateway.views import SlackWebhookView, TelegramWebhookView, WhatsAppWebhookView

# Register with and without trailing slash — Slack often omits the slash;
# Django's APPEND_SLASH 301 on POST breaks slash commands ("app did not respond").
_slack = SlackWebhookView.as_view()
_telegram = TelegramWebhookView.as_view()
_whatsapp = WhatsAppWebhookView.as_view()

urlpatterns = [
    path("telegram/", _telegram, name="bot_telegram_webhook"),
    path("telegram", _telegram),
    path("slack/", _slack, name="bot_slack_webhook"),
    path("slack", _slack),
    path("whatsapp/", _whatsapp, name="bot_whatsapp_webhook"),
    path("whatsapp", _whatsapp),
]
