from datetime import date, time, timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from graphql import GraphQLError
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import CustomUser
from organizations.models import Organization, OfficeLocation
from attendance.models import AttendanceRecord, AttendanceCorrection, UserDeviceBinding
from attendance.services import (
    request_regularization_for_user,
    process_regularization_approval_decision,
    get_monthly_regularization_quota_summary,
    count_business_days,
    generate_face_challenge_token,
    validate_face_challenge_token,
    assert_device_binding_allowed,
    assert_face_attendance_allowed,
)
from attendance.api_views import FaceExtractView
from payroll.models import PayrollRun


class AttendanceRegularizationPolicyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(
            name="Acme Corp",
            attendance_regularization_monthly_limit=3,
            attendance_regularization_deadline_days=3,
            attendance_regularization_escalation_limit=3,
            device_binding_enforced=False,
        )
        self.office = OfficeLocation.objects.create(
            organization=self.org,
            name="HQ Office",
            latitude=12.9716,
            longitude=77.5946,
            geo_radius_meters=500,
            login_time=time(9, 0),
            logout_time=time(18, 0),
        )

        self.employee = CustomUser.objects.create_user(
            email="emp@acme.com",
            username="emp_acme",
            password="Password123!",
            organization=self.org,
            role="employee",
            hierarchy_level=4,
            first_name="Alice",
            last_name="Smith",
        )
        self.manager = CustomUser.objects.create_user(
            email="manager@acme.com",
            username="mgr_acme",
            password="Password123!",
            organization=self.org,
            role="manager",
            hierarchy_level=3,
            first_name="Bob",
            last_name="Jones",
        )
        self.hr = CustomUser.objects.create_user(
            email="hr@acme.com",
            username="hr_acme",
            password="Password123!",
            organization=self.org,
            role="hr",
            hierarchy_level=3,
            first_name="Carol",
            last_name="White",
        )

        # Assign manager
        self.employee.manager = self.manager
        self.employee.save()

        # Other Org for tenant isolation testing
        self.other_org = Organization.objects.create(name="Beta Inc")
        self.other_user = CustomUser.objects.create_user(
            email="other@beta.com",
            username="other_beta",
            password="Password123!",
            organization=self.other_org,
            role="employee",
            hierarchy_level=4,
        )

    def test_valid_regularization_within_deadline(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            login_time=time(9, 30),
            logout_time=time(17, 30),
            actual_login_time=time(9, 30),
            actual_logout_time=time(17, 30),
            status="late_login",
        )

        correction = request_regularization_for_user(
            user=self.employee,
            attendance_record_id=rec.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="Missed biometric punch due to network latency at front gate.",
            category="BIOMETRIC_DEVICE_ERROR",
        )

        self.assertEqual(correction.status, "pending")
        self.assertEqual(correction.category, "BIOMETRIC_DEVICE_ERROR")
        self.assertEqual(correction.original_login_time, time(9, 30))
        self.assertFalse(correction.escalated_to_hr)

    def test_expired_submission_window_rejected(self):
        today = timezone.localdate()
        # 10 business days ago exceeds 3 business days SLA
        old_date = today - timedelta(days=15)
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=old_date,
            login_time=time(9, 30),
            logout_time=time(17, 30),
            status="present",
        )

        with self.assertRaises(GraphQLError) as ctx:
            request_regularization_for_user(
                user=self.employee,
                attendance_record_id=rec.id,
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                reason="Late submission request for old record.",
            )
        self.assertIn("Submission window expired", str(ctx.exception))

    def test_monthly_quota_exhausted(self):
        today = timezone.localdate()
        # Create 3 requests (the monthly quota limit)
        for i in range(1, 4):
            d = today - timedelta(days=i)
            rec = AttendanceRecord.objects.create(
                user=self.employee,
                office_location=self.office,
                attendance_date=d,
                login_time=time(9, 30),
                logout_time=time(17, 30),
                status="present",
            )
            AttendanceCorrection.objects.create(
                attendance_record=rec,
                requested_by=self.employee,
                category="FORGOT_TO_PUNCH",
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                _status="pending",
                reason=f"Correction #{i}",
            )

        # 4th request in the same month must be blocked
        rec4 = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            login_time=time(9, 30),
            logout_time=time(17, 30),
            status="present",
        )

        with self.assertRaises(GraphQLError) as ctx:
            request_regularization_for_user(
                user=self.employee,
                attendance_record_id=rec4.id,
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                reason="4th correction attempt",
            )
        self.assertIn("Monthly regularization quota (3 requests) exhausted", str(ctx.exception))

    def test_hr_escalation_on_third_request(self):
        today = timezone.localdate()
        # 2 existing requests
        for i in range(1, 3):
            d = today - timedelta(days=i)
            rec = AttendanceRecord.objects.create(
                user=self.employee,
                office_location=self.office,
                attendance_date=d,
                status="present",
            )
            AttendanceCorrection.objects.create(
                attendance_record=rec,
                requested_by=self.employee,
                _status="approved",
                reason=f"Prior request #{i}",
            )

        # 3rd request should trigger escalation_limit (3)
        rec3 = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )
        correction = request_regularization_for_user(
            user=self.employee,
            attendance_record_id=rec3.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="3rd request this month",
        )

        self.assertTrue(correction.escalated_to_hr)
        self.assertIn("Escalated to HR", correction.policy_violation_notes)

    def test_duplicate_pending_request_prevented(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )

        # First request
        request_regularization_for_user(
            user=self.employee,
            attendance_record_id=rec.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="Initial request",
        )

        # Duplicate pending attempt
        with self.assertRaises(GraphQLError) as ctx:
            request_regularization_for_user(
                user=self.employee,
                attendance_record_id=rec.id,
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                reason="Duplicate attempt",
            )
        self.assertIn("A pending regularization request already exists", str(ctx.exception))

    def test_self_approval_prevented(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.manager,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )
        correction = request_regularization_for_user(
            user=self.manager,
            attendance_record_id=rec.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="Manager requesting own correction",
        )

        # Manager attempts self-approval
        with self.assertRaises(GraphQLError) as ctx:
            process_regularization_approval_decision(
                correction_id=correction.id,
                action="approved",
                approver=self.manager,
                comments="Self approving",
            )
        self.assertIn("Self-approval is strictly prohibited", str(ctx.exception))

    def test_manager_approval_success_preserves_actual_punch(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            login_time=time(10, 0),
            logout_time=time(16, 0),
            actual_login_time=time(10, 0),
            actual_logout_time=time(16, 0),
            status="half_day",
        )
        correction = request_regularization_for_user(
            user=self.employee,
            attendance_record_id=rec.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="Corrected to full shift hours.",
        )

        process_regularization_approval_decision(
            correction_id=correction.id,
            action="approved",
            approver=self.manager,
            comments="Approved after checking badge logs.",
        )

        correction.refresh_from_db()
        rec.refresh_from_db()

        self.assertEqual(correction.status, "approved")
        self.assertEqual(correction.approved_by, self.manager)
        # Effective time updated
        self.assertEqual(rec.login_time, time(9, 0))
        self.assertEqual(rec.logout_time, time(18, 0))
        # Historical actual punch preserved!
        self.assertEqual(rec.actual_login_time, time(10, 0))
        self.assertEqual(rec.actual_logout_time, time(16, 0))
        self.assertEqual(rec.status, "present")

    def test_hr_only_can_approve_escalated_request(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )
        correction = AttendanceCorrection.objects.create(
            attendance_record=rec,
            requested_by=self.employee,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            _status="pending",
            escalated_to_hr=True,
            reason="High quota escalation",
        )

        # Regular manager approval blocked
        with self.assertRaises(GraphQLError) as ctx:
            process_regularization_approval_decision(
                correction_id=correction.id,
                action="approved",
                approver=self.manager,
            )
        self.assertIn("requires HR approval", str(ctx.exception))

        # HR user succeeds
        process_regularization_approval_decision(
            correction_id=correction.id,
            action="approved",
            approver=self.hr,
            comments="HR approved escalation",
        )
        correction.refresh_from_db()
        self.assertEqual(correction.status, "approved")

    def test_payroll_lock_prevents_regularization(self):
        today = timezone.localdate()
        PayrollRun.objects.create(
            organization=self.org,
            month=today.month,
            year=today.year,
            status="completed",
        )
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )

        with self.assertRaises(GraphQLError) as ctx:
            request_regularization_for_user(
                user=self.employee,
                attendance_record_id=rec.id,
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                reason="Attempting post-payroll correction",
            )
        self.assertIn("Attendance for this period is locked because payroll has already been finalized", str(ctx.exception))

    def test_cross_tenant_access_blocked(self):
        today = timezone.localdate()
        other_office = OfficeLocation.objects.create(
            organization=self.other_org,
            name="Beta Office",
            latitude=12.9716,
            longitude=77.5946,
            geo_radius_meters=500,
            login_time=time(9, 0),
            logout_time=time(18, 0),
        )
        other_rec = AttendanceRecord.objects.create(
            user=self.other_user,
            office_location=other_office,
            attendance_date=today,
            status="present",
        )

        with self.assertRaises(GraphQLError) as ctx:
            request_regularization_for_user(
                user=self.hr,
                attendance_record_id=other_rec.id,
                corrected_login_time=time(9, 0),
                corrected_logout_time=time(18, 0),
                reason="Cross tenant attack",
            )
        self.assertIn("Cross-tenant access forbidden", str(ctx.exception))

    def test_mandatory_comments_on_rejection(self):
        today = timezone.localdate()
        rec = AttendanceRecord.objects.create(
            user=self.employee,
            office_location=self.office,
            attendance_date=today,
            status="present",
        )
        correction = request_regularization_for_user(
            user=self.employee,
            attendance_record_id=rec.id,
            corrected_login_time=time(9, 0),
            corrected_logout_time=time(18, 0),
            reason="Request to be rejected",
        )

        with self.assertRaises(GraphQLError) as ctx:
            process_regularization_approval_decision(
                correction_id=correction.id,
                action="rejected",
                approver=self.manager,
                comments="",  # empty remarks
            )
        self.assertIn("A rejection reason/comment is required", str(ctx.exception))


class AntiProxyAndBiometricSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.org = Organization.objects.create(
            name="Secure Corp",
            face_attendance_enabled=True,
            device_binding_enforced=True,
        )
        self.employee = CustomUser.objects.create_user(
            email="victim@secure.com",
            username="victim_sec",
            password="Password123!",
            organization=self.org,
            role="employee",
            hierarchy_level=4,
        )
        self.hr = CustomUser.objects.create_user(
            email="hr@secure.com",
            username="hr_sec",
            password="Password123!",
            organization=self.org,
            role="hr",
            hierarchy_level=3,
        )

    def test_challenge_token_validation_and_replay_prevention(self):
        token = generate_face_challenge_token(self.employee.id)
        self.assertIsInstance(token, str)

        # 1. First validation succeeds
        validate_face_challenge_token(self.employee, token)

        # 2. Replay attack: Re-using the same token fails immediately
        with self.assertRaises(GraphQLError) as ctx:
            validate_face_challenge_token(self.employee, token)
        self.assertIn("Face challenge token has already been consumed (anti-replay)", str(ctx.exception))

    def test_device_binding_enforcement(self):
        # 1. First time device enrollment succeeds automatically
        assert_device_binding_allowed(self.employee, device_id="laptop-hardware-uuid-1", device_name="Alice Laptop")
        self.assertTrue(
            UserDeviceBinding.objects.filter(user=self.employee, device_id="laptop-hardware-uuid-1").exists()
        )

        # 2. Punching from the registered device passes
        assert_device_binding_allowed(self.employee, device_id="laptop-hardware-uuid-1")

        # 3. Punching from a coworker's / unregistered device is blocked
        with self.assertRaises(GraphQLError) as ctx:
            assert_device_binding_allowed(self.employee, device_id="friend-laptop-uuid-2")
        self.assertIn("Unregistered device detected", str(ctx.exception))

    def test_face_re_enrollment_lockdown_and_hr_authorization(self):
        view = FaceExtractView.as_view()

        # Dummy 128-d vector
        dummy_descriptor = [0.05] * 128
        self.employee.face_descriptor = dummy_descriptor
        self.employee.face_enrolled_at = timezone.now()
        self.employee.save()

        # Attempt unauthorized re-enrollment by an ordinary employee
        # Using a dummy 1x1 GIF / PNG for test upload
        dummy_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        from unittest.mock import patch
        with patch("attendance.api_views.extract_face_descriptor_from_bytes", return_value=(dummy_descriptor, 0.99)):
            req = self.factory.post(
                "/api/attendance/face/extract/",
                {"photo_base64": dummy_png, "enroll": "true"},
                format="json",
            )
            force_authenticate(req, user=self.employee)
            resp = view(req)

        # Re-enrollment must be blocked with 403 Forbidden
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Biometric re-enrollment requires prior HR or Admin authorization", resp.data.get("error", ""))

        # Now HR authorizes re-enrollment
        self.employee.re_enrollment_allowed = True
        self.employee.re_enrollment_allowed_by = self.hr
        self.employee.re_enrollment_allowed_at = timezone.now()
        self.employee.save()

        # The employee can now re-enroll once
        # (Mock extract_face_descriptor_from_bytes so test does not depend on local OpenCV models)
        from unittest.mock import patch
        with patch("attendance.api_views.extract_face_descriptor_from_bytes", return_value=(dummy_descriptor, 0.99)):
            req2 = self.factory.post(
                "/api/attendance/face/extract/",
                {"photo_base64": dummy_png, "enroll": "true"},
                format="json",
            )
            force_authenticate(req2, user=self.employee)
            resp2 = view(req2)

            self.assertEqual(resp2.status_code, 200)
            self.assertTrue(resp2.data.get("success"))

            # Verify that re-enrollment permission was automatically revoked
            self.employee.refresh_from_db()
            self.assertFalse(self.employee.re_enrollment_allowed)
            self.assertIsNone(self.employee.re_enrollment_allowed_by)

    def test_face_match_verification_enforced(self):
        # Enrolled face vector
        enrolled_vec = [0.1] * 128
        self.employee.face_descriptor = enrolled_vec
        self.employee.face_enrolled_at = timezone.now()
        self.employee.save()

        from unittest.mock import patch
        with patch("attendance.services.org_requires_face", return_value=True):
            # Matching face: Euclidean distance == 0
            score = assert_face_attendance_allowed(
                self.employee,
                face_descriptor=enrolled_vec,
                face_verified=True,
            )
            self.assertGreater(score, 0.9)

            # Mismatched face: completely different vector
            mismatched_vec = [0.9] * 128
            with self.assertRaises(GraphQLError) as ctx:
                assert_face_attendance_allowed(
                    self.employee,
                    face_descriptor=mismatched_vec,
                    face_verified=True,
                )
            self.assertIn("Face did not match", str(ctx.exception))
