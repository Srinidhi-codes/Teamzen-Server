from django.db import models
from django.conf import settings


class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ("general", "General"),
        ("bug", "Bug"),
        ("feature", "Feature request"),
        ("praise", "Praise"),
        ("admin_share", "Admin share"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    VISIBILITY_CHOICES = [
        ("private", "Private to admins"),
        ("org", "Visible to organization"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="feedback_items",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedback_authored",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="general")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="open")
    visibility = models.CharField(
        max_length=16,
        choices=VISIBILITY_CHOICES,
        default="private",
        help_text="private = author + admins; org = everyone in the organization",
    )
    admin_reply = models.TextField(blank=True, default="")
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_replies",
    )
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "visibility"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.organization_id})"


class FeedbackAttachment(models.Model):
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to="teamzen/feedback/",
        max_length=1024,
    )
    file_name = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.file_name or str(self.file)
