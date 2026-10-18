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


def get_leave_request_email_html(
    manager_name: str,
    employee_name: str,
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    reason: str = "",
    approval_url: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Leave Request notification HTML email (sent to manager)."""
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint

    safe_approval_url = sanitize_portal_url(approval_url, "leaves", is_admin=True)
    safe_company_url = sanitize_portal_url(company_url, is_admin=True)

    date_str = f"{start_date} to {end_date}" if start_date != end_date else start_date
    duration_str = f"{duration} day(s)" if not str(duration).endswith("day") and not str(duration).endswith("days") else str(duration)

    rows = [
        ("Employee", employee_name),
        ("Leave Type", leave_type),
        ("Dates", date_str),
        ("Duration", duration_str),
    ]

    reason_markup = ""
    if reason:
        reason_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 20px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    reason,
                    title="Reason Stated",
                    level="neutral",
                )}
            </td>
        </tr>
        """

    notice_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
            {alert_box_html(
                "Please check team availability and project coverage before approving or declining this request.",
                title="Manager Action",
                level="info",
            )}
        </td>
    </tr>
    """

    cta_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
            {button_html("Review & Take Action", safe_approval_url, accent)}
        </td>
    </tr>
    """

    body = f"""
        {hero_section_html(
            headline="New Leave Request",
            badge_label="LEAVE REQUEST",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{manager_name or 'Manager'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    <strong style="color: #0F172A;">{employee_name}</strong> has submitted a new leave request. Please review the details below and take action through your manager dashboard.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Leave Request Details")}
            </td>
        </tr>

        {reason_markup}
        {notice_markup}
        {cta_markup}
    """

    return get_base_template(
        title="New Leave Request",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=safe_company_url,
        show_header_title=False,
    )

