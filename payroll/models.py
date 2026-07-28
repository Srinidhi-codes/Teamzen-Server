from django.db import models
from django.conf import settings
from organizations.models import Organization
from cloudinary_storage.storage import RawMediaCloudinaryStorage

class SalaryComponent(models.Model):
    COMPONENT_TYPES = [
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
    ]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20) # e.g., BASIC, HRA, PF
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPES)
    is_taxable = models.BooleanField(default=True)
    is_statutory = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    
    class Meta:
        unique_together = ('organization', 'code')

    def __str__(self):
        return f"{self.name} ({self.code})"

class SalaryStructure(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class SalaryStructureComponent(models.Model):
    CALC_TYPES = [
        ('flat', 'Flat Amount'),
        ('percentage', 'Percentage of Base'),
    ]
    
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name='components')
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)
    calculation_type = models.CharField(max_length=20, choices=CALC_TYPES, default='flat')
    value = models.DecimalField(max_digits=12, decimal_places=2) # Could be amount or percentage
    base_component = models.ForeignKey(SalaryComponent, on_delete=models.SET_NULL, null=True, blank=True, related_name='derived_components')

    def __str__(self):
        return f"{self.salary_structure.name} - {self.component.name}"

class EmployeeSalaryStructure(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='salary_structures')
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE)
    annual_ctc = models.DecimalField(max_digits=15, decimal_places=2)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.salary_structure.name}"

class PayrollRun(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    month = models.IntegerField() # 1-12
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_gross = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_deduction = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_net_pay = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'month', 'year')

    def __str__(self):
        return f"Payroll {self.month}/{self.year} - {self.organization.name}"

class Payslip(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('paid', 'Paid'),
    ]
    
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Snapshot of employment details at time of payroll
    designation = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    
    worked_days = models.DecimalField(max_digits=4, decimal_places=1)
    lop_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    
    gross_earnings = models.DecimalField(max_digits=12, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payslip_pdf = models.FileField(upload_to='payslips/', null=True, blank=True, storage=RawMediaCloudinaryStorage())
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('payroll_run', 'user')

    def __str__(self):
        return f"Payslip {self.user.email} - {self.payroll_run.month}/{self.payroll_run.year}"

class PayslipComponent(models.Model):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='components')
    component_name = models.CharField(max_length=100)
    component_code = models.CharField(max_length=20)
    component_type = models.CharField(max_length=20) # Earning/Deduction
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.payslip} - {self.component_name}: {self.amount}"

class PayrollAdjustment(models.Model):
    ADJUSTMENT_TYPES = [
        ('earning', 'Addition'),
        ('deduction', 'Deduction'),
    ]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payroll_adjustments')
    month = models.IntegerField()
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    is_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.adjustment_type}: {self.amount} ({self.month}/{self.year})"


class SalaryAdvance(models.Model):
    """Admin-granted salary advance recovered via installments on subsequent payroll runs."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='salary_advances')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_advances',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    granted_on = models.DateField()
    installments_total = models.PositiveSmallIntegerField(default=1)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2)
    recovered_so_far = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-granted_on', '-id']

    def __str__(self):
        return f"Advance {self.user.email} ₹{self.amount} ({self.status})"
