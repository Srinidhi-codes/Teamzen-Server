from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from organizations.models import Organization, Department, Designation, OfficeLocation

class CustomUser(AbstractUser):
    """Extended User model with HR fields"""
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    ROLE_CHOICES = [
        ('superadmin', 'Superadmin'),
        ('admin', 'Admin'),
        ('hr', 'HR'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]
    
    EMPLOYMENT_TYPES = [
        ('full_time', 'Full Time'),
        ('contract', 'Contract'),
        ('intern', 'Intern'),
    ]

    EMPLOYEE_STATUS = [
        ('active', 'Active'),
        ('exited', 'Exited'),
        ('terminated', 'Terminated'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,  null=True,
        blank=True)
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    
    # Personal Details
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    profile_picture = models.ImageField(
        upload_to='teamzen/user_profile/',
        null=True,
        blank=True,
        max_length=1024,
    )

    # Face attendance enrollment (client-side descriptors; shared across web/mobile)
    face_descriptor = models.JSONField(
        null=True,
        blank=True,
        help_text="Normalized face descriptor vector produced by the client face pipeline",
    )
    face_enrollment_image = models.ImageField(
        upload_to='teamzen/face_enrollment/',
        null=True,
        blank=True,
        max_length=1024,
    )
    face_enrolled_at = models.DateTimeField(null=True, blank=True)
    
    # Employment Details
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='full_time')
    date_of_joining = models.DateField(default=timezone.localdate)
    date_of_exit = models.DateField(null=True, blank=True)
    
    # Banking & Tax
    bank_account_number = models.CharField(max_length=100, null=True, blank=True)
    bank_ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    aadhar_number = models.CharField(max_length=100, null=True, blank=True)
    pan_number = models.CharField(max_length=20, null=True, blank=True)
    uan_number = models.CharField(max_length=100, null=True, blank=True)
    residential_address = models.TextField(
        blank=True,
        default="",
        help_text="Residential / permanent address for Form 16 and letters",
    )
    
    # Razorpay Integration
    razorpay_contact_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_fund_account_id = models.CharField(max_length=100, null=True, blank=True)
    
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # 2FA Fields
    totp_secret = models.CharField(max_length=32, blank=True, null=True)
    is_totp_enabled = models.BooleanField(default=False)
    
    # Onboarding Flags
    has_seen_onboarding = models.BooleanField(default=False)
    has_seen_ai_onboarding = models.BooleanField(default=False)

    # Security: email alerts on login activity (own login for all roles;
    # admins/HR also get org logins; superadmins get platform-wide logins)
    email_login_alerts = models.BooleanField(
        default=False,
        help_text="When enabled, receive email alerts for login activity.",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'email']),
            models.Index(fields=['manager']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_subordinates(self):
        return self.subordinates.all()

    def has_role(self, role_name):
        return self.role == role_name

class UserLoginHistory(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='login_history')
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=25, decimal_places=10, null=True, blank=True)
    longitude = models.DecimalField(max_digits=25, decimal_places=10, null=True, blank=True)
    status = models.CharField(max_length=20, default='success') # success, failed

    class Meta:
        ordering = ['-login_time']
        verbose_name_plural = "User Login Histories"

    def __str__(self):
        return f"{self.user.email} logged in at {self.login_time}"
class UserDeviceSession(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='device_sessions')
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    browser = models.CharField(max_length=100, null=True, blank=True)
    os = models.CharField(max_length=100, null=True, blank=True)
    device_type = models.CharField(max_length=50, null=True, blank=True)  # e.g. Mobile, Tablet, Desktop
    device_name = models.CharField(max_length=100, null=True, blank=True) # e.g. Windows PC, iPhone
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_active']

    def __str__(self):
        return f"{self.user.email} - {self.device_name or 'Unknown'} ({self.os or 'Unknown'})"
