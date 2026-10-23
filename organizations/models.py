from django.db import models
from datetime import time
from django.core.validators import RegexValidator
from django.conf import settings


def default_weekend_days():
    """Sunday-only weekly off (matches historical leave duration behaviour)."""
    return [6]


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
    tan_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Tax Deduction Account Number (TRACES / TDS)",
    )
    cit_tds_office = models.TextField(
        blank=True,
        default="",
        help_text="CIT (TDS) office address",
    )
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
        help_text="When True, employees must verify face to punch attendance (geofence remains soft-flagged)",
    )
    # Attendance Regularization Policy & Security (Enterprise Guardrails)
    attendance_regularization_monthly_limit = models.PositiveSmallIntegerField(
        default=3,
        help_text="Maximum self-service regularizations permitted per employee per calendar month",
    )
    attendance_regularization_deadline_days = models.PositiveSmallIntegerField(
        default=3,
        help_text="Maximum allowed submission window in business days following the attendance discrepancy",
    )
    attendance_regularization_escalation_limit = models.PositiveSmallIntegerField(
        default=3,
        help_text="Monthly request count that escalates the approval to HR/Executive level",
    )
    device_binding_enforced = models.BooleanField(
        default=False,
        help_text="When True, employees may only punch attendance from registered and approved hardware devices",
    )
    weekend_days = models.JSONField(
        default=default_weekend_days,
        blank=True,
        help_text=(
            "Weekly off days as Python weekday ints (Mon=0 … Sun=6). "
            "Empty list means no weekly offs. Default is Sunday [6]."
        ),
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
        ordering = ['id']
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
        ordering = ['id']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


class Designation(models.Model):
    """Job designation model"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    hierarchy_level = models.IntegerField(
        default=4,
        help_text="Hierarchy grade level: 1=Exec, 2=Director/VP, 3=Manager/Lead, 4=Staff, 5=Associate"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
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


# ---------------------------------------------------------------------------
# 3-Tier Access Control & Feature Gating Models
# ---------------------------------------------------------------------------

class PlanFeatureDefault(models.Model):
    """Platform-wide default features per plan level (Super Admin managed)."""
    plan = models.CharField(max_length=20, choices=Organization.PLAN_CHOICES)
    module_key = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ('plan', 'module_key')
        ordering = ['plan', 'module_key']

    def __str__(self):
        status = "ON" if self.is_enabled else "OFF"
        return f"[{self.plan.upper()}] {self.module_key}: {status}"


class OrganizationFeatureOverride(models.Model):
    """Super Admin override for a specific company's plan features."""
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='feature_overrides'
    )
    module_key = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'module_key')
        ordering = ['organization', 'module_key']

    def __str__(self):
        status = "ENABLED" if self.is_enabled else "REVOKED"
        return f"{self.organization.name} - {self.module_key}: {status}"


class CompanyAdminDelegation(models.Model):
    """Super Admin delegation defining what Company Admins are authorized to manage."""
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='admin_delegation'
    )
    can_manage_payroll = models.BooleanField(default=True)
    can_manage_leaves = models.BooleanField(default=True)
    can_manage_attendance = models.BooleanField(default=True)
    can_manage_employees = models.BooleanField(default=True)
    can_manage_email_templates = models.BooleanField(default=True)
    can_manage_onboarding = models.BooleanField(default=True)
    can_manage_policies = models.BooleanField(default=True)
    can_manage_rbac = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delegation for {self.organization.name}"


class RoleModulePermission(models.Model):
    """Workforce role access matrix per organization (Company Admin & Super Admin managed)."""
    ACCESS_LEVELS = [
        ('none', 'No Access'),
        ('view', 'Read Only'),
        ('full', 'Full Access'),
    ]
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='role_permissions'
    )
    role = models.CharField(max_length=32)  # 'admin', 'hr', 'manager', 'employee'
    module_key = models.CharField(max_length=64)
    access_level = models.CharField(max_length=16, choices=ACCESS_LEVELS, default='view')
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'role', 'module_key')
        ordering = ['organization', 'role', 'module_key']

    def __str__(self):
        return f"{self.organization.name} - {self.role.upper()} - {self.module_key}: {self.access_level}"


class OrganizationRole(models.Model):
    """
    Dynamic workforce roles defined for an organization.
    Permits creating custom roles (e.g. 'Payroll Officer', 'Auditor', 'Recruiter')
    in addition to the built-in system roles (Admin, HR, Manager, Employee).
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='custom_roles'
    )
    role_key = models.CharField(max_length=32)
    role_label = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, null=True)
    is_system_role = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'role_key')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.organization.name} - {self.role_label} ({self.role_key})"

