from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_offboarding_email_html(
    recipient_name: str,
    title: str = "Offboarding Update",
    message: str = "",
    employee_name: str = "",
    last_working_day: str = "",
    clearance_status: str = "In Progress",
    action_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
    logo_url: str = "",
) -> str:
    """Generate offboarding / exit clearance notification email."""
    safe_action_url = sanitize_portal_url(action_url, "offboarding")
    safe_company_url = sanitize_portal_url(company_url)
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint

    rows = []
    if employee_name:
        rows.append(("Employee", employee_name))
    if last_working_day:
        rows.append(("Last Working Day", last_working_day))
    if clearance_status:
        rows.append(("Clearance Status", clearance_status))

    clean_title = title.strip()
    if clean_title.lower().startswith("notification:"):
        clean_title = clean_title[13:].strip()

    body = f"""
        {hero_section_html(
            headline=clean_title,
            badge_label="EXIT FORMALITIES",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{recipient_name or 'there'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    {message or 'There is an update on exit clearance requirements.'}
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Offboarding Details")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Please ensure all assigned company assets and department clearances are fulfilled prior to your final settlement.",
                    title="Clearance Checklist",
                    level="neutral",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("View Offboarding Status", safe_action_url, accent)}
            </td>
        </tr>
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
