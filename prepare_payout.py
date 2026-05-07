
import os
import django
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from users.models import CustomUser
from payroll.models import Payslip, PayrollRun

def prepare_for_payout():
    # 1. Update employee with bank details
    employee = CustomUser.objects.get(id=2)
    employee.bank_account_number = '1234567890'
    employee.bank_ifsc_code = 'HDFC0001234'
    employee.save()
    print(f"Updated bank details for {employee.email}")

    # 2. Find the latest payroll run
    run = PayrollRun.objects.filter(month=5, year=2026).first()
    if not run:
        print("No payroll run found for May 2026")
        return

    # 3. Publish all payslips in this run
    count = Payslip.objects.filter(payroll_run=run).update(status='published')
    run.status = 'completed'
    run.save()
    
    print(f"Published {count} payslips for Run ID {run.id}. Ready for payout!")

if __name__ == "__main__":
    prepare_for_payout()
