from django.db import models
from datetime import time
from django.core.validators import RegexValidator

class Organization(models.Model):
    """Enterprise organization model"""
    name = models.CharField(max_length=255, unique=True)
    logo = models.ImageField(upload_to='teamzen/organization/', null=True, blank=True)
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