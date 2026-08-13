from django.conf import settings
from django.db import models
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class OffboardingTemplate(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="offboarding_templates",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    it_contact = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offboarding_templates_as_it",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_offboarding_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class OffboardingTaskDefinition(models.Model):
    ASSIGNEE_ROLE_CHOICES = [
        ("hr", "HR"),
        ("it", "IT"),
        ("manager", "Manager"),
        ("employee", "Employee"),
    ]
    PHASE_CHOICES = [
        ("notice", "Notice period"),
        ("last_day", "Last day"),
        ("clearance", "Clearance"),
        ("settlement", "Settlement"),
        ("letters", "Letters"),
    ]
    DOCUMENT_CATEGORY_CHOICES = [
        ("id_proof", "ID proof"),
        ("exit_clearance", "Exit clearance"),
        ("hr_request", "HR request"),
        ("other", "Other"),
    ]

    template = models.ForeignKey(
        OffboardingTemplate,
        on_delete=models.CASCADE,
        related_name="task_definitions",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee_role = models.CharField(
        max_length=20, choices=ASSIGNEE_ROLE_CHOICES, default="employee"
    )
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default="clearance")
    due_offset_days = models.IntegerField(
        default=0,
        help_text="Days relative to last working day (negative = before)",
    )
    requires_document_category = models.CharField(
        max_length=32,
        choices=DOCUMENT_CATEGORY_CHOICES,
        blank=True,
        default="",
    )
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} [{self.phase}]"


class EmployeeOffboarding(models.Model):
    STATUS_CHOICES = [
        ("initiated", "Initiated"),
        ("in_progress", "In progress"),
        ("settlement_pending", "Settlement pending"),
        ("letters_pending", "Letters pending"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    REASON_CHOICES = [
        ("resign", "Resignation"),
        ("terminate", "Termination"),
        ("contract_end", "Contract end"),
        ("other", "Other"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="employee_offboardings",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offboarding",
    )
    template = models.ForeignKey(
        OffboardingTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offboardings",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="initiated")
    reason = models.CharField(max_length=32, choices=REASON_CHOICES, default="resign")
    progress_pct = models.PositiveSmallIntegerField(default=0)
    exit_date = models.DateField(null=True, blank=True)
    last_working_day = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_offboardings",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offboarding {self.user_id} ({self.status})"


class OffboardingTaskInstance(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("blocked", "Blocked"),
        ("skipped", "Skipped"),
    ]

    offboarding = models.ForeignKey(
        EmployeeOffboarding,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    definition = models.ForeignKey(
        OffboardingTaskDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee_role = models.CharField(max_length=20, default="employee")
    phase = models.CharField(max_length=20, default="clearance")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_offboarding_tasks",
    )
    due_at = models.DateField(null=True, blank=True)
    is_required = models.BooleanField(default=True)
    requires_document_category = models.CharField(max_length=32, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_offboarding_tasks",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class ExitInvite(models.Model):
    offboarding = models.ForeignKey(
        EmployeeOffboarding,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exit_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class FnfSettlement(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("hr_approved", "HR approved"),
        ("acknowledged", "Acknowledged by employee"),
        ("paid", "Paid"),
    ]

    offboarding = models.OneToOneField(
        EmployeeOffboarding,
        on_delete=models.CASCADE,
        related_name="settlement",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    pro_rata_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    leave_encashment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bonus_gratuity = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_additions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    recoveries = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    snapshot = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    statement_pdf_url = models.URLField(max_length=1024, blank=True, default="")
    computed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_fnf_settlements",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def recompute_net(self):
        from decimal import Decimal

        additions = (
            Decimal(self.pro_rata_salary or 0)
            + Decimal(self.leave_encashment or 0)
            + Decimal(self.bonus_gratuity or 0)
            + Decimal(self.other_additions or 0)
        )
        deductions = Decimal(self.recoveries or 0) + Decimal(self.other_deductions or 0)
        self.net_payable = additions - deductions
        return self.net_payable


def exit_letter_pdf_upload_to(instance, filename):
    org_id = instance.offboarding.organization_id if instance.offboarding_id else "unknown"
    return f"exit_letters/{org_id}/{instance.offboarding_id}/{filename}"


class ExitLetter(models.Model):
    LETTER_TYPE_CHOICES = [
        ("experience", "Experience letter"),
        ("relieving", "Relieving letter"),
        ("salary_certificate", "Salary certificate"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("issued", "Issued"),
    ]

    offboarding = models.ForeignKey(
        EmployeeOffboarding,
        on_delete=models.CASCADE,
        related_name="letters",
    )
    letter_type = models.CharField(max_length=32, choices=LETTER_TYPE_CHOICES)
    letter_template = models.ForeignKey(
        "onboarding.DocumentLetterTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exit_letters",
    )
    subject = models.CharField(max_length=255, blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    pdf_url = models.URLField(max_length=1024, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    issued_document = models.ForeignKey(
        "documents.IssuedDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exit_letters",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exit_letters",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("offboarding", "letter_type")]

    def __str__(self):
        return f"{self.letter_type} for offboarding {self.offboarding_id}"
