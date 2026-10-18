from .base_template import (
    get_base_template,
    button_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_password_reset_email_html(
    employee_name: str,
    reset_url: str = "",
    expiry_minutes: int = 30,
    ip_address: str = "",
    browser_info: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Password Reset HTML email with clean security design and zero emojis."""
    accent = "#0F766E"  # Teamzen Teal
    hero_bg = "#CCFBF1"  # Soft mint
    safe_url = sanitize_portal_url(reset_url, "reset-password")
    safe_company_url = sanitize_portal_url(company_url)

    rows = []
    if ip_address:
        rows.append(("Origin IP", ip_address))
    if browser_info:
        rows.append(("Client / Browser", browser_info))
    rows.append(("Valid For", f"{expiry_minutes} minutes"))

    details_markup = ""
    if rows:
        details_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Request Metadata")}
            </td>
        </tr>
        """

    link_fallback = f"""
    <p style="margin: 16px 0 0 0; font-size: 12px; color: #64748B; line-height: 1.5; word-break: break-all;">
        Or copy and paste this link in your browser:<br/>
        <a href="{safe_url}" style="color: {accent}; font-weight: 600;">{safe_url}</a>
    </p>
    """

    body = f"""
        {hero_section_html(
            headline="Password Reset Request",
            subtitle=f"This link is valid for {expiry_minutes} minutes",
            badge_label="ACCOUNT SECURITY",
            badge_color="#0F766E",
            badge_bg="#FFFFFF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name or 'there'}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    We received a request to reset the password associated with your <strong>{company_name}</strong> account. Click the button below to choose a new password.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 28px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("Reset Password", safe_url, accent)}
                {link_fallback}
            </td>
        </tr>

        {details_markup}

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 36px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "If you did not submit this request, no action is needed and your existing password remains secure. If you suspect unauthorized activity, contact your system administrator immediately.",
                    title="Security Note",
                    level="info",
                )}
            </td>
        </tr>
    """

    return get_base_template(
        title="Reset Your Password",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=safe_company_url,
        show_header_title=False,
    )
