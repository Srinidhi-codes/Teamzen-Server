from django.test import SimpleTestCase

from bot_gateway.formatters import format_for_bot


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
