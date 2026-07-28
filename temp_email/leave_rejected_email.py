from .base_template import get_base_template, button_html, info_row_html, status_badge_html

def get_leave_rejected_email_html(
    employee_name: str,
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    rejected_by: str = "",
    reason: str = "",
    dashboard_url: str = "https://teamzen-client.vercel.app/leaves",
    logo_url: str = "https://teamzen-admin.vercel.app/logo.png",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Leave Rejected notification HTML email."""

    accent = "#DC2626"  # Red for rejected
    accent_light = "#FEF2F2"

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #FEF2F2 0%, #FECACA 50%, #FCA5A5 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 20px;">❌</div>
                        <div style="margin-bottom: 12px;">
                            {status_badge_html("REJECTED", "#991B1B", "#FECACA")}
                        </div>
                        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.02em;">Leave Request Declined</h1>
                    </td>
                </tr>

                <!-- Message Area -->
                <tr>
                    <td style="padding: 32px 40px 16px 40px;">
                        <p style="margin: 0; font-size: 16px; color: #334155;">
                            Hi <strong>{employee_name}</strong>,
                        </p>
                        <p style="margin: 12px 0 0 0; font-size: 15px; color: #475569; line-height: 1.6;">
                            Unfortunately, your leave request has been <strong style="color: {accent};">declined</strong>. Please review the details below.
                        </p>
                    </td>
                </tr>

                <!-- Leave Details Card -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background-color: {accent_light}; border: 1px solid #FECACA; border-radius: 12px; padding: 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding-bottom: 12px; border-bottom: 1px solid #FECACA;">
                                        <p style="margin: 0; font-weight: 700; color: #991B1B; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">📋 Leave Details</p>
                                    </td>
                                </tr>
                                {info_row_html("Leave Type", leave_type, "🏷️", accent)}
                                {info_row_html("Dates", f"{start_date} to {end_date}", "📅", accent)}
                                {info_row_html("Duration", f"{duration} days", "⏱️", accent)}
                                {info_row_html("Rejected By", rejected_by, "👤", accent) if rejected_by else ""}
                            </table>
                        </div>
                    </td>
                </tr>

                <!-- Rejection Reason -->
                {f'''
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background-color: #FFFBEB; border-left: 4px solid {accent}; border-radius: 4px; padding: 16px;">
                            <p style="margin: 0; font-weight: 700; color: #92400E; font-size: 13px; text-transform: uppercase; margin-bottom: 8px;">⚠️ Reason for Rejection</p>
                            <p style="margin: 0; font-style: italic; color: #475569; line-height: 1.5;">"{reason}"</p>
                        </div>
                    </td>
                </tr>
                ''' if reason else ""}

                <!-- Tip Section -->
                <tr>
                    <td style="padding: 0 40px 32px 40px;">
                        <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px; padding: 16px;">
                            <p style="margin: 0; font-size: 14px; color: #1E40AF; line-height: 1.5;">
                                💡 <strong>Tip:</strong> You can discuss alternative dates with your manager or submit a new request with different dates.
                            </p>
                        </div>
                    </td>
                </tr>

                <!-- CTA -->
                <tr>
                    <td style="padding: 0 40px 40px 40px; text-align: center;">
                        {button_html("📝 Submit New Request", dashboard_url, "#4F46E5")}
                        <p style="margin: 14px 0 0 0; font-size: 13px; color: #94A3B8;">
                            Open Teamzen to explore alternate dates, review balances, or submit a revised leave request.
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title="Leave Request Declined",
        body_content=body,
        accent_color=accent,
        accent_light=accent_light,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=company_url
    )
