from django.conf import settings
from django.db import models
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class OnboardingTemplate(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="onboarding_templates",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_templates",
    )
    designation = models.ForeignKey(
        "organizations.Designation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_templates",
    )
    employment_type = models.CharField(max_length=20, blank=True, default="")
    is_default = models.BooleanField(default=False)
    it_contact = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_templates_as_it",
        help_text="User who receives IT-role onboarding tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_onboarding_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class OnboardingTaskDefinition(models.Model):
    ASSIGNEE_ROLE_CHOICES = [
        ("hr", "HR"),
        ("it", "IT"),
        ("manager", "Manager"),
        ("hire", "New hire"),
    ]
    PHASE_CHOICES = [
        ("preboarding", "Preboarding"),
        ("day1", "Day 1"),
        ("week1", "Week 1"),
        ("day30", "Day 30"),
        ("day90", "Day 90"),
    ]
    DOCUMENT_CATEGORY_CHOICES = [
        ("id_proof", "ID proof"),
        ("pan", "PAN"),
        ("aadhaar", "Aadhaar"),
        ("bank_proof", "Bank proof"),
        ("education", "Education"),
        ("offer", "Offer letter"),
        ("signed_policy", "Signed policy"),
        ("other", "Other"),
    ]

    template = models.ForeignKey(
        OnboardingTemplate,
        on_delete=models.CASCADE,
        related_name="task_definitions",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee_role = models.CharField(
        max_length=20, choices=ASSIGNEE_ROLE_CHOICES, default="hire"
    )
    phase = models.CharField(
        max_length=20, choices=PHASE_CHOICES, default="preboarding"
    )
    due_offset_days = models.IntegerField(
        default=0,
        help_text="Days relative to join date (negative = before join)",
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


class EmployeeOnboarding(models.Model):
    STATUS_CHOICES = [
        ("invited", "Invited"),
        ("preboarding", "Preboarding"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="employee_onboardings",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding",
    )
    template = models.ForeignKey(
        OnboardingTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboardings",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="invited"
    )
    progress_pct = models.PositiveSmallIntegerField(default=0)
    join_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_onboardings",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Onboarding {self.user_id} ({self.status})"


class OnboardingTaskInstance(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("blocked", "Blocked"),
        ("skipped", "Skipped"),
    ]

    onboarding = models.ForeignKey(
        EmployeeOnboarding,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    definition = models.ForeignKey(
        OnboardingTaskDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee_role = models.CharField(max_length=20, default="hire")
    phase = models.CharField(max_length=20, default="preboarding")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_tasks",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
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
        related_name="completed_onboarding_tasks",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.status})"


def employee_document_upload_to(instance, filename):
    org_id = instance.organization_id or "unknown"
    user_id = instance.user_id or "unknown"
    return f"employee_docs/{org_id}/{user_id}/{filename}"


class EmployeeDocument(models.Model):
    CATEGORY_CHOICES = OnboardingTaskDefinition.DOCUMENT_CATEGORY_CHOICES
    VERIFICATION_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="employee_documents",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_documents",
    )
    onboarding = models.ForeignKey(
        EmployeeOnboarding,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="other")
    title = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(
        upload_to=employee_document_upload_to,
        storage=RawMediaCloudinaryStorage(),
        max_length=1024,
    )
    file_name = models.CharField(max_length=255, blank=True, default="")
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_CHOICES, default="pending"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_employee_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    ai_suggested_category = models.CharField(max_length=32, blank=True, default="")
    ai_confidence = models.FloatField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_employee_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.category} for user {self.user_id}"


class DocumentLetterTemplate(models.Model):
    LETTER_TYPE_CHOICES = [
        ("offer", "Offer letter"),
        ("experience", "Experience letter"),
        ("salary_certificate", "Salary certificate"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="letter_templates",
    )
    name = models.CharField(max_length=255)
    letter_type = models.CharField(
        max_length=32, choices=LETTER_TYPE_CHOICES, default="offer"
    )
    subject = models.CharField(max_length=255, blank=True, default="")
    body_html = models.TextField(
        help_text="HTML with merge fields like {{employee_name}}, {{designation}}, {{join_date}}, {{company_name}}"
    )
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_letter_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.name} ({self.letter_type})"


class OfferLetter(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]
    SOURCE_CHOICES = [
        ("generated", "System generated"),
        ("uploaded", "HR uploaded"),
    ]

    onboarding = models.OneToOneField(
        EmployeeOnboarding,
        on_delete=models.CASCADE,
        related_name="offer_letter",
    )
    letter_template = models.ForeignKey(
        DocumentLetterTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offer_letters",
    )
    subject = models.CharField(max_length=255, blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    pdf_url = models.URLField(max_length=1024, blank=True, default="")
    signed_pdf_url = models.URLField(max_length=1024, blank=True, default="")
    signed_uploaded_at = models.DateTimeField(null=True, blank=True)
    signed_uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_signed_offer_letters",
    )
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default="generated"
    )
    include_ctc_annexure = models.BooleanField(default=False)
    annual_ctc = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    ctc_snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="Frozen CTC annexure payload used when generating the PDF",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    accepted_name = models.CharField(max_length=255, blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_ip = models.GenericIPAddressField(null=True, blank=True)
    accepted_ua = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_offer_letters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Offer for onboarding {self.onboarding_id} ({self.status})"


class PreboardingInvite(models.Model):
    onboarding = models.ForeignKey(
        EmployeeOnboarding,
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
        related_name="created_preboarding_invites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite for onboarding {self.onboarding_id}"
