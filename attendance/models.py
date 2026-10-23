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

    APPROVAL_CHOICES = [
        ('auto_approved', 'Auto Approved'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
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
    # Face attendance audit (populated when org.face_attendance_enabled)
    face_verified = models.BooleanField(default=False)
    face_match_score = models.FloatField(null=True, blank=True)
    check_in_selfie = models.ImageField(
        upload_to='teamzen/attendance_selfies/',
        null=True,
        blank=True,
        max_length=1024,
    )
    check_out_selfie = models.ImageField(
        upload_to='teamzen/attendance_selfies/',
        null=True,
        blank=True,
        max_length=1024,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    worked_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Background geo-heartbeat audit fields
    total_heartbeats = models.PositiveIntegerField(default=0, null=True, blank=True)
    valid_heartbeats = models.PositiveIntegerField(default=0, null=True, blank=True)
    out_of_fence_heartbeats = models.PositiveIntegerField(default=0, null=True, blank=True)
    effective_worked_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    roaming_anomaly_detected = models.BooleanField(default=False)
    roaming_notes = models.CharField(max_length=255, blank=True, default='')

    remarks = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)

    # Shift Window & Weekend/Holiday Manager Approval
    is_weekend_work = models.BooleanField(default=False)
    is_off_hours = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='auto_approved')
    approved_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_attendances'
    )
    approval_remarks = models.CharField(max_length=255, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'attendance_date')
        ordering = ['-attendance_date']

    def recalculate_worked_hours(self):
        """
        Recalculate worked hours from login & logout time, adjusting for roaming/out-of-fence gaps.
        """
        if self.login_time and self.logout_time:
            start = datetime.combine(self.attendance_date, self.login_time)
            end = datetime.combine(self.attendance_date, self.logout_time)
            
            # Handle cross-day logout
            if end < start:
                from datetime import timedelta
                end += timedelta(days=1)
                
            self.worked_hours = round(
                (end - start).total_seconds() / 3600,
                2
            )
            # Factor in out-of-fence heartbeats (e.g. roaming outside office)
            out_count = self.out_of_fence_heartbeats or 0
            if out_count > 0:
                # 20 min interval assumed per ping, 1.0 hour grace break allowance
                roaming_hours = round(out_count * 0.33, 2)
                excess_roaming = max(0.0, roaming_hours - 1.0)
                self.effective_worked_hours = round(max(0.0, float(self.worked_hours) - excess_roaming), 2)
            else:
                self.effective_worked_hours = self.worked_hours
        else:
            self.worked_hours = None
            self.effective_worked_hours = None

    def recalculate_status(self):
        """
        Main logic for status determination based on shift times, duration, and verified presence.
        """
        if not self.login_time or self.approval_status == 'rejected':
            self.status = 'absent'
            return

        office = self.office_location
        if not office:
            return

        # 1. Login Violation
        is_late = self.login_time > office.login_time
        
        if not self.logout_time:
            # Still clocked in
            self.status = 'late_login' if is_late else 'present'
            return

        # 2. Logout Violation
        is_early = self.logout_time < office.logout_time
        
        # 3. Duration-based overrides (use effective_worked_hours if presence tracked)
        hours = float(self.effective_worked_hours if self.effective_worked_hours is not None else (self.worked_hours or 0))
        
        if hours < 1.0:
            self.status = 'absent'
        elif hours < 4.0:
            self.status = 'half_day'
        elif is_late and is_early:
            self.status = 'half_day'  # Double violation is penalized
        elif is_late:
            self.status = 'late_login'
        elif is_early:
            self.status = 'early_logout'
        else:
            self.status = 'present'

    def save(self, *args, **kwargs):
        # Auto-calc before saving
        self.recalculate_worked_hours()
        self.recalculate_status()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.attendance_date} ({self.status})"


class AttendanceHeartbeat(models.Model):
    """Periodic background geolocation breadcrumb during a shift."""
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name='heartbeats',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    distance_meters = models.IntegerField(help_text="Calculated distance in meters from assigned office")
    is_within_geofence = models.BooleanField(default=False)
    accuracy_meters = models.FloatField(null=True, blank=True)
    is_mocked = models.BooleanField(default=False, help_text="Detected fake GPS / mock provider")
    battery_level = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['attendance_record', 'timestamp']),
        ]

    def __str__(self):
        fence_str = 'inside' if self.is_within_geofence else 'outside'
        return f"Heartbeat {self.attendance_record.user} @ {self.timestamp} ({fence_str}, {self.distance_meters}m)"

