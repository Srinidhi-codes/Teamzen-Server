from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from users.models import CustomUser
from leaves.models import LeaveType, LeaveBalance
from leaves.services import calculate_initial_entitlement

@receiver(post_save, sender=CustomUser)
def create_leave_balances_for_user(sender, instance, created, **kwargs):
    if not created:
        return

    current_year = timezone.now().year
    leave_types = LeaveType.objects.filter(is_active=True)

    for lt in leave_types:
        entitlement = calculate_initial_entitlement(instance, lt, current_year)

        LeaveBalance.objects.get_or_create(
            user=instance,
            leave_type=lt,
            year=current_year,
            defaults={
                "total_entitled": entitlement,
                "used": 0,
                "pending_approval": 0,
                "carried_forward": 0,
                "accrued": entitlement if lt.accrual_frequency == "onetime" else 0,
                "expired": 0
            }
        )
