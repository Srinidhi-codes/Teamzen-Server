from django.db import models, transaction
from viewflow.fsm import State
from users.models import CustomUser
from organizations.models import OfficeLocation
from datetime import datetime, date


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
    actual_login_time = models.TimeField(null=True, blank=True)
    actual_logout_time = models.TimeField(null=True, blank=True)
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

    def recalculate_worked_hours(self):
        """
        Recalculate worked hours from login & logout time
        """
        if self.login_time and self.logout_time:
            start = datetime.combine(date.today(), self.login_time)
            end = datetime.combine(date.today(), self.logout_time)
            self.worked_hours = round(
                (end - start).total_seconds() / 3600,
                2
            )
        else:
            self.worked_hours = None

    def __str__(self):
        return f"{self.user} - {self.attendance_date}"

class AttendanceCorrection(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),        
        ("cancelled", "Cancelled")
    ]

    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    corrected_login_time = models.TimeField(null=True, blank=True)
    corrected_logout_time = models.TimeField(null=True, blank=True)

    reason = models.TextField()

    _status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_column='status')
    
    status = State(states=STATUS_CHOICES, default='pending')

    @status.getter()
    def _status_get(self):
        return self._status

    @status.setter()
    def _status_set(self, value):
        self._status = value
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_corrections",
    )
    approval_comments = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @status.transition(source='pending', target='approved')
    def approve(self, approver, comments=None):
        """
        Apply correction to attendance but KEEP correction record
        """
        attendance = self.attendance_record

        if self.corrected_login_time:
            attendance.login_time = self.corrected_login_time

        if self.corrected_logout_time:
            attendance.logout_time = self.corrected_logout_time

        attendance.recalculate_worked_hours()
        attendance.status = "present"
        attendance.is_verified = True
        attendance.save()

        self.approved_by = approver
        self.approval_comments = comments

    @status.transition(source='pending', target='rejected')
    def reject(self, approver, comments=None):
        self.approved_by = approver
        self.approval_comments = comments

    @status.transition(source='pending', target='cancelled')
    def cancel(self):
        pass

    def __str__(self):
        return f"Correction for {self.attendance_record}"