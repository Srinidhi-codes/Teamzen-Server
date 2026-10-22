"""
Email Templates Registry for Teamzen HRMS
Defines the standard catalog of email automations, default contents, tokens,
and rendering utilities.
"""
from typing import Dict, Any, List, Optional
import re
from temp_email.base_template import (
    get_base_template,
    button_html,
    alert_box_html,
    resolve_portal_url,
    sanitize_portal_url,
)

DEFAULT_EMAIL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "leave_request": {
        "key": "leave_request",
        "name": "Leave Request Submitted (To Approver)",
        "category": "Leave Management",
        "description": "Sent to managers and HR when an employee submits a new leave request.",
        "default_subject": "New Leave Request from {{employee_name}}",
        "default_headline": "New Leave Application",
        "default_body": "<p>Hello <b>{{manager_name}}</b>,</p><p><b>{{employee_name}}</b> has applied for <b>{{duration}} day(s)</b> of <b>{{leave_type}}</b> from <b>{{from_date}}</b> to <b>{{to_date}}</b>.</p><p><b>Reason for leave:</b><br>{{reason}}</p><p>Please review and approve or decline this request at your earliest convenience.</p>",
        "default_cta_text": "Review Leave Request",
        "default_cta_url": "/leaves",
        "default_footer": "Need to adjust leave policies? Visit your HR settings.",
        "available_tokens": [
            "{{employee_name}}",
            "{{manager_name}}",
            "{{leave_type}}",
            "{{from_date}}",
            "{{to_date}}",
            "{{duration}}",
            "{{reason}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "employee_name": "Alex Johnson",
            "manager_name": "Sarah Connor",
            "leave_type": "Privilege Leave",
            "from_date": "Oct 24, 2026",
            "to_date": "Oct 28, 2026",
            "duration": "4",
            "reason": "Attending family wedding and travel.",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/leaves",
        }
    },
    "leave_approved": {
        "key": "leave_approved",
        "name": "Leave Request Approved (To Employee)",
        "category": "Leave Management",
        "description": "Sent to the employee as soon as their leave request is approved.",
        "default_subject": "Your {{leave_type}} Request has been Approved",
        "default_headline": "Leave Request Approved",
        "default_body": "<p>Hello <b>{{employee_name}}</b>,</p><p>Great news! Your request for <b>{{duration}} day(s)</b> of <b>{{leave_type}}</b> from <b>{{from_date}}</b> to <b>{{to_date}}</b> has been approved by <b>{{actor_name}}</b>.</p><p>Enjoy your time off! Your leave balances have been updated in your employee portal.</p>",
        "default_cta_text": "View Leave Details",
        "default_cta_url": "/leaves",
        "default_footer": "Have a restful time off!",
        "available_tokens": [
            "{{employee_name}}",
            "{{actor_name}}",
            "{{leave_type}}",
            "{{from_date}}",
            "{{to_date}}",
            "{{duration}}",
            "{{remarks}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "employee_name": "Alex Johnson",
            "actor_name": "Sarah Connor (Manager)",
            "leave_type": "Privilege Leave",
            "from_date": "Oct 24, 2026",
            "to_date": "Oct 28, 2026",
            "duration": "4",
            "remarks": "Approved. Please ensure handoff notes are shared.",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/leaves",
        }
    },
    "leave_rejected": {
        "key": "leave_rejected",
        "name": "Leave Request Declined (To Employee)",
        "category": "Leave Management",
        "description": "Sent to the employee if their leave request cannot be approved.",
        "default_subject": "Update on your {{leave_type}} Request",
        "default_headline": "Leave Request Declined",
        "default_body": "<p>Hello <b>{{employee_name}}</b>,</p><p>Your request for <b>{{duration}} day(s)</b> of <b>{{leave_type}}</b> from <b>{{from_date}}</b> to <b>{{to_date}}</b> was reviewed and declined by <b>{{actor_name}}</b>.</p><p><b>Reason / Comments:</b><br>{{reason}}</p><p>If you have any questions, please speak directly with your reporting manager.</p>",
        "default_cta_text": "Open Leave Portal",
        "default_cta_url": "/leaves",
        "default_footer": "You can submit an alternative date range if needed.",
        "available_tokens": [
            "{{employee_name}}",
            "{{actor_name}}",
            "{{leave_type}}",
            "{{from_date}}",
            "{{to_date}}",
            "{{duration}}",
            "{{reason}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "employee_name": "Alex Johnson",
            "actor_name": "Sarah Connor",
            "leave_type": "Casual Leave",
            "from_date": "Nov 02, 2026",
            "to_date": "Nov 04, 2026",
            "duration": "3",
            "reason": "Critical project milestone release scheduled for this week.",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/leaves",
        }
    },
    "leave_cancelled": {
        "key": "leave_cancelled",
        "name": "Leave Request Cancelled",
        "category": "Leave Management",
        "description": "Sent to manager and employee when a leave request is cancelled.",
        "default_subject": "Leave Request Cancelled: {{leave_type}}",
        "default_headline": "Leave Cancelled",
        "default_body": "<p>Hello <b>{{employee_name}}</b>,</p><p>The leave application for <b>{{duration}} day(s)</b> of <b>{{leave_type}}</b> (from <b>{{from_date}}</b> to <b>{{to_date}}</b>) has been successfully cancelled.</p><p>Your leave balances have been restored accordingly.</p>",
        "default_cta_text": "View Leave Balance",
        "default_cta_url": "/leaves",
        "default_footer": "Restored leave balance is immediately available for future applications.",
        "available_tokens": [
            "{{employee_name}}",
            "{{leave_type}}",
            "{{from_date}}",
            "{{to_date}}",
            "{{duration}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "employee_name": "Alex Johnson",
            "leave_type": "Sick Leave",
            "from_date": "Oct 19, 2026",
            "to_date": "Oct 20, 2026",
            "duration": "2",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/leaves",
        }
    },
    "login_alert": {
        "key": "login_alert",
        "name": "New Device / Location Login Alert",
        "category": "Security & Access",
        "description": "Sent immediately when an account sign-in occurs from a new device, browser, or location.",
        "default_subject": "Security Alert: New Sign-in to your {{company_name}} account",
        "default_headline": "New Sign-in Detected",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>We detected a new sign-in to your <b>{{company_name}}</b> account with the following details:</p><p>• <b>Time:</b> {{login_time}}<br>• <b>Device:</b> {{device}}<br>• <b>IP Address:</b> {{ip_address}}<br>• <b>Location:</b> {{location}}</p><p><b>Was this you?</b> If you recognize this activity, no action is needed. If you did not sign in, please secure your account immediately by changing your password.</p>",
        "default_cta_text": "Review Security & Active Sessions",
        "default_cta_url": "/profile?tab=security",
        "default_footer": "Protecting your account security is our top priority.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{login_time}}",
            "{{device}}",
            "{{ip_address}}",
            "{{location}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "David Miller",
            "login_time": "Oct 20, 2026 at 11:42 AM",
            "device": "Chrome on macOS 15.0",
            "ip_address": "49.207.214.88",
            "location": "Bengaluru, Karnataka, India",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/profile?tab=security",
        }
    },
    "attendance_alert": {
        "key": "attendance_alert",
        "name": "Attendance Review & Threshold Notice",
        "category": "Attendance",
        "description": "Sent to employees when attendance drops below company threshold or misses check-ins.",
        "default_subject": "Attendance Notice: {{period}}",
        "default_headline": "Attendance Review Required",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>This is a notification regarding your attendance record for <b>{{period}}</b>.</p><p>Your recorded attendance is currently at <b>{{recorded_attendance}}</b>, which is below the expected benchmark of <b>{{required_threshold}}</b>.</p><p>If you have missing check-ins or were on approved duty/leave, please submit an attendance correction request through your portal.</p>",
        "default_cta_text": "View Attendance & Regularize",
        "default_cta_url": "/attendance",
        "default_footer": "Regularizing attendance within 48 hours ensures accurate monthly payroll processing.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{period}}",
            "{{recorded_attendance}}",
            "{{required_threshold}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Priya Sharma",
            "period": "Last Week (Oct 12 - Oct 17)",
            "recorded_attendance": "60% (3 of 5 days)",
            "required_threshold": "85%",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/attendance",
        }
    },
    "welcome": {
        "key": "welcome",
        "name": "Welcome New Employee & Credentials",
        "category": "Employee Lifecycle",
        "description": "Sent to newly onboarded team members with portal login instructions.",
        "default_subject": "Welcome to {{company_name}}, {{recipient_name}}!",
        "default_headline": "Welcome to the Team!",
        "default_body": "<p>Dear <b>{{recipient_name}}</b>,</p><p>A warm welcome to <b>{{company_name}}</b>! We are thrilled to have you join our team as <b>{{designation}}</b> in the <b>{{department}}</b> department, starting <b>{{joining_date}}</b>.</p><p>Your corporate account has been set up. Click the button below to sign in and complete your onboarding profile.</p>",
        "default_cta_text": "Log In to Your Portal",
        "default_cta_url": "/login",
        "default_footer": "If you have any questions on your first day, your manager is ready to assist.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{designation}}",
            "{{department}}",
            "{{joining_date}}",
            "{{manager_name}}",
            "{{temp_password}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Michael Chang",
            "designation": "Senior Product Designer",
            "department": "Design & UX",
            "joining_date": "November 01, 2026",
            "manager_name": "Sarah Connor",
            "temp_password": "Teamzen@2026!",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/login",
        }
    },
    "password_reset": {
        "key": "password_reset",
        "name": "Password Reset Instructions",
        "category": "Security & Access",
        "description": "Sent when an employee or administrator requests a password reset.",
        "default_subject": "Reset your {{company_name}} password",
        "default_headline": "Password Reset Request",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>We received a request to reset the password for your account at <b>{{company_name}}</b>.</p><p>Click the button below to set a new password. This link is secure and will expire in 15 minutes.</p><p><i>If you did not request this change, please ignore this email; your account remains secure.</i></p>",
        "default_cta_text": "Reset My Password",
        "default_cta_url": "/reset-password",
        "default_footer": "For security reasons, never share this link with anyone.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Michael Chang",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/reset-password?token=xyz987abc",
        }
    },
    "payroll": {
        "key": "payroll",
        "name": "Monthly Payslip Generated",
        "category": "Payroll & Compensation",
        "description": "Sent to employees once monthly payroll is finalized and salary slips are ready.",
        "default_subject": "Your Payslip for {{month}} is now available",
        "default_headline": "Monthly Payslip Ready",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>Your salary slip for <b>{{month}}</b> has been processed and is now available in your self-service portal.</p><p>You can securely view your earnings breakdown, tax deductions, and download the official PDF copy anytime.</p>",
        "default_cta_text": "Download Salary Slip",
        "default_cta_url": "/payroll",
        "default_footer": "For payroll inquiries or tax declaration updates, reach out to your finance department.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{month}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Rachel Adams",
            "month": "September 2026",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/payroll",
        }
    },
    "announcement": {
        "key": "announcement",
        "name": "Company Announcement",
        "category": "General",
        "description": "Sent when leadership or HR publishes an organization-wide update or announcement.",
        "default_subject": "Company Announcement: {{announcement_title}}",
        "default_headline": "Company Announcement",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>A new announcement has been published for all team members:</p><div style='padding:16px;background-color:#F8FAFC;border-left:4px solid #0F766E;border-radius:6px;margin:16px 0;'><h3 style='margin:0 0 8px 0;color:#0F172A;'>{{announcement_title}}</h3><div>{{announcement_body}}</div></div><p>Click below to join the discussion on the company feed.</p>",
        "default_cta_text": "View on Company Feed",
        "default_cta_url": "/feed",
        "default_footer": "Teamzen Organization Broadcast",
        "available_tokens": [
            "{{recipient_name}}",
            "{{announcement_title}}",
            "{{announcement_body}}",
            "{{posted_by}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Teamzen Team",
            "announcement_title": "Annual Company Retreat & Q4 Kickoff Announced!",
            "announcement_body": "We are excited to share the dates and location for our upcoming company retreat. Check out the schedule, travel arrangements, and agenda items on the portal.",
            "posted_by": "People Operations",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/feed",
        }
    },
    "document": {
        "key": "document",
        "name": "Document Verification & Requests",
        "category": "Documents",
        "description": "Sent when an employee document is approved, requires signing, or needs re-upload.",
        "default_subject": "Document Update: {{document_name}}",
        "default_headline": "Document Action Required",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>There is an update on your document <b>{{document_name}}</b> (Category: <b>{{category}}</b>).</p><p><b>Current Status:</b> {{status}}</p><p>Please open your documents workspace to take any necessary action or download the verified copy.</p>",
        "default_cta_text": "Open Documents Workspace",
        "default_cta_url": "/documents",
        "default_footer": "Official company documentation hub.",
        "available_tokens": [
            "{{recipient_name}}",
            "{{document_name}}",
            "{{category}}",
            "{{status}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "John Doe",
            "document_name": "Non-Disclosure Agreement (NDA)",
            "category": "Legal & Compliance",
            "status": "Verified & Approved",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/documents",
        }
    },
    "general_notification": {
        "key": "general_notification",
        "name": "General Workspace Notifications",
        "category": "General",
        "description": "Sent for mentions, feed comments, and other general system notifications.",
        "default_subject": "{{title}}",
        "default_headline": "{{title}}",
        "default_body": "<p>Hello <b>{{recipient_name}}</b>,</p><p>{{message}}</p><p>Click below to jump directly to your workspace.</p>",
        "default_cta_text": "Open Workspace",
        "default_cta_url": "/dashboard",
        "default_footer": "Teamzen Notification System",
        "available_tokens": [
            "{{recipient_name}}",
            "{{title}}",
            "{{message}}",
            "{{company_name}}",
            "{{action_url}}",
        ],
        "sample_context": {
            "recipient_name": "Sarah Connor",
            "title": "New Feed Mention",
            "message": "Alex Johnson mentioned you in a post: '@Sarah Connor please check the draft.'",
            "company_name": "Teamzen Corp",
            "action_url": "https://portal.teamzen.io/feed",
        }
    }
}


