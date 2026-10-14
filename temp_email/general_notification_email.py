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


def get_general_notification_email_html(
    recipient_name: str,
    title: str,
    message: str,
    category: str = "System Notification",
    badge_label: str = "",
    details: list = None,
    action_url: str = "",
    action_text: str = "Open Workspace",
    priority: str = "normal",  # normal, info, warning, urgent, success
    alert_note: str = "",
    alert_level: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
    logo_url: str = "",
) -> str:
    """
    Universal, production-ready email template for all notifications.
    Ensures every email in the HRMS is delivered with executive styling,
    structured typography, and zero unstyled fallback text.
    """
    safe_company_url = sanitize_portal_url(company_url)
    safe_action_url = sanitize_portal_url(action_url) if action_url else safe_company_url

    priority_configs = {
        "normal": {"accent": "#0F766E", "hero_bg": "#CCFBF1", "badge_color": "#0F766E", "badge_bg": "#E6FFFA", "label": "NOTIFICATION"},
        "info": {"accent": "#0284C7", "hero_bg": "#E0F2FE", "badge_color": "#0369A1", "badge_bg": "#BAE6FD", "label": "INFORMATION"},
        "success": {"accent": "#059669", "hero_bg": "#ECFDF5", "badge_color": "#047857", "badge_bg": "#D1FAE5", "label": "COMPLETED"},
        "warning": {"accent": "#D97706", "hero_bg": "#FEF3C7", "badge_color": "#B45309", "badge_bg": "#FDE68A", "label": "ATTENTION REQUIRED"},
        "urgent": {"accent": "#DC2626", "hero_bg": "#FEE2E2", "badge_color": "#B91C1C", "badge_bg": "#FECACA", "label": "URGENT ACTION"},
    }

    cfg = priority_configs.get(priority.lower(), priority_configs["normal"])
    accent = cfg["accent"]
    hero_bg = cfg["hero_bg"]
    badge_text = badge_label or category.upper() or cfg["label"]

    clean_title = (title or "Notification").strip()
    if clean_title.lower().startswith("notification:"):
        clean_title = clean_title[13:].strip()

    # Format message paragraphs
    paragraphs = [p.strip() for p in (message or "").split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = ["You have a new update in your HRMS account."]

    message_html = "".join(
        f'<p style="margin: 0 0 14px 0; font-size: 15px; color: #334155; line-height: 1.7;">{p}</p>'
        for p in paragraphs
    )

    # Details card table
    details_card_markup = ""
    if details:
        # Support dict or list of (key, value)
        rows = details.items() if isinstance(details, dict) else details
        details_card_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(list(rows), card_title="Activity Details")}
            </td>
        </tr>
        """

    # Alert box
    alert_markup = ""
    if alert_note:
        level = alert_level or ("warning" if priority in ["warning", "urgent"] else "info")
        alert_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {alert_box_html(alert_note, level=level)}
            </td>
        </tr>
        """

    # CTA Button
    cta_markup = ""
    if safe_action_url and safe_action_url != "#":
        btn_label = action_text or "Open Workspace"
        cta_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 8px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html(btn_label, safe_action_url, accent)}
            </td>
        </tr>
        """

    body = f"""
        {hero_section_html(
            headline=clean_title,
            badge_label=badge_text,
            badge_color=cfg["badge_color"],
            badge_bg=cfg["badge_bg"],
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{recipient_name or 'there'}</strong>,
                </p>
                {message_html}
            </td>
        </tr>

        {details_card_markup}
        {alert_markup}
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
