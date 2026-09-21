def logo_badge_html(accent_color: str) -> str:
    """Email-safe fallback mark when no hosted logo URL is available."""
    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display: inline-block;">
        <tr>
            <td align="center" valign="middle" style="width: 48px; height: 48px; border-radius: 8px; background-color: {accent_color}; color: #FFFFFF; font-size: 24px; font-weight: 800; line-height: 48px; text-align: center;">
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

    # Force light rendering: iOS Mail dark mode often inverts text to white while
    # leaving light backgrounds, which makes headings like "Your One-Time Password" unreadable.
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light only">
        <meta name="supported-color-schemes" content="light only">
        <title>{title}</title>
        <style>
            :root {{ color-scheme: light only; supported-color-schemes: light only; }}
            body {{ background-color: #F9FAFB !important; background: #F9FAFB; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 40px 20px; color: #111827 !important; }}
            .shell {{ max-width: 600px; margin: 0 auto; }}
            .brandbar {{ text-align: center; margin: 0 0 24px 0; }}
            .container {{ background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden; }}
            .topline {{ height: 4px; background-color: {accent_color}; }}
            .header {{ padding: 32px 40px 24px 40px; background-color: #FFFFFF !important; border-bottom: 1px solid #F3F4F6; }}
            .content {{ padding: 0; background-color: #FFFFFF !important; }}
            .footer {{ padding: 32px 40px; background-color: #F9FAFB !important; border-top: 1px solid #E5E7EB; text-align: center; }}
            .eyebrow {{ margin: 0 0 8px 0; color: #6B7280 !important; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
            .title {{ margin: 0; color: #111827 !important; font-size: 24px; font-weight: 700; letter-spacing: -0.01em; }}
            p {{ font-size: 15px; color: #374151 !important; line-height: 1.6; margin: 0 0 16px 0; }}
            .footer-note {{ color: #6B7280 !important; font-size: 13px; margin: 0 0 16px 0; line-height: 1.5; }}
            .footer-links a {{ color: {accent_color} !important; text-decoration: none; margin: 0 12px; font-size: 13px; font-weight: 500; }}
            
            /* Keep light palette */
            @media (prefers-color-scheme: dark) {{
                body {{ background-color: #F9FAFB !important; color: #111827 !important; }}
                .container, .content, .header, .brandchip {{ background-color: #FFFFFF !important; }}
                .footer {{ background-color: #F9FAFB !important; }}
                .title, h1, p {{ color: #111827 !important; }}
                .eyebrow, .footer-note {{ color: #6B7280 !important; }}
            }}
            @media only screen and (max-width: 600px) {{
                body {{ padding: 20px 10px; }}
                .header, .footer {{ padding: 24px 20px; }}
                .title {{ font-size: 20px; }}
            }}
        </style>
    </head>
    <body style="background-color: #F9FAFB; margin: 0; padding: 40px 20px; color: #111827;">
        <div class="shell">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" class="container" bgcolor="#FFFFFF" style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden;">
                <tr>
                    <td class="topline" bgcolor="{accent_color}" style="height: 4px; background-color: {accent_color}; font-size: 0; line-height: 0;">&nbsp;</td>
                </tr>
                <tr>
                    <td class="header" bgcolor="#FFFFFF" style="padding: 32px 40px 24px 40px; background-color: #FFFFFF; border-bottom: 1px solid #F3F4F6;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                                <td style="vertical-align: middle;">
                                    <p class="eyebrow" style="margin: 0 0 8px 0; color: #6B7280; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">{footer_text}</p>
                                    <h1 class="title" style="margin: 0; color: #111827; font-size: 24px; font-weight: 700; letter-spacing: -0.01em;">{title}</h1>
                                </td>
                                <td style="width: 132px; text-align: right; vertical-align: middle;">
                                    {logo_html}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td class="content" bgcolor="#FFFFFF" style="padding: 0; background-color: #FFFFFF;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#FFFFFF" style="background-color: #FFFFFF;">
                        {body_content}
                        </table>
                    </td>
                </tr>
                <tr>
                    <td class="footer" bgcolor="#F9FAFB" style="padding: 32px 40px; background-color: #F9FAFB; border-top: 1px solid #E5E7EB; text-align: center;">
                        <p class="footer-note" style="margin: 0 0 16px 0; color: #6B7280; font-size: 13px; line-height: 1.5;">This notification was generated securely by {footer_text}. If you did not expect this message, please contact your administrator.</p>
                        <p class="footer-links" style="margin: 0;">
                            <a href="{company_url}" style="color: {accent_color}; text-decoration: none; margin: 0 12px; font-size: 13px; font-weight: 500;">Open Workspace</a>
                            <a href="{company_url}" style="color: {accent_color}; text-decoration: none; margin: 0 12px; font-size: 13px; font-weight: 500;">Help Center</a>
                        </p>
                    </td>
                </tr>
            </table>
        </div>
    </body>
</html>
"""

def button_html(text: str, url: str, bg_color: str = "#4F46E5", text_color: str = "#ffffff") -> str:
    return f'<a href="{url}" style="background-color: {bg_color}; color: {text_color}; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; font-size: 14px; display: inline-block; text-align: center; border: 1px solid rgba(0,0,0,0.1);">{text}</a>'

def info_row_html(label: str, value: str, icon: str = "", accent_color: str = "#4F46E5") -> str:
    # We ignore the `icon` argument since we are removing emojis
    return f"""
    <tr>
        <td style="padding: 10px 0; border-bottom: 1px solid #F3F4F6;">
            <p style="margin: 0; font-size: 14px; color: #374151; line-height: 1.5;">
                <strong style="display: inline-block; min-width: 140px; color: #6B7280; font-weight: 500;">{label}</strong>
                <span style="color: #111827; font-weight: 600;">{value}</span>
            </p>
        </td>
    </tr>
    """

def status_badge_html(text: str, text_color: str, bg_color: str) -> str:
    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em;">{text}</span>'
