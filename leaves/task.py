from celery import shared_task
from leaves.services import run_monthly_accrual, run_carry_forward

@shared_task
def run_monthly_leave_accrual():
    """
    Monthly scheduled task to run leave accruals.
    """
    run_monthly_accrual()

@shared_task
def run_yearly_carry_forward():
    """
    Yearly task to process carry forward balances.
    """
    run_carry_forward()
