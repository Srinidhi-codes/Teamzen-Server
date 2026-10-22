from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('PUSH', 'Push Notification'),
        ('EMAIL', 'Email Notification'),
        ('BOTH', 'Both'),
    ]

    LEVEL_CHOICES = [
        ('personal', 'Personal'),
        ('admin', 'Admin'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acted_notifications'
    )
    verb = models.CharField(max_length=255)  # e.g., "approved", "rejected", "requested"
    target_type = models.CharField(max_length=100, blank=True, null=True)  # e.g., "Leave Request"
    target_id = models.CharField(max_length=255, blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    
    message = models.TextField()
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES, default='BOTH')
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='personal')
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Notification for {self.recipient.email}: {self.verb}"


class EmailTemplateSetting(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='email_template_settings'
    )
    template_key = models.CharField(max_length=64, db_index=True)
    is_enabled = models.BooleanField(default=True)

    # Custom template overrides (null means use built-in default)
    custom_category = models.CharField(max_length=64, blank=True, null=True, help_text="Custom category for this email notification")
    custom_subject = models.CharField(max_length=255, blank=True, null=True)
    custom_headline = models.CharField(max_length=255, blank=True, null=True)
    custom_body = models.TextField(blank=True, null=True)
    custom_cta_text = models.CharField(max_length=100, blank=True, null=True)
    custom_cta_url = models.CharField(max_length=500, blank=True, null=True)
    custom_footer = models.TextField(blank=True, null=True)

    # Raw JSX / HTML Direct Paste Mode
    is_raw_html_mode = models.BooleanField(
        default=False,
        help_text="When True, custom_full_html is rendered directly bypassing the standard builder"
    )
    custom_full_html = models.TextField(
        blank=True,
        null=True,
        help_text="Direct custom raw HTML or JSX email template code"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_email_templates'
    )

    class Meta:
        unique_together = ('organization', 'template_key')
        indexes = [
            models.Index(fields=['organization', 'template_key']),
        ]

    def __str__(self):
        org_name = self.organization.name if self.organization else "System Default"
        status = "Enabled" if self.is_enabled else "Disabled"
        return f"{self.template_key} ({org_name}) - {status}"

    @classmethod
    def is_email_enabled(cls, organization, template_key: str) -> bool:
        """
        Check if sending email for this template_key is enabled for the organization.
        Defaults to True if no record exists.
        """
        if not template_key:
            return True
        try:
            if organization:
                setting = cls.objects.filter(organization=organization, template_key=template_key).first()
                if setting is not None:
                    return setting.is_enabled
            default_setting = cls.objects.filter(organization__isnull=True, template_key=template_key).first()
            if default_setting is not None:
                return default_setting.is_enabled
        except Exception as e:
            print(f"[EmailTemplateSetting] is_email_enabled check error: {e}")
        return True

    @classmethod
    def get_setting_or_default(cls, organization, template_key: str):
        setting = None
        if organization:
            setting = cls.objects.filter(organization=organization, template_key=template_key).first()
        if not setting:
            setting = cls.objects.filter(organization__isnull=True, template_key=template_key).first()
        return setting
