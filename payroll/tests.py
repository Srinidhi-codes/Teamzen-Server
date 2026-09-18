from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from organizations.models import Organization
from payroll.api_views import _match_uploaded_payslips
from payroll.models import PayrollRun, Payslip
from payroll.services import PayrollService
from payroll.standard_payslip_layouts import render_standard_payslip
from payroll.template_services import build_demo_payslip_mock


User = get_user_model()


class PayslipFilenameMatchingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Test Payroll Co",
            headquarters_address="1 Test Street",
        )
        self.admin = User.objects.create_user(
            username="payroll-admin",
            email="payroll-admin@example.com",
            password="test-password",
            role="admin",
            organization=self.org,
        )
        self.run = PayrollRun.objects.create(
            organization=self.org,
            month=3,
            year=2026,
            status="completed",
            processed_by=self.admin,
        )

    def make_payslip(self, employee_id, first_name, last_name, suffix):
        user = User.objects.create_user(
            username=f"employee-{suffix}",
            email=f"employee-{suffix}@example.com",
            password="test-password",
            role="employee",
            organization=self.org,
            employee_id=employee_id,
            first_name=first_name,
            last_name=last_name,
        )
        return Payslip.objects.create(
            payroll_run=self.run,
            user=user,
            worked_days=Decimal("22"),
            gross_earnings=Decimal("50000"),
            total_deductions=Decimal("5000"),
            net_pay=Decimal("45000"),
        )

    def pdf(self, name):
        return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")

    def test_employee_id_match_takes_priority(self):
        payslip = self.make_payslip("EMP-001", "Aanya", "Sharma", "one")
        result = _match_uploaded_payslips(
            self.run, [self.pdf("March_EMP-001_Aanya_Sharma.pdf")]
        )

        self.assertTrue(result[0]["matched"])
        self.assertEqual(result[0]["matchBy"], "employee_id")
        self.assertEqual(result[0]["payslipId"], str(payslip.id))

    def test_unique_full_name_matches_but_duplicate_name_does_not(self):
        unique = self.make_payslip("EMP-002", "Ravi", "Kumar", "two")
        self.make_payslip("EMP-003", "John", "Smith", "three")
        self.make_payslip("EMP-004", "John", "Smith", "four")

        result = _match_uploaded_payslips(
            self.run,
            [self.pdf("Ravi_Kumar_March.pdf"), self.pdf("John_Smith_March.pdf")],
        )

        self.assertEqual(result[0]["payslipId"], str(unique.id))
        self.assertEqual(result[0]["matchBy"], "name")
        self.assertFalse(result[1]["matched"])

    def test_standard_layouts_render_as_distinct_pdfs(self):
        mock = build_demo_payslip_mock(self.org)
        rendered = [
            render_standard_payslip(mock, layout, {})
            for layout in ("classic", "compact", "minimal")
        ]

        self.assertTrue(all(pdf.startswith(b"%PDF") for pdf in rendered))
        self.assertEqual(len(set(rendered)), 3)

    def test_publish_keeps_uploaded_pdfs(self):
        from unittest.mock import patch

        uploaded = self.make_payslip("EMP-010", "Neha", "Iyer", "upload")
        uploaded.payslip_pdf.name = "media/payslips/neha.pdf"
        uploaded.pdf_source = "uploaded"
        uploaded.save(update_fields=["payslip_pdf", "pdf_source"])
        generated = self.make_payslip("EMP-011", "Arun", "Mehta", "generated")

        with patch.object(PayrollService, "generate_payslip_pdf") as generate:
            PayrollService.publish_run_pdfs(self.run)

        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[0].id, generated.id)
        uploaded.refresh_from_db()
        generated.refresh_from_db()
        self.assertEqual(uploaded.status, "published")
        self.assertEqual(generated.status, "published")
        self.assertEqual(uploaded.pdf_source, "uploaded")
        self.assertTrue(uploaded.payslip_pdf)
