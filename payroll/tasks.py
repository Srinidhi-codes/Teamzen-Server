from celery import shared_task
from datetime import date
import logging

logger = logging.getLogger(__name__)


def _previous_month(today: date):
    if today.month == 1:
        return 12, today.year - 1
    return today.month - 1, today.year


@shared_task(name="payroll.tasks.auto_run_payroll_for_due_orgs")
def auto_run_payroll_for_due_orgs():
    """
    Daily Beat task: for pro/elite orgs with payroll_auto_enabled,
    on payroll_cycle_day create+process previous calendar month's run.
    Payslips remain draft — admin must publish/payout.
    """
    from organizations.models import Organization
    from payroll.models import PayrollRun
    from payroll.services import PayrollService
    from users.models import CustomUser
    from notifications.utils import notify_user

    today = date.today()
    month, year = _previous_month(today)

    orgs = Organization.objects.filter(
        is_active=True,
        plan__in=["pro", "elite"],
        payroll_auto_enabled=True,
        payroll_cycle_day=today.day,
    )

    processed = 0
    for org in orgs:
        try:
            existing = PayrollRun.objects.filter(
                organization=org, month=month, year=year
            ).first()
            if existing and existing.status == "completed":
                continue
            if existing and existing.status not in ("draft", "failed"):
                continue

            run = PayrollService.create_draft_run(org, month, year, processed_by=None)
            service = PayrollService()
            ok = service.process_payroll(run.id)
            if not ok:
                logger.error("Auto payroll failed for org=%s %s/%s", org.id, month, year)
                continue

            processed += 1
            admins = CustomUser.objects.filter(
                organization=org, role__in=["admin", "superadmin"], is_active=True
            )
            msg = (
                f"Automated payroll for {month}/{year} has been calculated. "
                f"Review payslips, then Publish and process Payouts."
            )
            for admin in admins:
                try:
                    notify_user(
                        recipient_id=admin.id,
                        verb="payroll_auto",
                        message=msg,
                        target_type="Payroll Run",
                        target_id=str(run.id),
                        level="admin",
                    )
                except Exception:
                    logger.exception("Notify admin failed user=%s", admin.id)
        except Exception:
            logger.exception("Auto payroll error org=%s", org.id)

    return {"processed": processed, "month": month, "year": year}
