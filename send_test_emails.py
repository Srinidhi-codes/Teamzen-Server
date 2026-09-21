import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.mail import EmailMultiAlternatives
from temp_email.leave_approved_email import get_leave_approved_email_html
from temp_email.leave_rejected_email import get_leave_rejected_email_html
from temp_email.leave_cancelled_email import get_leave_cancelled_email_html
from temp_email.leave_request_email import get_leave_request_email_html
from temp_email.welcome_email import get_welcome_email_html
from temp_email.announcement_email import get_announcement_email_html
from temp_email.onboarding_email import get_preboarding_invite_email_html
from temp_email.password_reset_email import get_password_reset_email_html
from temp_email.login_alert_email import get_login_alert_email_html
from temp_email.otp_email import get_otp_email_html
from temp_email.payroll_email import get_payroll_email_html

recipient_email = "srinidhiachar2518@gmail.com"

def send_email(subject, html_content):
    try:
        msg = EmailMultiAlternatives(
            subject=f"[Test] {subject}",
            body="Please view this email in an HTML compatible client.",
            from_email="no-reply@teamzen.com",
            to=[recipient_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"Sent {subject}")
    except Exception as e:
        print(f"Failed to send {subject}: {e}")

emails_to_send = [
    ("Leave Approved", get_leave_approved_email_html(employee_name="Srinidhi", leave_type="Sick Leave", start_date="2026-09-22", end_date="2026-09-23", duration="2")),
    ("Leave Rejected", get_leave_rejected_email_html(employee_name="Srinidhi", leave_type="Annual Leave", start_date="2026-10-01", end_date="2026-10-05", duration="5")),
    ("Leave Cancelled", get_leave_cancelled_email_html(employee_name="Srinidhi", leave_type="Casual Leave", start_date="2026-09-25", end_date="2026-09-25", duration="1")),
    ("Leave Request", get_leave_request_email_html(manager_name="Manager", employee_name="Srinidhi", leave_type="Unpaid Leave", start_date="2026-11-01", end_date="2026-11-02", duration="2")),
    ("Welcome Email", get_welcome_email_html(employee_name="Srinidhi", employee_email="srinidhiachar2518@gmail.com", designation="Software Engineer", joining_date="2026-09-21")),
    ("Announcement", get_announcement_email_html(employee_name="Srinidhi", announcement_title="New Policy Updates", announcement_body="We have updated our internal policies.", category="HR", priority="high")),
    ("Onboarding", get_preboarding_invite_email_html(employee_name="Srinidhi", designation="Software Engineer", join_date="2026-09-21")),
    ("Password Reset", get_password_reset_email_html(employee_name="Srinidhi", reset_url="https://example.com/reset")),
    ("Login Alert", get_login_alert_email_html(recipient_name="Srinidhi", actor_name="Admin", actor_email="admin@example.com", login_time="2026-09-21 10:00:00")),
    ("OTP", get_otp_email_html(employee_name="Srinidhi", otp_code="123456")),
    ("Payroll", get_payroll_email_html(employee_name="Srinidhi", month="September 2026")),
]

for subject, html in emails_to_send:
    send_email(subject, html)
