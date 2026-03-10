from .base_template import get_base_template, button_html, info_row_html, status_badge_html

def get_leave_cancelled_email_html(
    employee_name: str,
    manager_name: str = "Manager",
    leave_type: str = "Casual Leave",
    start_date: str = "",
    end_date: str = "",
    duration: str = "1 day",
    cancelled_by: str = "",
    dashboard_url: str = "https://teamzen-admin.vercel.app/leaves",
    logo_url: str = "https://teamzen-admin.vercel.app/logo.png",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Leave Request Cancelled notification HTML email (sent to manager)."""

    accent = "#EA580C"  # Orange for cancelled requests
    accent_light = "#FFF7ED"

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, #FFF7ED 0%, #FFEDD5 50%, #FED7AA 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 20px;">📅</div>
                        <div style="margin-bottom: 12px;">
                            {status_badge_html("CANCELLED", "#9A3412", "#FFEDD5")}
                        </div>
                        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #000000; letter-spacing: -0.02em;">Leave Request Cancelled</h1>
                    </td>
                </tr>

                <!-- Message Area -->
                <tr>
                    <td style="padding: 32px 40px 16px 40px;">
                        <p style="margin: 0; font-size: 16px; color: #334155;">
                            Hi <strong>{manager_name}</strong>,
                        </p>
                        <p style="margin: 12px 0 0 0; font-size: 15px; color: #475569; line-height: 1.6;">
                            <strong>{employee_name}</strong> has cancelled a leave request. 
                        </p>
                    </td>
                </tr>

                <!-- Leave Details Card -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background-color: {accent_light}; border: 1px solid #FFEDD5; border-radius: 12px; padding: 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding-bottom: 12px; border-bottom: 1px solid #FFEDD5;">
                                        <p style="margin: 0; font-weight: 700; color: #9A3412; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">📋 Leave Details</p>
                                    </td>
                                </tr>
                                {info_row_html("Employee", employee_name, "👤", accent)}
                                {info_row_html("Leave Type", leave_type, "🏷️", accent)}
                                {info_row_html("Dates", f"{start_date} to {end_date}", "📅", accent)}
                                {info_row_html("Duration", f"{duration} days", "⏱️", accent)}
                                {info_row_html("Cancelled By", cancelled_by if cancelled_by else employee_name, "🚫", accent)}
                            </table>
                        </div>
                    </td>
                </tr>

                <!-- CTA -->
                <tr>
                    <td style="padding: 0 40px 40px 40px; text-align: center;">
                        {button_html("View Details", dashboard_url, accent)}
                    </td>
                </tr>
    """

    return get_base_template(
        title="Leave Request Cancelled",
        body_content=body,
        accent_color=accent,
        accent_light=accent_light,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=company_url
    )
