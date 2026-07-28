def logo_badge_html(accent_color: str) -> str:
    """Email-safe fallback mark when no hosted logo URL is available."""
    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display: inline-block;">
        <tr>
            <td align="center" valign="middle" style="width: 56px; height: 56px; border-radius: 16px; background: linear-gradient(135deg, {accent_color}, #0EA5E9); color: #FFFFFF; font-size: 28px; font-weight: 800; line-height: 56px; text-align: center; box-shadow: 0 8px 18px rgba(37, 99, 235, 0.18);">
                T
            </td>
        </tr>
    </table>
    """


def resolve_email_logo_url(logo_url: str = "") -> str:
    """Prefer an explicit logo URL, then the Cloudinary-hosted Teamzen mark."""
    if logo_url:
        return logo_url
    try:
        from django.conf import settings
        return getattr(settings, "EMAIL_LOGO_URL", "") or ""
    except Exception:
        return ""


def get_base_template(
    title: str,
    body_content: str,
    accent_color: str = "#4F46E5",
    accent_light: str = "#EEF2FF",
    logo_url: str = "",
    footer_text: str = "Teamzen HRMS",
    company_url: str = "#",
) -> str:
    """Generate the base responsive HTML email template."""
    resolved_logo = resolve_email_logo_url(logo_url)
    logo_html = (
        f'<img src="{resolved_logo}" alt="{footer_text}" width="120" height="56" '
        f'style="display: block; width: 120px; height: 56px; object-fit: contain; '
        f'background: #FFFFFF; border-radius: 12px;" />'
        if resolved_logo
        else logo_badge_html(accent_color)
    )

    return f"""<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{ background: #F4F7FB; font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px 10px; color: #334155; }}
            .shell {{ max-width: 640px; margin: 0 auto; }}
            .brandbar {{ text-align: center; margin: 0 0 14px 0; }}
            .brandchip {{ display: inline-block; padding: 7px 14px; border-radius: 999px; background: #FFFFFF; border: 1px solid #E2E8F0; color: #0F172A; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }}
            .container {{ background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 24px; overflow: hidden; box-shadow: 0 20px 45px rgba(15, 23, 42, 0.08); }}
            .topline {{ height: 4px; background: linear-gradient(90deg, {accent_color}, #0EA5E9); }}
            .header {{ padding: 26px 32px 18px 32px; background: linear-gradient(180deg, {accent_light}, #FFFFFF 70%); border-bottom: 1px solid #EEF2F7; }}
            .content {{ padding: 0; }}
            .footer {{ padding: 24px 32px 32px 32px; background: #FAFBFD; border-top: 1px solid #E2E8F0; }}
            .eyebrow {{ margin: 0 0 8px 0; color: {accent_color}; font-size: 12px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; }}
            .title {{ margin: 0; color: #0F172A; font-size: 28px; font-weight: 800; letter-spacing: -0.03em; }}
            p {{ font-size: 15px; color: #475569; line-height: 1.7; margin: 0 0 16px 0; }}
            .footer-note {{ color: #64748B; font-size: 12px; margin: 0; }}
            .footer-links a {{ color: {accent_color}; text-decoration: none; margin: 0 8px; font-size: 12px; font-weight: 600; }}
            @media only screen and (max-width: 640px) {{
                body {{ padding: 12px 0; }}
                .header {{ padding: 22px 22px 14px 22px; }}
                .footer {{ padding: 20px 22px 24px 22px; }}
                .title {{ font-size: 24px; }}
            }}
        </style>
    </head>
    <body>
        <div class="shell">
            <div class="brandbar">
                <span class="brandchip">Teamzen Product Update</span>
            </div>
            <div class="container">
                <div class="topline"></div>
                <div class="header">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                        <tr>
                            <td style="vertical-align: middle;">
                                <p class="eyebrow">Teamzen HRMS</p>
                                <h1 class="title">{title}</h1>
                            </td>
                            <td style="width: 132px; text-align: right; vertical-align: middle;">
                                {logo_html}
                            </td>
                        </tr>
                    </table>
                </div>
                <div class="content">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                    {body_content}
                    </table>
                </div>
                <div class="footer">
                    <p class="footer-note">This notification was generated by {footer_text}. If you did not expect this message, please contact your HR or platform administrator.</p>
                    <p class="footer-links" style="margin: 12px 0 0 0;">
                        <a href="{company_url}">Open workspace</a>
                        <a href="{company_url}">Visit company portal</a>
                    </p>
                </div>
            </div>
        </div>
    </body>
</html>
"""

def button_html(text: str, url: str, bg_color: str = "#4F46E5", text_color: str = "#ffffff") -> str:
    return f'<a href="{url}" style="background: linear-gradient(135deg, {bg_color}, #0EA5E9); color: {text_color}; text-decoration: none; padding: 13px 24px; border-radius: 12px; font-weight: 700; display: inline-block; text-align: center; box-shadow: 0 10px 24px rgba(37, 99, 235, 0.18);">{text}</a>'

def info_row_html(label: str, value: str, icon: str = "", accent_color: str = "#4F46E5") -> str:
    icon_str = f"{icon} " if icon else ""
    return f"""
    <tr>
        <td style="padding: 8px 0;">
            <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.6;">
                <strong style="display: inline-block; min-width: 118px; color: {accent_color};">{icon_str}{label}</strong>
                <span style="color: #0F172A; font-weight: 600;">{value}</span>
            </p>
        </td>
    </tr>
    """

def status_badge_html(text: str, text_color: str, bg_color: str) -> str:
    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 5px 12px; border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase;">{text}</span>'
