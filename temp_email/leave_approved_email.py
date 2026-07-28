from .base_template import get_base_template, button_html, info_row_html, status_badge_html

def get_leave_approved_email_html(
    employee_name: str,
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    approved_by: str = "",
    remarks: str = "",
    dashboard_url: str = "https://teamzen-client.vercel.app/leaves",
    logo_url: str = "https://teamzen-admin.vercel.app/logo.png",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Leave Approved notification HTML email."""

    accent = "#059669"  # Green for approved
    accent_light = "#ECFDF5"

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 50%, #A7F3D0 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 20px;">✅</div>
                        <div style="margin-bottom: 12px;">
                            {status_badge_html("APPROVED", "#065F46", "#D1FAE5")}
                        </div>
                        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.02em;">Leave Request Approved</h1>
                    </td>
                </tr>

                <!-- Message Area -->
                <tr>
                    <td style="padding: 32px 40px 16px 40px;">
                        <p style="margin: 0; font-size: 16px; color: #334155;">
                            Hi <strong>{employee_name}</strong>,
                        </p>
                        <p style="margin: 12px 0 0 0; font-size: 15px; color: #475569; line-height: 1.6;">
                            Great news! Your leave request has been <strong style="color: {accent};">approved</strong>. Enjoy your time off!
                        </p>
                    </td>
                </tr>

                <!-- Leave Details Card -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background-color: {accent_light}; border: 1px solid #D1FAE5; border-radius: 12px; padding: 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding-bottom: 12px; border-bottom: 1px solid #D1FAE5;">
                                        <p style="margin: 0; font-weight: 700; color: #065F46; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">📋 Leave Details</p>
                                    </td>
                                </tr>
                                {info_row_html("Leave Type", leave_type, "🏷️", accent)}
                                {info_row_html("Dates", f"{start_date} to {end_date}", "📅", accent)}
                                {info_row_html("Duration", f"{duration} days", "⏱️", accent)}
                                {info_row_html("Approved By", approved_by, "👤", accent) if approved_by else ""}
                            </table>
                        </div>
                    </td>
                </tr>

                <!-- Plan Ahead -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background: #FFFFFF; border: 1px solid #BBF7D0; border-radius: 14px; padding: 16px 18px;">
                            <p style="margin: 0 0 8px 0; font-size: 12px; font-weight: 800; color: #059669; text-transform: uppercase; letter-spacing: 0.08em;">Next steps</p>
                            <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.7;">
                                Your schedule has been updated. Use Teamzen to review your leave timeline, balances, and any related attendance updates.
                            </p>
                        </div>
                    </td>
                </tr>

                <!-- Remarks -->
                {f'''
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background-color: #F0FDF4; border-left: 4px solid {accent}; border-radius: 4px; padding: 16px;">
                            <p style="margin: 0; font-weight: 700; color: #166534; font-size: 13px; text-transform: uppercase; margin-bottom: 8px;">💬 Approval Remarks</p>
                            <p style="margin: 0; font-style: italic; color: #475569; line-height: 1.5;">"{remarks}"</p>
                        </div>
                    </td>
                </tr>
                ''' if remarks else ""}

                <!-- CTA -->
                <tr>
                    <td style="padding: 0 40px 40px 40px; text-align: center;">
                        {button_html("🏠 View My Leaves", dashboard_url, "#4F46E5")}
                        <p style="margin: 14px 0 0 0; font-size: 13px; color: #94A3B8;">
                            You can revisit the approval details and leave balance anytime from your employee dashboard.
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title="Leave Request Approved",
        body_content=body,
        accent_color=accent,
        accent_light=accent_light,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=company_url
    )
