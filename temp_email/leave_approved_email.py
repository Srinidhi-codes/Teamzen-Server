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


def get_leave_approved_email_html(
    employee_name: str,
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    approved_by: str = "",
    remarks: str = "",
    dashboard_url: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Leave Approved notification HTML email."""
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint

    safe_dashboard_url = sanitize_portal_url(dashboard_url, "leaves")
    safe_company_url = sanitize_portal_url(company_url)

    date_str = f"{start_date} to {end_date}" if start_date != end_date else start_date
    duration_str = f"{duration} day(s)" if not str(duration).endswith("day") and not str(duration).endswith("days") else str(duration)

    rows = [
        ("Leave Type", leave_type),
        ("Dates", date_str),
        ("Duration", duration_str),
    ]
    if approved_by:
        rows.append(("Approved By", approved_by))
    rows.append(("Status", "Approved"))

    remarks_markup = ""
    if remarks:
        remarks_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 20px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    remarks,
                    title="Approver Remarks",
                    level="info",
                )}
            </td>
        </tr>
        """

    notice_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
            {alert_box_html(
                "Your schedule and leave balance have been updated automatically. You can check your remaining balances in the employee portal.",
                title="Schedule Updated",
                level="info",
            )}
        </td>
    </tr>
    """

    cta_markup = f"""
    <tr>
        <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
            {button_html("View My Leaves", safe_dashboard_url, accent)}
        </td>
    </tr>
    """

    body = f"""
        {hero_section_html(
            headline="Leave Request Approved",
            badge_label="LEAVE APPROVED",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Your leave request has been approved. The details of your approved time off are summarized below.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Leave Summary")}
            </td>
        </tr>

        {remarks_markup}
        {notice_markup}
        {cta_markup}
    """

    return get_base_template(
        title="Leave Request Approved",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=safe_company_url,
        show_header_title=False,
    )
