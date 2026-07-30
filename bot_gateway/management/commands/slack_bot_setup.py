"""
Document required Slack app configuration for Teamzen bot gateway.

Usage:
  python manage.py slack_bot_setup
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print Slack app scopes and webhook URL guidance for Sequence 6"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Teamzen Slack bot setup"))
        self.stdout.write("")
        self.stdout.write("Request URL (Events / Slash / Interactivity):")
        self.stdout.write("  https://<your-api-host>/api/bot/slack/")
        self.stdout.write("")
        self.stdout.write("Bot token scopes:")
        for scope in (
            "chat:write",
            "commands",
            "im:history",
            "im:read",
            "users:read",
            "app_mentions:read",
        ):
            self.stdout.write(f"  - {scope}")
        self.stdout.write("")
        self.stdout.write("Subscribe to bot events: message.im, app_mention")
        self.stdout.write("Slash commands: /teamzen, /leaves, /checkin, /checkout, /payslip, /balance")
        self.stdout.write("")
        self.stdout.write("Env: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET")
