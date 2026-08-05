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

class EmployeeComponentOverride(models.Model):
    """Per-employee override for a salary component.
    Allows including/excluding specific components or changing their value."""

    employee_salary = models.ForeignKey(
        EmployeeSalaryStructure, on_delete=models.CASCADE, related_name='component_overrides'
    )
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)
    is_excluded = models.BooleanField(default=False, help_text='If True, this component is skipped for this employee')
    override_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Custom flat amount. If null, uses the structure default.'
    )

    class Meta:
        unique_together = ('employee_salary', 'component')

    def __str__(self):
        return f"{self.employee_salary.user.email} - {self.component.name} ({'excluded' if self.is_excluded else self.override_value or 'default'})"


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


class DataImportJob(models.Model):
    """Startup migration: Excel/CSV upload → map columns → preview → commit."""

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("mapped", "Mapped"),
        ("previewed", "Previewed"),
        ("committed", "Committed"),
        ("failed", "Failed"),
    ]
    SOURCE_CHOICES = [
        ("csv", "CSV"),
        ("xlsx", "Excel"),
        ("xls", "Excel legacy"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="data_import_jobs"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_import_jobs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="csv")
    file_name = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(
        upload_to="imports/",
        null=True,
        blank=True,
        storage=RawMediaCloudinaryStorage(),
    )
    headers = models.JSONField(default=list, blank=True)
    sample_rows = models.JSONField(default=list, blank=True)
    all_rows = models.JSONField(default=list, blank=True)
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Maps source header → target field key (or empty to skip)",
    )
    mapping_confidence = models.JSONField(default=dict, blank=True)
    preview_result = models.JSONField(default=dict, blank=True)
    commit_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.id} ({self.status}) — {self.file_name}"


class PayslipTemplate(models.Model):
    """Payslip visual template: gallery presets + org customs (incl. clone-from-upload)."""

    SOURCE_CHOICES = [
        ("system", "System gallery"),
        ("custom", "Custom"),
        ("cloned", "Cloned from upload"),
    ]
    LAYOUT_CHOICES = [
        ("classic", "Classic"),
        ("modern", "Modern"),
        ("compact", "Compact"),
        ("minimal", "Minimal"),
        ("uploaded", "Uploaded PDF"),
        ("networth", "Networth-style replica"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payslip_templates",
        help_text="Null = system gallery template available to all orgs",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, blank=True, default="")
    description = models.TextField(blank=True, default="")
    layout_key = models.CharField(
        max_length=20, choices=LAYOUT_CHOICES, default="classic"
    )
    theme = models.JSONField(
        default=dict,
        blank=True,
        help_text="Colors and display flags used by PDF renderer",
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="custom")
    source_file = models.FileField(
        upload_to="payslip_templates/",
        null=True,
        blank=True,
        storage=RawMediaCloudinaryStorage(),
    )
    preview_notes = models.TextField(
        blank=True,
        default="",
        help_text="AI notes from clone-from-upload analysis",
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_payslip_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        scope = self.organization_id or "system"
        return f"{self.name} ({scope})"
