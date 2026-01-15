from celery import shared_task
from leaves.services import perform_accrual
from leaves.models import LeaveBalance

@shared_task
def run_monthly_leave_accrual():
    balances = LeaveBalance.objects.filter(is_locked=False)
    for balance in balances:
        perform_accrual(balance)
