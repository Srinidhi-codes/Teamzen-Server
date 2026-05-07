
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payroll.models import Payslip
from payroll.services import PayrollService

def regenerate_payslips():
    payslips = Payslip.objects.all()
    for p in payslips:
        print(f"Regenerating PDF for Payslip ID: {p.id}")
        PayrollService.generate_payslip_pdf(p)
        p.refresh_from_db()
        print(f"New Path: {p.payslip_pdf.name}")
        print(f"New URL: {p.payslip_pdf.url}")

if __name__ == "__main__":
    regenerate_payslips()
