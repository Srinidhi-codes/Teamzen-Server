import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.mail import EmailMultiAlternatives
from temp_email import (
    get_leave_approved_email_html,
    get_leave_rejected_email_html,
    get_leave_cancelled_email_html,
    get_leave_request_email_html,
    get_welcome_email_html,
    get_announcement_email_html,
    get_preboarding_invite_email_html,
    get_onboarding_task_reminder_email_html,
    get_attendance_alert_email_html,
    get_general_notification_email_html,
    get_password_reset_email_html,
    get_login_alert_email_html,
    get_otp_email_html,
    get_payroll_email_html,
    get_document_notification_email_html,
    get_offboarding_email_html,
)

from notifications.email_backends import BrevoHTTPBackend
from django.conf import settings

recipient_email = os.environ.get("TEST_EMAIL", "connectifyappmails@gmail.com")

def send_email(subject, html_content, to_email=None):
    target = to_email or recipient_email
    try:
        msg = EmailMultiAlternatives(
            subject=f"[Preview] {subject}",
            body="Please view this email in an HTML-compatible email client.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[target],
            connection=BrevoHTTPBackend()
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"Delivered: '{subject}' -> {target}")
    except Exception as e:
        print(f"Failed to deliver '{subject}' to {target}: {e}")


emails_to_send = [
    ("Weekly Attendance Alert", get_attendance_alert_email_html(
        recipient_name="Shreyas R",
        alert_title="Low Weekly Attendance",
        message="Your attendance for the last week was 1/5 days. Please ensure you maintain at least 80% attendance.",
        recorded_attendance="1/5 days (20%)",
        required_threshold="80% (4/5 days)",
    )),
    ("Overdue Onboarding Task", get_onboarding_task_reminder_email_html(
        recipient_name="Shreyas R",
        task_title="Upload ID proof",
        hire_name="Shreyas R",
        days_overdue=24,
        is_overdue=True,
    )),
    ("General System Notification", get_general_notification_email_html(
        recipient_name="Shreyas R",
        title="Policy Update Acknowledged",
        message="Your annual compliance acknowledgement has been recorded in the company register.",
        category="Compliance",
        details=[("Module", "Code of Conduct 2026"), ("Timestamp", "Today, 10:30 AM"), ("Status", "Verified")],
    )),
    ("Leave Approved", get_leave_approved_email_html(employee_name="Srinidhi", leave_type="Sick Leave", start_date="2026-09-22", end_date="2026-09-23", duration="2")),
    ("Leave Rejected", get_leave_rejected_email_html(employee_name="Srinidhi", leave_type="Annual Leave", start_date="2026-10-01", end_date="2026-10-05", duration="5", reason="Peak release sprint scheduled during requested dates")),
    ("Leave Cancelled", get_leave_cancelled_email_html(employee_name="Srinidhi", leave_type="Casual Leave", start_date="2026-09-25", end_date="2026-09-25", duration="1")),
    ("Leave Request", get_leave_request_email_html(manager_name="Manager", employee_name="Srinidhi", leave_type="Unpaid Leave", start_date="2026-11-01", end_date="2026-11-02", duration="2", reason="Personal family commitment")),
    ("Welcome Email", get_welcome_email_html(employee_name="Srinidhi", employee_email="srinidhiachar2518@gmail.com", designation="Software Engineer", department="Engineering", joining_date="2026-09-21", temp_password="Tz#9824X")),
    ("Announcement", get_announcement_email_html(employee_name="Srinidhi", announcement_title="New Policy Updates", announcement_body="We have updated our internal workplace policies. Please review them at your earliest convenience.", category="HR", priority="high")),
    ("Onboarding Invite", get_preboarding_invite_email_html(employee_name="Srinidhi", designation="Software Engineer", join_date="2026-09-21")),
    ("Password Reset", get_password_reset_email_html(employee_name="Srinidhi", reset_url="")),
    ("Login Alert", get_login_alert_email_html(recipient_name="Srinidhi", actor_name="Admin", actor_email="admin@example.com", login_time="2026-09-21 10:00:00")),
    ("OTP Verification", get_otp_email_html(employee_name="Srinidhi", otp_code="123456")),
    ("Payroll Statement", get_payroll_email_html(employee_name="Srinidhi", month="September 2026", gross_salary="₹ 85,000", net_salary="₹ 76,400", total_deductions="₹ 8,600")),
    ("Document Notification", get_document_notification_email_html(recipient_name="Srinidhi", document_name="Non-Disclosure Agreement", document_category="Legal", status="Pending Signature")),
    ("Offboarding Clearance", get_offboarding_email_html(recipient_name="Srinidhi", employee_name="Srinidhi", last_working_day="Oct 31, 2026")),
]

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    to_addr = recipient_email
    for i, a in enumerate(args):
        if a.startswith("--to="):
            to_addr = a.split("=", 1)[1]
        elif a == "--to" and i + 1 < len(args):
            to_addr = args[i + 1]

    if "--send-all" in args:
        print(f"Sending all {len(emails_to_send)} preview emails to {to_addr}...")
        for subject, html in emails_to_send:
            send_email(subject, html, to_email=to_addr)
    elif "--send-sample" in args or "--send" in args:
        samples = [emails_to_send[0], emails_to_send[1]]
        print(f"Sending 2 sample preview emails (Attendance + Overdue Task) to {to_addr}...")
        for subject, html in samples:
            send_email(subject, html, to_email=to_addr)
    else:
        print(f"Generated {len(emails_to_send)} email templates ready for delivery.")
        print(f"Target address configured: {recipient_email}")
        print("To send live preview emails, run:")
        print("  python send_test_emails.py --send")
        print("  python send_test_emails.py --send --to your-email@domain.com")

