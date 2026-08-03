from django.test import SimpleTestCase, override_settings
from django.test import Client

from bot_gateway.formatters import format_for_bot, format_for_platform
from bot_gateway.models import BotSession


class FormatterTests(SimpleTestCase):
    def test_balance_card(self):
        raw = (
            "[BALANCE_CARD] Name: Casual Leave | Total: 10.0 | Used: 1.5 | "
            "Pending: 1.0 | Available: 7.5 [/BALANCE_CARD]"
        )
        out = format_for_bot(raw)
        self.assertIn("Casual Leave", out)
        self.assertIn("7.5", out)
        self.assertNotIn("BALANCE_CARD", out)

    def test_payroll_card(self):
        raw = (
            "[PAYROLL_CARD] month: May | year: 2026 | gross: 35000 | "
            "net: 34800 | deductions: 200 [/PAYROLL_CARD]"
        )
        out = format_for_bot(raw)
        self.assertIn("Payslip", out)
        self.assertIn("34800", out)

    def test_format_for_whatsapp(self):
        out = format_for_platform("<b>Hello</b> world", BotSession.PLATFORM_WHATSAPP)
        self.assertIn("*Hello*", out)
        self.assertNotIn("<b>", out)


class WhatsAppAdapterTests(SimpleTestCase):
    def test_normalize_chat_id(self):
        from bot_gateway.adapters import whatsapp_api

        self.assertEqual(whatsapp_api.normalize_chat_id("+91 98765-43210"), "919876543210")
        self.assertEqual(whatsapp_api.normalize_chat_id("919876543210"), "919876543210")

    @override_settings(WHATSAPP_APP_SECRET="testsecret", DEBUG=False)
    def test_verify_signature_ok(self):
        import hashlib
        import hmac

        from bot_gateway.adapters import whatsapp_api

        body = b'{"object":"whatsapp_business_account"}'
        sig = "sha256=" + hmac.new(b"testsecret", body, hashlib.sha256).hexdigest()
        self.assertTrue(whatsapp_api.verify_signature(body, sig))

    @override_settings(WHATSAPP_APP_SECRET="testsecret", DEBUG=False)
    def test_verify_signature_bad(self):
        from bot_gateway.adapters import whatsapp_api

        self.assertFalse(whatsapp_api.verify_signature(b"{}", "sha256=deadbeef"))

    def test_leave_approval_keyboard_shape(self):
        from bot_gateway.adapters import whatsapp_api

        kb = whatsapp_api.leave_approval_keyboard(42)
        buttons = kb["interactive"]["action"]["buttons"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["reply"]["id"], "lv:42:a")
        self.assertEqual(buttons[1]["reply"]["id"], "lv:42:r")

    def test_registry_returns_whatsapp(self):
        from bot_gateway.adapters.registry import get_adapter
        from bot_gateway.adapters import whatsapp_api

        self.assertIs(get_adapter(BotSession.PLATFORM_WHATSAPP), whatsapp_api)


class WhatsAppWebhookTests(SimpleTestCase):
    def test_health_get(self):
        client = Client()
        resp = client.get("/api/bot/whatsapp/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["service"], "teamzen-whatsapp-bot")

    @override_settings(WHATSAPP_VERIFY_TOKEN="teamzen_wa_verify_test")
    def test_hub_challenge(self):
        client = Client()
        resp = client.get(
            "/api/bot/whatsapp/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "teamzen_wa_verify_test",
                "hub.challenge": "12345challenge",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), "12345challenge")

    @override_settings(WHATSAPP_VERIFY_TOKEN="teamzen_wa_verify_test")
    def test_hub_challenge_wrong_token(self):
        client = Client()
        resp = client.get(
            "/api/bot/whatsapp/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "12345challenge",
            },
        )
        self.assertEqual(resp.status_code, 403)
