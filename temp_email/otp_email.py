from .base_template import (
    get_base_template,
    alert_box_html,
    hero_section_html,
)


def get_otp_email_html(
    employee_name: str = "",
    otp_code: str = "",
    expiry_minutes: int = 5,
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the OTP Login HTML email with clean executive security styling."""
    # Handle single-argument calls where code was passed first, e.g. get_otp_email_html("123456")
    if not otp_code and employee_name and (employee_name.isdigit() or len(employee_name) == 6):
        otp_code = employee_name
        employee_name = "there"

    accent = "#4F46E5"  # Indigo
    hero_bg = "#EEF2FF"

    code_display = otp_code or "------"
    salutation_name = (employee_name or "there").strip()

    body = f"""
        {hero_section_html(
            headline="One-Time Verification Code",
            subtitle=f"This code will expire in {expiry_minutes} minutes",
            badge_label="SECURITY VERIFICATION",
            badge_color="#4338CA",
            badge_bg="#E0E7FF",
            hero_bg=hero_bg,
        )}

        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 16px 36px; background-color: #FFFFFF;">
                <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Hi <strong style="color: #0F172A;">{salutation_name}</strong>,
                </p>
                <p style="margin: 0 0 20px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                    Use the following single-use verification code to complete sign-in to your <strong style="color: #0F172A;">{company_name}</strong> account.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 28px 36px; text-align: center; background-color: #FFFFFF;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border: 2px dashed #C7D2FE; border-radius: 12px; margin: 0 auto;">
                    <tr>
                        <td bgcolor="#F8FAFC" style="padding: 18px 40px; background-color: #F8FAFC; text-align: center;">
                            <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; color: {accent}; letter-spacing: 8px;">
                                {code_display}
                            </span>
                        </td>
                    </tr>
                </table>
                <p style="margin: 12px 0 0 0; font-size: 12px; color: #64748B;">
                    Single-use verification passcode &bull; Do not share this code with anyone.
                </p>
            </td>
        </tr>

        <tr>
            <td bgcolor="#FFFFFF" style="padding: 0 36px 36px 36px; background-color: #FFFFFF;">
                {alert_box_html(
                    "If you did not initiate this sign-in request, please ignore this email or notify your system administrator immediately. Your password remains safe.",
                    title="Security Notice",
                    level="info",
                )}
            </td>
        </tr>
    """

    return get_base_template(
        title="Your Verification Code",
        body_content=body,
        accent_color=accent,
        accent_light=hero_bg,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=company_url,
        show_header_title=False,
    )
