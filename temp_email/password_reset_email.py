from .base_template import get_base_template, button_html

def get_password_reset_email_html(
    employee_name: str,
    reset_url: str = "#",
    expiry_minutes: int = 30,
    ip_address: str = "",
    browser_info: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Password Reset HTML email."""

    accent = "#4F46E5"  # Indigo

    request_info = ""
    if ip_address or browser_info:
        rows = ""
        if ip_address:
            rows += f'<p style="margin: 0 0 4px 0; font-size: 12px; color: #64748B;">IP Address: <strong>{ip_address}</strong></p>'
        if browser_info:
            rows += f'<p style="margin: 0; font-size: 12px; color: #64748B;">Browser: <strong>{browser_info}</strong></p>'
        request_info = f"""
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
                            <tr>
                                <td style="padding: 16px 20px;">
                                    <p style="margin: 0 0 8px 0; font-size: 12px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px;">🖥️ Request Details</p>
                                    {rows}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
        """

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 50%, #C7D2FE 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 12px;">🔐</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.5px;">
                            Password Reset Request
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
                        <p style="margin: 0 0 16px 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            We received a request to reset your password for your <strong>{company_name}</strong> account. Click the button below to set a new password.
                        </p>
                    </td>
                </tr>

                <!-- CTA -->
                <tr>
                    <td style="padding: 8px 40px 24px 40px; text-align: center;">
                        {button_html("🔑 Reset My Password", reset_url, accent)}
                        <p style="margin: 16px 0 0 0; font-size: 13px; color: #94A3B8;">
                            Or copy this link:<br>
                            <a href="{reset_url}" style="color: {accent}; word-break: break-all; font-size: 12px;">{reset_url}</a>
                        </p>
                    </td>
                </tr>

                {request_info}

                <!-- Security Warning -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #FEF2F2; border-radius: 12px; border: 1px solid #FECACA;">
                            <tr>
                                <td style="padding: 16px 20px;">
                                    <p style="margin: 0; font-size: 13px; color: #991B1B; line-height: 1.6;">
                                        🛡️ <strong>Didn't request this?</strong> If you didn't request a password reset, please ignore this email or contact your administrator immediately. Your password will remain unchanged.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Expiry Notice -->
                <tr>
                    <td style="padding: 0 40px 40px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #FFFBEB; border-radius: 12px; border: 1px solid #FDE68A;">
                            <tr>
                                <td style="padding: 16px 20px;">
                                    <p style="margin: 0; font-size: 13px; color: #92400E; line-height: 1.6;">
                                        ⏳ This link will expire in <strong>{expiry_minutes} minutes</strong>. After that, you'll need to request a new password reset.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
    """

    return get_base_template(
        title="Reset Your Password 🔐",
        body_content=body,
        accent_color=accent,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=company_url,
    )
