from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_announcement_email_html(
    employee_name: str = "",
    announcement_title: str = "",
    announcement_body: str = "",
    category: str = "General",
    posted_by: str = "HR Department",
    posted_date: str = "",
    action_url: str = "",
    action_text: str = "View in Workspace",
    priority: str = "normal",  # normal, high, urgent
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
    image_url: str = None,
) -> str:
    """Generate the Company Announcement HTML email with clean corporate styling."""
    safe_action_url = sanitize_portal_url(action_url, "notifications")
    safe_company_url = sanitize_portal_url(company_url)
    priority_configs = {
        "normal": {"accent": "#0F766E", "hero_bg": "#CCFBF1", "badge_color": "#0F766E", "badge_bg": "#FFFFFF", "label": "COMPANY ANNOUNCEMENT"},
        "high": {"accent": "#0F766E", "hero_bg": "#CCFBF1", "badge_color": "#0F766E", "badge_bg": "#FFFFFF", "label": "IMPORTANT NOTICE"},
        "urgent": {"accent": "#0F766E", "hero_bg": "#CCFBF1", "badge_color": "#0F766E", "badge_bg": "#FFFFFF", "label": "URGENT ANNOUNCEMENT"},
    }

    cfg = priority_configs.get(str(priority).lower(), priority_configs["normal"])
    accent = cfg["accent"]
    hero_bg = cfg["hero_bg"]
    clean_title = announcement_title or "Company Announcement"

    image_html = ""
    if image_url:
        image_html = f"""
        <div style="margin: 20px 0; text-align: center;">
            <img src="{image_url}" alt="Announcement Attachment" style="max-width: 100%; border-radius: 10px; border: 1px solid #E2E8F0;" />
        </div>
        """

    rows = [
        ("Category", category),
    ]
    if posted_by:
        rows.append(("Posted By", posted_by))
    if posted_date:
        rows.append(("Date Posted", posted_date))

    body = f"""
        {hero_section_html(
            headline=clean_title,
            badge_label=cfg["label"],
            badge_color=cfg["badge_color"],
            badge_bg=cfg["badge_bg"],
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name or 'there'}</strong>,
                </p>
                {image_html}
                <div style="margin: 0 0 20px 0; font-size: 15px; color: #334155; line-height: 1.7; white-space: pre-wrap;">
                    {announcement_body}
                </div>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Announcement Overview")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html(action_text, safe_action_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title=clean_title,
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=safe_company_url,
        show_header_title=False,
    )
