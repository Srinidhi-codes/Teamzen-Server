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
    profile_picture = models.ImageField(upload_to='teamzen/user_profile/', null=True, blank=True)
    
    # Employment Details
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='full_time')
    date_of_joining = models.DateField(default=timezone.localdate)
    date_of_leaving = models.DateField(null=True, blank=True)
    
    # Banking & Tax
    bank_account_number = models.CharField(max_length=100, null=True, blank=True)
    bank_ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    aadhar_number = models.CharField(max_length=100, null=True, blank=True)
    pan_number = models.CharField(max_length=20, null=True, blank=True)
    uan_number = models.CharField(max_length=100, null=True, blank=True)
    
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
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
    


