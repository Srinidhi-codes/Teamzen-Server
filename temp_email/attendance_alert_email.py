from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    resolve_portal_url,
    sanitize_portal_url,
)


def get_attendance_alert_email_html(
    recipient_name: str,
    alert_title: str = "Low Weekly Attendance",
    message: str = "",
    period: str = "Previous Week",
    recorded_attendance: str = "",
    required_threshold: str = "80% (4/5 days)",
    status_text: str = "Below Threshold",
    action_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
    logo_url: str = "",
) -> str:
    """
    Production-ready email template for attendance alerts (low attendance, missing checkouts, etc.).
    Designed to match executive HRMS styling with zero tacky emojis.
    """
    safe_action_url = sanitize_portal_url(action_url, "attendance")
    safe_company_url = sanitize_portal_url(company_url)
    accent = "#D97706"  # Amber
    hero_bg = "#FEF3C7"  # Soft amber

    is_missing_checkout = "checkout" in alert_title.lower() or "check-out" in alert_title.lower()
    if is_missing_checkout:
        accent = "#0284C7"  # Sky blue
        hero_bg = "#E0F2FE"
        badge_label = "ATTENDANCE UPDATE"
        badge_color = "#0369A1"
        badge_bg = "#BAE6FD"
        default_message = (
            "Our automated attendance log indicates a missing clock-out record for your recent shift. "
            "Please review and submit a correction to keep your work records up to date."
        )
    else:
        badge_label = "ATTENDANCE NOTICE"
        badge_color = "#B45309"
        badge_bg = "#FDE68A"
        default_message = (
            "Your logged attendance for the recent period fell below the company threshold. "
            "Please ensure you log your shifts consistently to meet work requirements."
        )

    clean_title = alert_title.strip()
    if clean_title.lower().startswith("notification:"):
        clean_title = clean_title[13:].strip()

    display_message = message or default_message

    # Build key-value rows for the card table
    rows = []
    if period:
        rows.append(("Evaluation Period", period))
    if recorded_attendance:
        rows.append(("Logged Attendance", recorded_attendance))
    if required_threshold and not is_missing_checkout:
        rows.append(("Required Minimum", required_threshold))
    if status_text:
        rows.append(("Status", status_text))

    details_markup = ""
    if rows:
        details_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Attendance Summary")}
            </td>
        </tr>
        """

    notice_box = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
            {alert_box_html(
                "Timely attendance records ensure accurate payroll processing, leave accruals, and policy compliance.",
                title="Policy Reminder",
                level="warning" if not is_missing_checkout else "info",
            )}
        </td>
    </tr>
    """

    cta_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
            {button_html("View Attendance Log", safe_action_url, accent)}
        </td>
    </tr>
    """

    body = f"""
        {hero_section_html(
            headline=clean_title,
            badge_label=badge_label,
            badge_color=badge_color,
            badge_bg=badge_bg,
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{recipient_name or 'there'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    {display_message}
                </p>
            </td>
        </tr>

        {details_markup}
        {notice_box}
        {cta_markup}
    """

    return get_base_template(
        title=clean_title,
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )

