"""
Document required Meta WhatsApp Cloud API setup for Teamzen bot gateway.

Usage:
  python manage.py whatsapp_bot_setup
"""

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print WhatsApp Cloud API env and webhook guidance"

    def handle(self, *args, **options):
        configured = bool(
            (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip()
            and (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
        )
        verify = (getattr(settings, "WHATSAPP_VERIFY_TOKEN", "") or "").strip() or "(not set)"

        self.stdout.write(self.style.NOTICE("Teamzen WhatsApp bot setup (Meta Cloud API)"))
        self.stdout.write("")
        self.stdout.write(f"Configured: {configured}")
        self.stdout.write(f"Verify token: {verify}")
        self.stdout.write("")
        self.stdout.write("1. Create app at https://developers.facebook.com/")
        self.stdout.write("2. Add WhatsApp product -> API Setup")
        self.stdout.write("3. Copy Phone number ID + Access token + App Secret")
        self.stdout.write("4. Allowlist your personal WhatsApp number for sandbox")
        self.stdout.write("5. Expose Django with HTTPS (ngrok / Cloudflare Tunnel / deploy)")
        self.stdout.write("")
        self.stdout.write("Webhook callback URL:")
        self.stdout.write("  https://<your-api-host>/api/bot/whatsapp/")
        self.stdout.write("Verify token: same as WHATSAPP_VERIFY_TOKEN in .env")
        self.stdout.write("Subscribe to field: messages")
        self.stdout.write("")
        self.stdout.write("Env vars:")
        for key in (
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_APP_SECRET",
            "WHATSAPP_API_VERSION",
        ):
            present = bool((getattr(settings, key, "") or "").strip())
            self.stdout.write(f"  - {key}: {'set' if present else 'MISSING'}")
        self.stdout.write("")
        self.stdout.write("Health check: GET /api/bot/whatsapp/")
