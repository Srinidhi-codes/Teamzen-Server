from django.conf import settings
from django.db import models
from django.utils import timezone


class GoogleCalendarConnection(models.Model):
    """Per-user Google Calendar OAuth connection (Sequence 6)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_calendar",
    )
    refresh_token = models.TextField()
    access_token = models.TextField(blank=True, default="")
    token_expiry = models.DateTimeField(null=True, blank=True)
    calendar_id = models.CharField(max_length=255, default="primary")
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Calendar connection"
        verbose_name_plural = "Google Calendar connections"

    def __str__(self):
        return f"GCal:{self.user_id}"

    @property
    def access_token_valid(self) -> bool:
        if not self.access_token or not self.token_expiry:
            return False
        return timezone.now() < self.token_expiry
