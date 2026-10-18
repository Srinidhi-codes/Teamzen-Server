from .base_template import (
    get_base_template,
    button_html,
    status_badge_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_document_notification_email_html(
    recipient_name: str,
    title: str = "Document Notification",
    message: str = "",
    document_name: str = "",
    document_category: str = "",
    status: str = "Action Required",
    action_url: str = "",
    action_text: str = "View Document",
    company_name: str = "Teamzen",
    company_url: str = "",
    logo_url: str = "",
) -> str:
    """Generate professional document activity notification email."""
    safe_action_url = sanitize_portal_url(action_url, "documents")
    safe_company_url = sanitize_portal_url(company_url)
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint

    rows = []
    if document_name:
        rows.append(("Document", document_name))
    if document_category:
        rows.append(("Category", document_category.replace("_", " ").title()))
    if status:
        rows.append(("Current Status", status))

    clean_title = title.strip()
    if clean_title.lower().startswith("notification:"):
        clean_title = clean_title[13:].strip()

    body = f"""
        {hero_section_html(
            headline=clean_title,
            badge_label="DOCUMENT SERVICE",
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
                    {message or 'There is a new update regarding your company documents.'}
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Document Details")}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Uploaded files are encrypted and stored according to internal organizational data governance policies.",
                    title="Document Security",
                    level="info",
                )}
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
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )
