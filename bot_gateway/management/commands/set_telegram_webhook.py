from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from bot_gateway.adapters import telegram_api


class Command(BaseCommand):
    help = "Register or clear the Telegram webhook for Teamzen bot_gateway"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            default="",
            help="Full public webhook URL, e.g. https://api.example.com/api/bot/telegram/",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete the current webhook (useful for local polling tests)",
        )
        parser.add_argument(
            "--base-url",
            type=str,
            default="",
            help="Public API base (e.g. https://api.example.com). Appends /api/bot/telegram/",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
            raise CommandError("TELEGRAM_BOT_TOKEN is not set")

        if options["delete"]:
            result = telegram_api.delete_webhook()
            self.stdout.write(self.style.SUCCESS(f"deleteWebhook → {result}"))
            return

        url = options["url"]
        if not url and options["base_url"]:
            base = options["base_url"].rstrip("/")
            url = f"{base}/api/bot/telegram/"
        if not url:
            raise CommandError("Provide --url or --base-url")

        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
        result = telegram_api.set_webhook(url, secret_token=secret)
        if not result.get("ok"):
            raise CommandError(f"setWebhook failed: {result}")
        self.stdout.write(self.style.SUCCESS(f"Webhook set to {url}"))
        self.stdout.write(str(result))
