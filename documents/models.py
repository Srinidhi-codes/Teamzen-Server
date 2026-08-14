from django.conf import settings
from django.db import models
from cloudinary_storage.storage import RawMediaCloudinaryStorage


def issued_document_upload_to(instance, filename):
    org_id = instance.organization_id or "unknown"
    user_id = instance.user_id or "unknown"
    return f"issued_docs/{org_id}/{user_id}/{filename}"


class IssuedDocument(models.Model):
    """HR-published packs for employee download (Form 16, certificates, exit letters)."""

    CATEGORY_CHOICES = [
        ("form_16", "Form 16"),
        ("salary_certificate", "Salary certificate"),
        ("experience", "Experience letter"),
        ("relieving", "Relieving letter"),
        ("fnf_statement", "F&F statement"),
        ("policy_ack", "Policy acknowledgement"),
        ("other", "Other"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="issued_documents",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="issued_documents",
    )
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="other")
    title = models.CharField(max_length=255)
    financial_year = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="e.g. 2025-26 for Form 16",
    )
    file = models.FileField(
        upload_to=issued_document_upload_to,
        storage=RawMediaCloudinaryStorage(),
        max_length=1024,
        blank=True,
        null=True,
    )
    file_url = models.URLField(max_length=1024, blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    visible_to_employee = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_issued_documents",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return f"{self.title} → user {self.user_id}"

    @property
    def download_url(self) -> str:
        # Prefer explicit URL (Cloudinary secure_url) — more reliable for raw PDFs
        if self.file_url:
            return self.file_url
        if self.file:
            try:
                url = self.file.url
                if url:
                    return url
            except Exception:
                pass
        return ""


class DocumentRequest(models.Model):
    """HR asks an employee to upload a specific document."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
    ]
    CATEGORY_CHOICES = [
        ("id_proof", "ID proof"),
        ("pan", "PAN"),
        ("aadhaar", "Aadhaar"),
        ("bank_proof", "Bank proof"),
        ("education", "Education"),
        ("hr_request", "HR request"),
        ("exit_clearance", "Exit clearance"),
        ("other", "Other"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="document_requests",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_requests",
    )
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="hr_request")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    due_at = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_document_requests",
    )
    fulfilled_document = models.ForeignKey(
        "onboarding.EmployeeDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fulfills_requests",
    )
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Request {self.title} ({self.status})"