class UserDeviceBinding(models.Model):
    """
    Hardware Device Registration for anti-proxy & anti-buddy punching enforcement.
    Prevents employees from clocking in for peers from unauthorized devices.
    """
    DEVICE_TYPES = [
        ("web", "Web Browser"),
        ("mobile_android", "Android App"),
        ("mobile_ios", "iOS App"),
        ("kiosk", "Office Kiosk / Shared Device"),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="device_bindings")
    device_id = models.CharField(max_length=128, db_index=True)
    device_name = models.CharField(max_length=128, blank=True, default="")
    device_type = models.CharField(max_length=32, choices=DEVICE_TYPES, default="web")
    fingerprint = models.CharField(max_length=255, blank=True, default="")
    is_trusted = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "device_id")
        indexes = [
            models.Index(fields=["user", "device_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.device_name or self.device_id[:12]}"


class AttendanceCorrection(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),        
        ("cancelled", "Cancelled")
    ]

    CATEGORY_CHOICES = [
        ("FORGOT_TO_PUNCH", "Forgot to Punch"),
        ("BIOMETRIC_DEVICE_ERROR", "Biometric / Device Failure"),
        ("CLIENT_VISIT_ON_DUTY", "Client Visit / On-Duty"),
        ("POWER_INTERNET_OUTAGE", "Power / Internet Outage"),
        ("OTHER_EXCEPTION", "Other Exception"),
    ]

    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    category = models.CharField(
        max_length=40,
        choices=CATEGORY_CHOICES,
        default="FORGOT_TO_PUNCH",
        help_text="Standardized justification category for attendance adjustment",
    )
    supporting_evidence = models.FileField(
        upload_to="teamzen/regularization_proofs/",
        null=True,
        blank=True,
        max_length=1024,
        help_text="Uploaded document or screenshot supporting the regularization request",
    )

    # Requested adjustment times
    corrected_login_time = models.TimeField(null=True, blank=True)
    corrected_logout_time = models.TimeField(null=True, blank=True)

    # Historical punch snapshot at time of request (prevents tampering)
    original_login_time = models.TimeField(null=True, blank=True)
    original_logout_time = models.TimeField(null=True, blank=True)

    # System-suggested bounds (derived from shift or verified office heartbeats)
    system_suggested_login_time = models.TimeField(null=True, blank=True)
    system_suggested_logout_time = models.TimeField(null=True, blank=True)

    reason = models.TextField()

    # Policy escalation & audit notes
    escalated_to_hr = models.BooleanField(
        default=False,
        help_text="True if request hit the organizational quota threshold and requires HR escalation",
    )
    policy_violation_notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Automatic policy evaluation notes (e.g. 3rd monthly request)",
    )

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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @status.transition(source='pending', target='approved')
    def approve(self, approver, comments=None):
        """
        Apply correction to attendance while preserving historical punch data.
        """
        attendance = self.attendance_record

        # Preserve original unadjusted punch times if not already set
        if not attendance.actual_login_time and attendance.login_time:
            attendance.actual_login_time = attendance.login_time
        if not attendance.actual_logout_time and attendance.logout_time:
            attendance.actual_logout_time = attendance.logout_time

        if self.corrected_login_time:
            attendance.login_time = self.corrected_login_time

        if self.corrected_logout_time:
            attendance.logout_time = self.corrected_logout_time

        attendance.is_verified = True
        attendance.recalculate_worked_hours()

        hours = float(attendance.worked_hours or 0)
        if hours >= 8.0:
            attendance.status = 'present'
        elif hours >= 4.0:
            attendance.status = 'half_day'
        elif hours > 0:
            attendance.status = 'present'

        attendance.save()

        self.approved_by = approver
        self.approval_comments = comments or ""

    @status.transition(source='pending', target='rejected')
    def reject(self, approver, comments=None):
        self.approved_by = approver
        self.approval_comments = comments or ""

    @status.transition(source='pending', target='cancelled')
    def cancel(self):
        pass

    def __str__(self):
        return f"Correction for {self.attendance_record} ({self.category} - {self.status})"