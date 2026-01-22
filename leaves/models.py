from django.db import models

# Create your models here.

from django.db import models
from django.utils import timezone
from users.models import CustomUser
from organizations.models import Organization

class LeaveType(models.Model):
    """Different types of leaves"""
    ACCRUAL_FREQ = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('onetime', 'One-time'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    max_days_per_year = models.IntegerField(default=10)
    carry_forward_allowed = models.BooleanField(default=False)
    carry_forward_max_days = models.IntegerField(default=0)
    accrual_frequency = models.CharField(max_length=20, choices=ACCRUAL_FREQ)
    accrual_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_paid_leave = models.BooleanField(default=False)
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    allow_encashment = models.BooleanField(default=False)
    encashment_rate = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    prorate_on_join = models.BooleanField(default=True)
    prorate_on_exit = models.BooleanField(default=True)
    proration_basis = models.CharField(
        max_length=20,
        choices=[
            ("daily", "Daily"),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('annually', 'Annually'),
        ],
        default="monthly"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'code')

    def __str__(self):
        return f"{self.name} ({self.code})"


class LeaveBalance(models.Model):
    """Track leave balance for each user"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    year = models.IntegerField()
    total_entitled = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    used = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pending_approval = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    carried_forward = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_accrued_date = models.DateField(null=True, blank=True)
    accrued = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    expired = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_locked = models.BooleanField(default=False) # Leaves freeze when user leaves the organization
    locked_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'leave_type', 'year')

    def get_available_balance(self):
        balance = self.total_entitled + self.carried_forward - self.used - self.pending_approval

        # apply carry forward cap
        max_cf = self.leave_type.carry_forward_max_days
        if self.carried_forward > max_cf:
            balance -= (self.carried_forward - max_cf)

        return max(balance, 0)

    def __str__(self):
        return f"{self.user} - {self.leave_type} ({self.year})"


class LeaveRequest(models.Model):
    """Leave request model"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    from_date = models.DateField()
    to_date = models.DateField()
    duration_days = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    approval_comments = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.leave_type} ({self.from_date})"


class CompanyHoliday(models.Model):
    """Company holidays"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    holiday_date = models.DateField()
    is_optional = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'holiday_date')

    def __str__(self):
        return f"{self.name} ({self.holiday_date})"