from django.db import models
from datetime import time
from django.core.validators import RegexValidator
from django.conf import settings

class Organization(models.Model):
    """Enterprise organization model"""
    ACCENT_CHOICES = [
        ('teal', 'Teal'),
        ('slate', 'Slate'),
        ('blue', 'Blue'),
        ('green', 'Green'),
        ('indigo', 'Indigo'),
        ('orange', 'Orange'),
        ('red', 'Red'),
        ('purple', 'Purple'),
    ]

    name = models.CharField(max_length=255, unique=True)
    logo = models.ImageField(
        upload_to='teamzen/organization/',
        null=True,
        blank=True,
        max_length=1024,
    )
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    pan_number = models.CharField(max_length=50, null=True, blank=True)
    registration_number = models.CharField(max_length=100, null=True, blank=True)
    headquarters_address = models.TextField()
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('elite', 'Elite'),
    ]
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    plan_expires_at = models.DateField(
        null=True,
        blank=True,
        help_text='When the current paid plan ends. Null for free or lifetime.',
    )
    # Payroll automation (effective only for pro/elite — enforced in service/GraphQL)
    payroll_cycle_day = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of month (1–28) to auto-create previous month payroll",
    )
    payroll_auto_enabled = models.BooleanField(
        default=False,
        help_text="When True and plan is pro/elite, Celery auto-runs payroll on cycle day",
    )
    face_attendance_enabled = models.BooleanField(
        default=False,
        help_text="When True, employees must verify face and be inside geofence to punch attendance",
    )
    accent = models.CharField(
        max_length=20,
        choices=ACCENT_CHOICES,
        default='teal',
        help_text='Company color theme applied to the employee portal',
    )
    llm_api_key = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
 
    def __str__(self):
        return self.name


class OfficeLocation(models.Model):
    """
    Represents a physical office location with optional geo-fencing and shift constraints.
    Used for attendance, payroll jurisdiction, and employee assignment.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="office_locations"
    )

    # General Information
    name = models.CharField(max_length=255)
    address = models.TextField()

    city = models.CharField(max_length=64,null=True, blank=True)
    state = models.CharField(max_length=64,null=True, blank=True)
    country = models.CharField(max_length=64,null=True, blank=True)

    # Postal Code — longer to support global formats
    zip_code = models.CharField(
        max_length=20,null=True, blank=True,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9\s\-]+$",
                message="Zip codes may include letters, numbers, spaces, and hyphens."
            )
        ]
    )

    # Attendance Time Window (simple shift model)
    login_time = models.TimeField(default=time(9, 0))
    logout_time = models.TimeField(default=time(18, 0))

    # Geo-Fencing (optional)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Allowed radius in meters for geofence — 100m default
    geo_radius_meters = models.PositiveIntegerField(default=100)

    is_active = models.BooleanField(default=True)

    # Meta Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city"]),
            models.Index(fields=["state"]),
            models.Index(fields=["country"]),
        ]
        unique_together = ('organization', 'name')

    def __str__(self):
        return f"{self.name} ({self.city}, {self.country})"


class Department(models.Model):
    """Department model"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


class Designation(models.Model):
    """Job designation model"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# MCP platform tokens + audit (Sequence 5)
# ---------------------------------------------------------------------------

MCP_SCOPE_CHOICES = [
    "attendance:read",
    "attendance:write",
    "leaves:read",
    "leaves:write",
    "payroll:read",
    "policy:read",
    "hr:read",
]


class MCPApiToken(models.Model):
    """Org-scoped API token for external MCP clients (Cursor / Claude Desktop)."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="mcp_api_tokens",
    )
    name = models.CharField(max_length=100, help_text="Label, e.g. 'Cursor desktop'")
    token_prefix = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, help_text="List of scope strings")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_mcp_tokens",
    )
    bound_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mcp_bound_tokens",
        help_text="If set, all tool calls run as this user (user_id args are overwritten).",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.organization_id}) [{self.token_prefix}…]"

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])


class MCPAuditLog(models.Model):
    """Immutable log of MCP tool invocations."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mcp_audit_logs",
    )
    token = models.ForeignKey(
        MCPApiToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    server_name = models.CharField(max_length=64)
    tool_name = models.CharField(max_length=128)
    actor_user_id = models.IntegerField(null=True, blank=True)
    args_digest = models.CharField(max_length=64, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    is_internal = models.BooleanField(
        default=False,
        help_text="True when called via LangGraph internal secret",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["-created_at", "organization"],
                name="organizatio_created_a9cc50_idx",
            ),
            models.Index(
                fields=["tool_name", "-created_at"],
                name="organizatio_tool_na_61fc9a_idx",
            ),
        ]

    def __str__(self):
        status = "ok" if self.success else "fail"
        return f"{self.server_name}.{self.tool_name} [{status}] @ {self.created_at}"


class MCPDeviceCode(models.Model):
    """OAuth 2.0 device authorization grant for MCP clients (Cursor)."""

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DENIED, "Denied"),
        (STATUS_EXPIRED, "Expired"),
    ]

    device_code = models.CharField(max_length=64, unique=True, db_index=True)
    user_code = models.CharField(max_length=16, unique=True, db_index=True)
    client_id = models.CharField(max_length=128, default="cursor")
    scopes = models.JSONField(default=list)
    interval = models.PositiveSmallIntegerField(default=5)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mcp_device_codes",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mcp_device_codes",
    )
    access_token = models.ForeignKey(
        MCPApiToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_grants",
    )
    token_issued = models.BooleanField(
        default=False,
        help_text="True after the device client has polled and received the token once",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_code} [{self.status}]"


class MCPAuthCode(models.Model):
    """Authorization-code grant for browser redirect MCP clients."""

    code = models.CharField(max_length=64, unique=True, db_index=True)
    client_id = models.CharField(max_length=128, default="cursor")
    redirect_uri = models.CharField(max_length=512)
    scopes = models.JSONField(default=list)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_auth_codes",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="mcp_auth_codes",
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"auth_code…{self.code[-6:]} user={self.user_id}"
