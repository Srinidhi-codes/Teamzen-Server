from django.conf import settings
from django.db import models
from django.utils import timezone


class BotSession(models.Model):
    """Links a chat platform identity to a verified Teamzen user."""

    PLATFORM_TELEGRAM = "telegram"
    PLATFORM_WHATSAPP = "whatsapp"
    PLATFORM_SLACK = "slack"
    PLATFORM_CHOICES = [
        (PLATFORM_TELEGRAM, "Telegram"),
        (PLATFORM_WHATSAPP, "WhatsApp"),
        (PLATFORM_SLACK, "Slack"),
    ]

    AUTH_AWAITING_IDENTITY = "awaiting_identity"
    AUTH_AWAITING_OTP = "awaiting_otp"
    AUTH_VERIFIED = "verified"
    AUTH_CHOICES = [
        (AUTH_AWAITING_IDENTITY, "Awaiting identity"),
        (AUTH_AWAITING_OTP, "Awaiting OTP"),
        (AUTH_VERIFIED, "Verified"),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    chat_id = models.CharField(max_length=100)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bot_sessions",
    )
    auth_state = models.CharField(
        max_length=32,
        choices=AUTH_CHOICES,
        default=AUTH_AWAITING_IDENTITY,
    )
    pending_identity = models.CharField(max_length=255, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("platform", "chat_id")
        indexes = [
            models.Index(fields=["user", "platform", "is_verified"]),
        ]

    def __str__(self):
        who = self.user.email if self.user_id else self.pending_identity or "?"
        return f"{self.platform}:{self.chat_id} → {who}"

    @property
    def is_active(self) -> bool:
        if not self.is_verified or not self.user_id:
            return False
        if self.expires_at and timezone.now() >= self.expires_at:
            return False
        return True

    def mark_expired(self):
        self.is_verified = False
        self.auth_state = self.AUTH_AWAITING_IDENTITY
        self.user = None
        self.pending_identity = None
        self.expires_at = None
        self.save(
            update_fields=[
                "is_verified",
                "auth_state",
                "user",
                "pending_identity",
                "expires_at",
                "updated_at",
            ]
        )
