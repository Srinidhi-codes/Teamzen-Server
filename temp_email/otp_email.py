from .base_template import get_base_template

def get_otp_email_html(
    employee_name: str,
    otp_code: str,
    expiry_minutes: int = 5,
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the OTP Login HTML email."""

    accent = "#4F46E5"  # Indigo

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 50%, #C7D2FE 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 12px;">🔑</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.5px;">
                            Your One-Time Password
                        </h1>
                        <p style="margin: 0; font-size: 14px; color: #64748B;">
                            Expires in {expiry_minutes} minutes
                        </p>
                    </td>
                </tr>

                <!-- Message -->
                <tr>
                    <td class="content-block" style="padding: 28px 40px 16px 40px;">
                        <p style="margin: 0 0 16px 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            Hi <strong>{employee_name}</strong>,
                        </p>
                        <p style="margin: 0 0 24px 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            Use the following one-time passcode to sign in to your <strong>{company_name}</strong> account.
                        </p>
                    </td>
                </tr>

                <!-- OTP Code Display -->
                <tr>
                    <td style="padding: 8px 40px 32px 40px; text-align: center;">
                        <div style="display: inline-block; background-color: #F8FAFC; border: 2px dashed #C7D2FE; border-radius: 12px; padding: 16px 36px;">
                            <span style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 800; color: {accent}; letter-spacing: 6px;">
                                {otp_code}
                            </span>
                        </div>
                        <p style="margin: 16px 0 0 0; font-size: 13px; color: #94A3B8;">
                            This code is valid for single use only.
                        </p>
                    </td>
                </tr>

                <!-- Security Warning -->
                <tr>
                    <td style="padding: 0 40px 40px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #FEF2F2; border-radius: 12px; border: 1px solid #FECACA;">
                            <tr>
                                <td style="padding: 16px 20px;">
                                    <p style="margin: 0; font-size: 13px; color: #991B1B; line-height: 1.6;">
                                        🛡️ <strong>Security Reminder:</strong> If you did not request this code, someone might have entered your email address by mistake. You can safely ignore this email; your account remains secure.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
    """

    return get_base_template(
        title="Your Single Sign-On OTP 🔑",
        body_content=body,
        accent_color=accent,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=company_url,
    )
