from .base_template import get_base_template


def get_login_alert_email_html(
    recipient_name: str,
    actor_name: str,
    actor_email: str,
    login_time: str,
    ip_address: str = "Unknown",
    location: str = "Unknown",
    device: str = "Unknown",
    organization_name: str = "",
    is_own_login: bool = True,
    security_url: str = "https://teamzen-admin.vercel.app/settings/security",
    logo_url: str = "",
    company_name: str = "Teamzen",
) -> str:
    """Generate HTML for a login activity security alert."""

    accent = "#0F766E"  # Teal
    headline = "New sign-in to your account" if is_own_login else "Login activity alert"
    intro = (
        f"We detected a successful sign-in to your <strong style=\"color: #0F172A;\">{company_name}</strong> account."
        if is_own_login
        else f"A user signed in to <strong style=\"color: #0F172A;\">{company_name}</strong>."
    )
    org_row = ""
    if organization_name:
        org_row = f"""
                                    <tr>
                                        <td style="padding: 8px 0; font-size: 13px; color: #64748B; width: 120px;">Organization</td>
                                        <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{organization_name}</td>
                                    </tr>
        """

    body = f"""
                <tr>
                    <td class="hero-section" bgcolor="#CCFBF1" style="padding: 40px 40px 28px 40px; text-align: center; background-color: #CCFBF1;">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 12px;">🔐</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #0F172A !important; letter-spacing: -0.5px;">
                            <span style="color: #0F172A; background-color: #CCFBF1;">{headline}</span>
                        </h1>
                        <p style="margin: 0; font-size: 14px; color: #334155 !important;">
                            <span style="color: #334155; background-color: #CCFBF1;">Security notification</span>
                        </p>
                    </td>
                </tr>

                <tr>
                    <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 40px 16px 40px; background-color: #FFFFFF;">
                        <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                            Hi <strong style="color: #0F172A;">{recipient_name}</strong>,
                        </p>
                        <p style="margin: 0 0 24px 0; font-size: 15px; color: #334155; line-height: 1.7;">
                            {intro}
                        </p>
                    </td>
                </tr>

                <tr>
                    <td bgcolor="#FFFFFF" style="padding: 0 40px 28px 40px; background-color: #FFFFFF;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
                            <tr>
                                <td style="padding: 20px 24px;">
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                        <tr>
                                            <td style="padding: 8px 0; font-size: 13px; color: #64748B; width: 120px;">User</td>
                                            <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{actor_name} &lt;{actor_email}&gt;</td>
                                        </tr>
                                        {org_row}
                                        <tr>
                                            <td style="padding: 8px 0; font-size: 13px; color: #64748B;">Time</td>
                                            <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{login_time}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px 0; font-size: 13px; color: #64748B;">IP address</td>
                                            <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{ip_address or "Unknown"}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px 0; font-size: 13px; color: #64748B;">Location</td>
                                            <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{location or "Unknown"}</td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px 0; font-size: 13px; color: #64748B;">Device</td>
                                            <td style="padding: 8px 0; font-size: 13px; color: #0F172A; font-weight: 600;">{device or "Unknown"}</td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <tr>
                    <td bgcolor="#FFFFFF" style="padding: 0 40px 40px 40px; background-color: #FFFFFF; text-align: center;">
                        <a href="{security_url}" style="display: inline-block; padding: 12px 24px; background-color: {accent}; color: #FFFFFF; text-decoration: none; border-radius: 10px; font-size: 14px; font-weight: 700;">
                            Review security settings
                        </a>
                        <p style="margin: 20px 0 0 0; font-size: 13px; color: #991B1B; line-height: 1.6;">
                            If this wasn’t you (or looks suspicious), reset the password and review active sessions immediately.
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title=headline,
        body_content=body,
        accent_color=accent,
        accent_light="#CCFBF1",
        logo_url=logo_url,
        footer_text=company_name,
    )
