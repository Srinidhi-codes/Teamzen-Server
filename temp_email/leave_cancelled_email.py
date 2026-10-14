from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_leave_cancelled_email_html(
    employee_name: str,
    manager_name: str = "Manager",
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    cancelled_by: str = "",
    dashboard_url: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Leave Request Cancelled notification HTML email (sent to manager)."""
    accent = "#EA580C"
    hero_bg = "#FFF7ED"
    safe_dashboard_url = sanitize_portal_url(dashboard_url, "leaves", is_admin=True)
    safe_company_url = sanitize_portal_url(company_url, is_admin=True)

    date_str = f"{start_date} to {end_date}" if start_date != end_date else start_date
    duration_str = f"{duration} day(s)" if not str(duration).endswith("day") and not str(duration).endswith("days") else str(duration)

    rows = [
        ("Employee", employee_name),
        ("Leave Type", leave_type),
        ("Dates", date_str),
        ("Duration", duration_str),
        ("Cancelled By", cancelled_by if cancelled_by else employee_name),
    ]

    body = f"""
        {hero_section_html(
            headline="Leave Request Cancelled",
            badge_label="CANCELLED",
            badge_color="#C2410C",
            badge_bg="#FFEDD5",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{manager_name or 'Manager'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    A previously scheduled leave request has been cancelled. The team schedule and employee leave balance have been restored automatically.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Cancelled Leave Summary")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "No further action is required. You can review current team schedules and availability in your admin dashboard.",
                    title="Information",
                    level="info",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("View Team Leaves", safe_dashboard_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title="Leave Request Cancelled",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=safe_company_url,
        show_header_title=False,
    )
