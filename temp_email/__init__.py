# Export all email templates for easy reusability
from .base_template import (
    get_base_template,
    button_html,
    info_row_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    resolve_portal_url,
    sanitize_portal_url,
)
from .general_notification_email import get_general_notification_email_html
from .attendance_alert_email import get_attendance_alert_email_html
from .onboarding_email import (
    get_onboarding_task_reminder_email_html,
    get_preboarding_invite_email_html,
    get_document_rejected_email_html,
)
from .leave_request_email import get_leave_request_email_html
from .leave_approved_email import get_leave_approved_email_html
from .leave_rejected_email import get_leave_rejected_email_html
from .leave_cancelled_email import get_leave_cancelled_email_html
from .welcome_email import get_welcome_email_html
from .announcement_email import get_announcement_email_html
from .otp_email import get_otp_email_html
from .password_reset_email import get_password_reset_email_html
from .payroll_email import get_payroll_email_html
from .login_alert_email import get_login_alert_email_html
from .document_email import get_document_notification_email_html
from .offboarding_email import get_offboarding_email_html

__all__ = [
    "get_base_template",
    "button_html",
    "info_row_html",
    "status_badge_html",
    "card_table_html",
    "alert_box_html",
    "hero_section_html",
    "resolve_portal_url",
    "sanitize_portal_url",
    "get_general_notification_email_html",
    "get_attendance_alert_email_html",
    "get_onboarding_task_reminder_email_html",
    "get_preboarding_invite_email_html",
    "get_document_rejected_email_html",
    "get_leave_request_email_html",
    "get_leave_approved_email_html",
    "get_leave_rejected_email_html",
    "get_leave_cancelled_email_html",
    "get_welcome_email_html",
    "get_announcement_email_html",
    "get_otp_email_html",
    "get_password_reset_email_html",
    "get_payroll_email_html",
    "get_login_alert_email_html",
    "get_document_notification_email_html",
    "get_offboarding_email_html",
]
