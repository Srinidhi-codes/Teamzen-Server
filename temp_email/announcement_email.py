from .base_template import get_base_template, button_html, info_row_html, status_badge_html

def get_announcement_email_html(
    employee_name: str = "",
    announcement_title: str = "",
    announcement_body: str = "",
    category: str = "General",
    posted_by: str = "",
    posted_date: str = "",
    action_url: str = "https://teamzen-client.vercel.app/notifications",
    action_text: str = "View Details",
    priority: str = "normal",  # normal, high, urgent
    logo_url: str = "",
    company_name: str = "Teamzen",
    company_url: str = "#",
) -> str:
    """Generate the Company Announcement HTML email."""

    # Color based on priority
    priority_config = {
        "normal": {"accent": "#4F46E5", "bg": "#EEF2FF", "icon": "📢", "label": "Announcement"},
        "high": {"accent": "#EA580C", "bg": "#FFF7ED", "icon": "⚡", "label": "Important"},
        "urgent": {"accent": "#DC2626", "bg": "#FEF2F2", "icon": "🚨", "label": "Urgent Action Required"},
    }
    
    config = priority_config.get(priority.lower(), priority_config["normal"])
    accent = config["accent"]
    accent_light = config["bg"]

    body = f"""
                <!-- Hero Section -->
                <tr>
                    <td class="hero-section" style="padding: 40px 40px 28px 40px; text-align: center; background: linear-gradient(135deg, {accent_light} 0%, #ffffff 100%);">
                        <div style="font-size: 48px; line-height: 1; margin-bottom: 20px;">{config["icon"]}</div>
                        <div style="margin-bottom: 12px;">
                            {status_badge_html(config["label"], accent, accent_light)}
                        </div>
                        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #1E293B; letter-spacing: -0.02em;">{announcement_title or "Company Announcement"}</h1>
                    </td>
                </tr>

                <!-- Message Area -->
                <tr>
                    <td style="padding: 32px 40px 24px 40px;">
                        <p style="margin: 0; font-size: 16px; color: #334155;">
                            Hi <strong>{employee_name}</strong>,
                        </p>
                        <div style="margin: 16px 0; font-size: 15px; color: #475569; line-height: 1.7; white-space: pre-wrap;">
                            {announcement_body}
                        </div>
                    </td>
                </tr>

                <!-- Announcement Focus -->
                <tr>
                    <td style="padding: 0 40px 24px 40px;">
                        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 18px 20px;">
                            <p style="margin: 0 0 8px 0; font-size: 12px; font-weight: 800; color: {accent}; text-transform: uppercase; letter-spacing: 0.08em;">
                                Action summary
                            </p>
                            <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.7;">
                                Category: <strong style="color: #0F172A;">{category}</strong>
                                {f' · Posted by <strong style="color: #0F172A;">{posted_by}</strong>' if posted_by else ""}
                                {f' · {posted_date}' if posted_date else ""}
                            </p>
                        </div>
                    </td>
                </tr>

                <!-- Meta Details -->
                <tr>
                    <td style="padding: 0 40px 32px 40px;">
                        <div style="border-top: 1px solid #E2E8F0; padding-top: 16px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td>
                                        <p style="margin: 0; font-size: 13px; color: #64748B;">
                                            <strong>Posted By:</strong> {posted_by}
                                        </p>
                                    </td>
                                    <td style="text-align: right;">
                                        <p style="margin: 0; font-size: 13px; color: #64748B;">
                                            {posted_date}
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </div>
                    </td>
                </tr>

                <!-- CTA -->
                <tr>
                    <td style="padding: 0 40px 40px 40px; text-align: center;">
                        {button_html(action_text, action_url, accent)}
                        <p style="margin: 14px 0 0 0; font-size: 13px; color: #94A3B8;">
                            Open Teamzen to read the full update and respond if action is required.
                        </p>
                    </td>
                </tr>
    """

    return get_base_template(
        title=announcement_title or "Announcement",
        body_content=body,
        accent_color=accent,
        accent_light=accent_light,
        logo_url=logo_url,
        footer_text=f"{company_name} HRMS",
        company_url=company_url
    )
