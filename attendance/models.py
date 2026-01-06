from django.db import models
from users.models import CustomUser
from organizations.models import OfficeLocation

class AttendanceRecord(models.Model):
    """Daily attendance record"""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late_login', 'Late Login'),
        ('early_logout', 'Early Logout'),
        ('half_day', 'Half Day'),
        ('leave', 'Leave'),
        ('holiday', 'Holiday'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.CASCADE)
    attendance_date = models.DateField()
    login_time = models.TimeField(null=True, blank=True)
    logout_time = models.TimeField(null=True, blank=True)
    login_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    login_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    logout_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    logout_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    is_within_geofence = models.BooleanField(default=False)
    login_distance = models.IntegerField(null=True, blank=True)
    logout_distance = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    worked_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'attendance_date')
        ordering = ['-attendance_date']

    def __str__(self):
        return f"{self.user} - {self.attendance_date}"

class AttendanceCorrection(models.Model):
    """Attendance correction requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    corrected_login_time = models.TimeField(null=True, blank=True)
    corrected_logout_time = models.TimeField(null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_corrections')
    approval_comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Correction for {self.attendance_record}"
