from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('PUSH', 'Push Notification'),
        ('EMAIL', 'Email Notification'),
        ('BOTH', 'Both'),
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
    
    message = models.TextField()
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES, default='BOTH')
    
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
