from .base_template import get_base_template, button_html, info_row_html

def get_welcome_email_html(
    employee_name: str,
    employee_email: str,
    designation: str = "",
    department: str = "",
    joining_date: str = "",
    login_url: str = "#",
    temp_password: str = "",
    manager_name: str = "",
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Welcome/Onboarding HTML email."""
    details_rows = ""
    if designation:
        details_rows += info_row_html("Designation", designation, "💼")
    if department:
        details_rows += info_row_html("Department", department, "🏢")
    if joining_date:
        details_rows += info_row_html("Joining Date", joining_date, "📅")
    if manager_name:
        details_rows += info_row_html("Reporting To", manager_name, "👤")
    if employee_email:
        details_rows += info_row_html("Email", employee_email, "✉️")

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 48px 40px 32px 40px; text-align: center; background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 50%, #C7D2FE 100%);">
                        <div style="font-size: 56px; line-height: 1; margin-bottom: 16px;">🎉</div>
                        <h1 style="margin: 0 0 8px 0; font-size: 26px; font-weight: 800; color: #1E293B; letter-spacing: -0.5px;">
                            Welcome to {company_name}!
                        </h1>
                        <p style="margin: 0; font-size: 15px; color: #64748B; line-height: 1.6;">
                            We're thrilled to have you on board, <strong style="color: #4F46E5;">{employee_name}</strong>
                        </p>
                    </td>
                </tr>

                <!-- Message -->
                <tr>
                    <td class="content-block" style="padding: 32px 40px 16px 40px;">
                        <p style="margin: 0 0 16px 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            Hello <strong>{employee_name}</strong>,
                        </p>
                        <p style="margin: 0 0 16px 0; font-size: 15px; color: #475569; line-height: 1.7;">
                            Your account on the <strong>{company_name} HRMS Portal</strong> has been created successfully. 
                            You can now access your dashboard to manage your profile, attendance, leaves, and more.
                        </p>
                    </td>
                </tr>

                <!-- Product Highlights -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                                <td style="padding-right: 8px; vertical-align: top;">
                                    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 14px; padding: 16px;">
                                        <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 800; color: #4F46E5; text-transform: uppercase; letter-spacing: 0.08em;">Profile</p>
                                        <p style="margin: 0; font-size: 13px; color: #475569; line-height: 1.6;">Complete your profile, personal details, and work setup in one place.</p>
                                    </div>
                                </td>
                                <td style="padding-left: 8px; vertical-align: top;">
                                    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 14px; padding: 16px;">
                                        <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 800; color: #4F46E5; text-transform: uppercase; letter-spacing: 0.08em;">Workday</p>
                                        <p style="margin: 0; font-size: 13px; color: #475569; line-height: 1.6;">Track attendance, request leave, and stay aligned with your team.</p>
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Account Details Card -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
                            <tr>
                                <td style="padding: 20px 24px 8px 24px;">
                                    <p style="margin: 0 0 12px 0; font-size: 13px; font-weight: 700; color: #4F46E5; text-transform: uppercase; letter-spacing: 1px;">
                                        📋 Your Details
                                    </p>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                        {details_rows}
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                {"" if not temp_password else f'''
                <!-- Temporary Password -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #FFFBEB; border-radius: 12px; border: 1px solid #FDE68A;">
                            <tr>
                                <td style="padding: 16px 24px;">
                                    <p style="margin: 0 0 4px 0; font-size: 13px; font-weight: 600; color: #92400E;">
                                        🔐 Your Temporary Password
                                    </p>
                                    <p style="margin: 0; font-size: 20px; font-weight: 700; color: #1E293B; font-family: monospace; letter-spacing: 2px; background-color: #FFFFFF; padding: 10px 16px; border-radius: 8px; border: 1px dashed #FDE68A; display: inline-block;">
                                        {temp_password}
                                    </p>
                                    <p style="margin: 8px 0 0 0; font-size: 12px; color: #B45309;">
                                        ⚠️ Please change this password after your first login.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                '''}

                <!-- CTA Button -->
                <tr>
                    <td style="padding: 8px 40px 40px 40px; text-align: center;">
                        {button_html("🚀 Access Your Dashboard", login_url)}
                        <p style="margin: 16px 0 0 0; font-size: 13px; color: #94A3B8;">
                            or copy this link: <a href="{login_url}" style="color: #4F46E5; word-break: break-all;">{login_url}</a>
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title=f"Welcome to {company_name}!",
        body_content=body,
        logo_url=logo_url,
        footer_text=company_name,
        company_url=company_url,
    )
