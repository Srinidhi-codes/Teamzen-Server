from payroll.models import Payslip
for p in Payslip.objects.all():
    print(f'User: {p.user.email} | Status: {p.status} | Bank: {p.user.bank_account_number} | IFSC: {p.user.bank_ifsc_code}')