def substitute_tokens(text: str, context: Dict[str, Any]) -> str:
    """Replace {{token_name}} placeholders with values from context."""
    if not text:
        return ""
    result = text
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        str_val = str(val if val is not None else "")
        result = result.replace(placeholder, str_val)
    return result


def render_email_html(
    template_setting, # Can be EmailTemplateSetting or dict
    context: Dict[str, Any],
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """
    Renders custom or default email template into a full responsive HTML layout.
    """
    key = getattr(template_setting, "template_key", None) or (template_setting.get("key") if isinstance(template_setting, dict) else "general_notification")
    default_spec = DEFAULT_EMAIL_TEMPLATES.get(key, DEFAULT_EMAIL_TEMPLATES["general_notification"])

    is_raw_html_mode = getattr(template_setting, "is_raw_html_mode", False) if hasattr(template_setting, "is_raw_html_mode") else (template_setting.get("is_raw_html_mode", False) if isinstance(template_setting, dict) else False)
    custom_full_html = getattr(template_setting, "custom_full_html", None) if hasattr(template_setting, "custom_full_html") else (template_setting.get("custom_full_html") if isinstance(template_setting, dict) else None)

    clean_company = (company_name or "").strip() or "Teamzen"

    merged_context = dict(context)
    if "company_name" not in merged_context:
        merged_context["company_name"] = clean_company

    # If raw HTML / JSX mode is active and custom full HTML is supplied
    if is_raw_html_mode and custom_full_html and custom_full_html.strip():
        rendered_raw = substitute_tokens(custom_full_html, merged_context)
        # If it already includes a full HTML document, return as is
        if "<html" in rendered_raw.lower() or "<!doctype" in rendered_raw.lower():
            return rendered_raw
        # Otherwise wrap cleanly in the base responsive wrapper
        return get_base_template(
            title=default_spec.get("default_headline", "Notification"),
            body_content=rendered_raw,
            accent_color="#0F766E",
            footer_text=f"{clean_company} HRMS",
            company_url=company_url or resolve_portal_url(),
            show_header_title=False,
            eyebrow_text=clean_company,
        )

    custom_headline = getattr(template_setting, "custom_headline", None) if hasattr(template_setting, "custom_headline") else (template_setting.get("custom_headline") if isinstance(template_setting, dict) else None)
    custom_body = getattr(template_setting, "custom_body", None) if hasattr(template_setting, "custom_body") else (template_setting.get("custom_body") if isinstance(template_setting, dict) else None)
    custom_cta_text = getattr(template_setting, "custom_cta_text", None) if hasattr(template_setting, "custom_cta_text") else (template_setting.get("custom_cta_text") if isinstance(template_setting, dict) else None)
    custom_cta_url = getattr(template_setting, "custom_cta_url", None) if hasattr(template_setting, "custom_cta_url") else (template_setting.get("custom_cta_url") if isinstance(template_setting, dict) else None)
    custom_footer = getattr(template_setting, "custom_footer", None) if hasattr(template_setting, "custom_footer") else (template_setting.get("custom_footer") if isinstance(template_setting, dict) else None)

    headline = custom_headline or default_spec["default_headline"]
    raw_body = custom_body or default_spec["default_body"]
    cta_text = custom_cta_text or default_spec["default_cta_text"]
    cta_url = custom_cta_url or default_spec.get("default_cta_url", "/dashboard")
    footer_text = custom_footer or default_spec.get("default_footer", f"{clean_company} Workspace")

    rendered_headline = substitute_tokens(headline, merged_context)
    rendered_body = substitute_tokens(raw_body, merged_context)
    rendered_cta_text = substitute_tokens(cta_text, merged_context)
    rendered_footer = substitute_tokens(footer_text, merged_context)

    # Resolve target URL
    raw_resolved_url = substitute_tokens(cta_url, merged_context)
    if raw_resolved_url.startswith("http"):
        final_action_url = raw_resolved_url
    else:
        final_action_url = resolve_portal_url(raw_resolved_url)

    # Build internal HTML table rows with standard corporate padding
    body_rows = [
        f"""
        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 18px 36px; background-color: #FFFFFF;">
                <div style="font-size: 15px; line-height: 1.7; color: #334155; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                    {rendered_body}
                </div>
            </td>
        </tr>
        """
    ]

    # Action CTA button: text is first argument, URL is second argument!
    if rendered_cta_text and final_action_url:
        btn_markup = button_html(rendered_cta_text, final_action_url)
        body_rows.append(
            f"""
            <tr>
                <td bgcolor="#FFFFFF" style="padding: 6px 36px 24px 36px; background-color: #FFFFFF; text-align: left;">
                    {btn_markup}
                </td>
            </tr>
            """
        )

    # Contextual footer hint / callout card
    if rendered_footer:
        body_rows.append(
            f"""
            <tr>
                <td bgcolor="#FFFFFF" style="padding: 4px 36px 28px 36px; background-color: #FFFFFF;">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;">
                        <tr>
                            <td style="padding: 12px 18px; font-size: 13px; color: #64748B; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                                {rendered_footer}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            """
        )

    full_inner_content = "".join(body_rows)

    return get_base_template(
        title=rendered_headline,
        body_content=full_inner_content,
        accent_color="#0F766E",
        footer_text=f"{clean_company} HRMS",
        company_url=company_url or resolve_portal_url(),
        show_header_title=True,
        eyebrow_text=clean_company,
    )


def resolve_template_key(target_type: Optional[str], verb: Optional[str] = "", extra_context: Optional[dict] = None) -> str:
    """Map target_type & verb to the corresponding template key."""
    tt = str(target_type or "").lower().strip()
    v = str(verb or "").lower().strip()
    ctx = extra_context or {}

    if "leave" in tt or "leave" in v:
        if v in ("approved", "leave_approved") or ctx.get("status") == "approved":
            return "leave_approved"
        elif v in ("rejected", "declined", "leave_rejected") or ctx.get("status") == "rejected":
            return "leave_rejected"
        elif v in ("cancelled", "leave_cancelled") or ctx.get("status") == "cancelled":
            return "leave_cancelled"
        return "leave_request"

    if "login" in tt or "login" in v or "sign-in" in v:
        return "login_alert"

    if "attendance" in tt or "attendance" in v:
        return "attendance_alert"

    if "welcome" in tt or "welcome" in v:
        return "welcome"

    if "payroll" in tt or "payslip" in tt or "payslip" in v:
        return "payroll"

    if "announcement" in tt or "announcement" in v:
        return "announcement"

    if "document" in tt:
        return "document"

    if "password" in tt or "password" in v:
        return "password_reset"

    return "general_notification"
