from .base_template import (
    get_base_template,
    button_html,
    card_table_html,
    alert_box_html,
    hero_section_html,
    sanitize_portal_url,
)


def get_welcome_email_html(
    employee_name: str,
    employee_email: str = "",
    designation: str = "",
    department: str = "",
    joining_date: str = "",
    login_url: str = "",
    temp_password: str = "",
    manager_name: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "",
) -> str:
    """Generate the Welcome/Onboarding HTML email."""
    accent = "#4F46E5"  # Indigo
    hero_bg = "#EEF2FF"
    safe_login_url = sanitize_portal_url(login_url, "login")
    safe_company_url = sanitize_portal_url(company_url)

    rows = []
    if employee_email:
        rows.append(("Work Email", employee_email))
    if designation:
        rows.append(("Designation", designation))
    if department:
        rows.append(("Department", department))
    if joining_date:
        rows.append(("Joining Date", joining_date))
    if manager_name:
        rows.append(("Reporting To", manager_name))

    temp_password_markup = ""
    if temp_password:
        temp_password_markup = f"""
        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
                    <tr>
                        <td style="padding: 20px 24px;">
                            <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.08em;">
                                Temporary Access Password
                            </p>
                            <div style="background-color: #FFFFFF; border: 1px dashed #CBD5E1; border-radius: 8px; padding: 12px 18px; margin: 8px 0;">
                                <span style="font-family: 'Courier New', Courier, monospace; font-size: 20px; font-weight: 700; color: #0F172A; letter-spacing: 2px;">
                                    {temp_password}
                                </span>
                            </div>
                            <p style="margin: 8px 0 0 0; font-size: 12px; color: #64748B; line-height: 1.5;">
                                For your security, you will be prompted to set a permanent password upon first login.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        """

    body = f"""
        {hero_section_html(
            headline=f"Welcome to {company_name}",
            subtitle="Your employee account has been created successfully",
            badge_label="ACCOUNT ACTIVATED",
            badge_color="#4338CA",
            badge_bg="#E0E7FF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{employee_name}</strong>,
                </p>
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    We are thrilled to welcome you to the team. Your account on the <strong>{company_name} HRMS Portal</strong> is ready. You can now sign in to view your profile, manage attendance, submit documents, and review team schedules.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 24px 36px; background-color: #FFFFFF;">
                {card_table_html(rows, card_title="Your Profile Details")}
            </td>
        </tr>

        {temp_password_markup}

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "Please complete your profile details and verify your contact information to activate all workplace services.",
                    title="Next Steps",
                    level="info",
                )}
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 4px 36px 36px 36px; background-color: #FFFFFF; text-align: center;">
                {button_html("Sign In to Workspace", safe_login_url, accent)}
            </td>
        </tr>
    """

    return get_base_template(
        title=f"Welcome to {company_name}",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=safe_company_url,
        show_header_title=False,
    )
