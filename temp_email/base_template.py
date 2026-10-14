def logo_badge_html(accent_color: str, brand_char: str = "T") -> str:
    """Email-safe fallback mark when no hosted logo URL is available."""
    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display: inline-block;">
        <tr>
            <td align="center" valign="middle" style="width: 44px; height: 44px; border-radius: 10px; background-color: {accent_color}; color: #FFFFFF; font-size: 20px; font-weight: 800; line-height: 44px; text-align: center; letter-spacing: -0.5px;">
                {brand_char}
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


def resolve_portal_url(path: str = "", is_admin: bool = False) -> str:
    """
    Dynamically resolve portal URL from environment variables / Django settings.
    Ensures email action buttons link to whatever URL is configured in .env.
    """
    import os
    base = ""
    try:
        from django.conf import settings
        if is_admin:
            base = (
                os.getenv("FRONTEND_ADMIN_URL")
                or os.getenv("ADMIN_FRONTEND_URL")
                or getattr(settings, "FRONTEND_ADMIN_URL", "")
                or os.getenv("CLIENT_URL")
                or os.getenv("FRONTEND_URL")
                or getattr(settings, "CLIENT_URL", "")
                or "http://localhost:3000"
            )
        else:
            base = (
                os.getenv("CLIENT_URL")
                or os.getenv("FRONTEND_URL")
                or getattr(settings, "CLIENT_URL", "")
                or getattr(settings, "FRONTEND_URL", "")
                or os.getenv("NEXT_PUBLIC_CLIENT_URL")
                or "http://localhost:3000"
            )
    except Exception:
        import os
        if is_admin:
            base = (
                os.getenv("FRONTEND_ADMIN_URL")
                or os.getenv("ADMIN_FRONTEND_URL")
                or os.getenv("CLIENT_URL")
                or "http://localhost:3000"
            )
        else:
            base = (
                os.getenv("CLIENT_URL")
                or os.getenv("FRONTEND_URL")
                or "http://localhost:3000"
            )

    base = str(base).strip().rstrip("/")
    if path:
        clean_path = str(path).strip().lstrip("/")
        return f"{base}/{clean_path}"
    return base


def sanitize_portal_url(url: str = "", default_path: str = "", is_admin: bool = False) -> str:
    """
    Sanitize an action or portal URL to guarantee it dynamically adheres to .env configuration.
    1. If url is empty, '#', or None, resolves using resolve_portal_url(default_path, is_admin=is_admin).
    2. If url points to legacy hardcoded domains (e.g., vercel.app links like teamzen-client.vercel.app,
       teamzen-admin.vercel.app, or a misconfigured backend localhost:8000/admin for a frontend route),
       it rewrites the host to the environment's configured portal host while preserving path and query.
    3. If url is a relative path (e.g. '/leaves' or 'leaves'), prepends the dynamic portal base URL.
    4. Genuine external URLs (e.g. drive.google.com, cloudinary.com, docs, etc.) are kept intact.
    """
    if not url or str(url).strip() in ("", "#"):
        return resolve_portal_url(default_path, is_admin=is_admin)

    url_str = str(url).strip()

    # Relative paths
    if url_str.startswith("/") and not url_str.startswith("//"):
        return resolve_portal_url(url_str, is_admin=is_admin)

    # Legacy or deployed vercel domains that need dynamic substitution
    legacy_admin_hosts = [
        "teamzen-admin.vercel.app",
        "teamzen-admin-v2-beta.vercel.app",
    ]
    legacy_client_hosts = [
        "teamzen-client.vercel.app",
        "teamzen.vercel.app",
    ]

    from urllib.parse import urlparse

    try:
        parsed = urlparse(url_str)
        netloc = parsed.netloc.lower()

        # Check for legacy admin vercel hosts
        if any(h in netloc for h in legacy_admin_hosts):
            admin_base = resolve_portal_url(is_admin=True)
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += f"?{parsed.query}"
            clean_sub = path_and_query.lstrip("/")
            return f"{admin_base}/{clean_sub}" if clean_sub else admin_base

        # Check for legacy client vercel hosts
        if any(h in netloc for h in legacy_client_hosts):
            client_base = resolve_portal_url(is_admin=False)
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += f"?{parsed.query}"
            clean_sub = path_and_query.lstrip("/")
            return f"{client_base}/{clean_sub}" if clean_sub else client_base

        # Check if accidentally pointing to Django admin port for frontend paths
        if "localhost:8000/admin/" in url_str and any(seg in url_str for seg in ["settings", "leaves", "moderation", "dashboard"]):
            target_admin_base = resolve_portal_url(is_admin=True)
            rel = url_str.split("localhost:8000/admin/", 1)[-1].lstrip("/")
            return f"{target_admin_base}/{rel}"

        # If it's already an absolute URL with scheme (http/https), return it
        if parsed.scheme in ("http", "https"):
            return url_str

        # If it doesn't have scheme and doesn't look like domain (no dot in first segment), treat as path
        if not parsed.scheme and "/" in url_str:
            return resolve_portal_url(url_str, is_admin=is_admin)

    except Exception:
        pass

    return url_str or resolve_portal_url(default_path, is_admin=is_admin)


def get_base_template(
    title: str,
    body_content: str,
    accent_color: str = "#4F46E5",
    accent_light: str = "#EEF2FF",
    logo_url: str = "",
    footer_text: str = "Teamzen HRMS",
    company_url: str = "",
    show_header_title: bool = True,
    header_subtitle: str = "",
) -> str:
    """Generate the base responsive HTML email template."""
    safe_company_url = sanitize_portal_url(company_url)
    resolved_logo = resolve_email_logo_url(logo_url)
    logo_html = (
        f'<img src="{resolved_logo}" alt="{footer_text}" width="120" height="48" '
        f'style="display: block; width: 120px; height: 48px; object-fit: contain; '
        f'background: #FFFFFF; border-radius: 8px;" />'
        if resolved_logo
        else logo_badge_html(accent_color)
    )


    header_title_html = ""
    if show_header_title and title:
        sub_html = f'<p style="margin: 4px 0 0 0; color: #64748B; font-size: 14px;">{header_subtitle}</p>' if header_subtitle else ""
        header_title_html = f"""
            <h1 class="title" style="margin: 0; color: #0F172A; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.3;">{title}</h1>
            {sub_html}
        """

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
            body {{ background-color: #F8FAFC !important; background: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 40px 16px; color: #0F172A !important; -webkit-font-smoothing: antialiased; }}
            .shell {{ max-width: 600px; margin: 0 auto; }}
            .container {{ background-color: #FFFFFF !important; border: 1px solid #E2E8F0; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); }}
            .topline {{ height: 4px; background-color: {accent_color}; }}
            .header {{ padding: 28px 36px 20px 36px; background-color: #FFFFFF !important; border-bottom: 1px solid #F1F5F9; }}
            .content {{ padding: 0; background-color: #FFFFFF !important; }}
            .footer {{ padding: 28px 36px; background-color: #F8FAFC !important; border-top: 1px solid #E2E8F0; text-align: center; }}
            .eyebrow {{ margin: 0 0 6px 0; color: #64748B !important; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }}
            .title {{ margin: 0; color: #0F172A !important; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }}
            p {{ font-size: 15px; color: #334155 !important; line-height: 1.65; margin: 0 0 16px 0; }}
            .footer-note {{ color: #64748B !important; font-size: 12px; margin: 0 0 14px 0; line-height: 1.5; }}
            .footer-links a {{ color: {accent_color} !important; text-decoration: none; margin: 0 10px; font-size: 12px; font-weight: 600; }}
            
            @media (prefers-color-scheme: dark) {{
                body {{ background-color: #F8FAFC !important; color: #0F172A !important; }}
                .container, .content, .header {{ background-color: #FFFFFF !important; }}
                .footer {{ background-color: #F8FAFC !important; }}
                .title, h1, p {{ color: #0F172A !important; }}
                .eyebrow, .footer-note {{ color: #64748B !important; }}
            }}
            @media only screen and (max-width: 600px) {{
                body {{ padding: 16px 8px; }}
                .header, .footer {{ padding: 22px 20px; }}
                .hero-section {{ padding: 28px 20px 20px 20px !important; }}
                .content-block {{ padding: 20px 20px 16px 20px !important; }}
                .title {{ font-size: 20px; }}
            }}
        </style>
    </head>
    <body style="background-color: #F8FAFC; margin: 0; padding: 40px 16px; color: #0F172A;">
        <div class="shell">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" class="container" bgcolor="#FFFFFF" style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; overflow: hidden;">
                <tr>
                    <td class="topline" bgcolor="{accent_color}" style="height: 4px; background-color: {accent_color}; font-size: 0; line-height: 0;">&nbsp;</td>
                </tr>
                <tr>
                    <td class="header" bgcolor="#FFFFFF" style="padding: 28px 36px 20px 36px; background-color: #FFFFFF; border-bottom: 1px solid #F1F5F9;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                                <td style="vertical-align: middle;">
                                    <p class="eyebrow" style="margin: 0 0 4px 0; color: #64748B; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;">{footer_text}</p>
                                    {header_title_html}
                                </td>
                                <td style="width: 130px; text-align: right; vertical-align: middle;">
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
                    <td class="footer" bgcolor="#F8FAFC" style="padding: 28px 36px; background-color: #F8FAFC; border-top: 1px solid #E2E8F0; text-align: center;">
                        <p class="footer-note" style="margin: 0 0 12px 0; color: #64748B; font-size: 12px; line-height: 1.5;">This notification was delivered securely by {footer_text}. If you did not expect this message, please notify your system administrator.</p>
                        <p class="footer-links" style="margin: 0;">
                            <a href="{safe_company_url}" style="color: {accent_color}; text-decoration: none; margin: 0 10px; font-size: 12px; font-weight: 600;">Workspace Portal</a>
                            <span style="color: #CBD5E1;">&bull;</span>
                            <a href="{safe_company_url}" style="color: {accent_color}; text-decoration: none; margin: 0 10px; font-size: 12px; font-weight: 600;">Help &amp; Support</a>
                        </p>
                    </td>
                </tr>
            </table>
        </div>
    </body>
</html>
"""


def button_html(text: str, url: str, bg_color: str = "#4F46E5", text_color: str = "#FFFFFF") -> str:
    """Bulletproof corporate button component."""
    safe_url = sanitize_portal_url(url)
    return (
        f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display: inline-block; margin: 0 auto;">'
        f'<tr><td align="center" style="border-radius: 8px; background-color: {bg_color};">'
        f'<a href="{safe_url}" style="background-color: {bg_color}; color: {text_color}; text-decoration: none; padding: 12px 28px; '
        f'border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block; text-align: center; '
        f'letter-spacing: -0.2px; border: 1px solid rgba(0, 0, 0, 0.08); font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">{text}</a>'
        f'</td></tr></table>'
    )


def info_row_html(label: str, value: str, icon: str = "", accent_color: str = "#4F46E5") -> str:
    """Single key-value row (ignores icon to strictly prevent unwanted emojis)."""
    return f"""
    <tr>
        <td style="padding: 10px 0; border-bottom: 1px solid #F1F5F9;">
            <p style="margin: 0; font-size: 14px; color: #334155; line-height: 1.5;">
                <strong style="display: inline-block; min-width: 140px; color: #64748B; font-weight: 500;">{label}</strong>
                <span style="color: #0F172A; font-weight: 600;">{value}</span>
            </p>
        </td>
    </tr>
    """


def status_badge_html(text: str, text_color: str, bg_color: str) -> str:
    """Clean, high-contrast status badge (uppercase, subtle radius)."""
    return (
        f'<span style="background-color: {bg_color}; color: {text_color}; padding: 4px 10px; '
        f'border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; '
        f'letter-spacing: 0.06em; display: inline-block; border: 1px solid rgba(0, 0, 0, 0.05);">{text}</span>'
    )


def card_table_html(rows: list, card_title: str = "") -> str:
    """
    Renders a sleek, rounded card table with key-value rows.
    rows: list of tuples (label, value) or (label, value, is_highlight)
    """
    title_markup = ""
    if card_title:
        title_markup = f"""
        <tr>
            <td colspan="2" style="padding-bottom: 12px; border-bottom: 1px solid #E2E8F0;">
                <p style="margin: 0; font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.08em;">
                    {card_title}
                </p>
            </td>
        </tr>
        """

    rows_markup = ""
    for item in rows:
        if not item or len(item) < 2:
            continue
        label, value = item[0], item[1]
        if value is None or value == "":
            continue
        rows_markup += f"""
        <tr>
            <td style="padding: 9px 0; font-size: 13px; color: #64748B; width: 140px; vertical-align: top; border-bottom: 1px solid #F1F5F9;">
                {label}
            </td>
            <td style="padding: 9px 0; font-size: 13px; color: #0F172A; font-weight: 600; vertical-align: top; border-bottom: 1px solid #F1F5F9;">
                {value}
            </td>
        </tr>
        """

    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#F8FAFC" style="background-color: #F8FAFC; border-radius: 12px; border: 1px solid #E2E8F0;">
        <tr>
            <td style="padding: 18px 22px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                    {title_markup}
                    {rows_markup}
                </table>
            </td>
        </tr>
    </table>
    """


def alert_box_html(text: str, title: str = "", level: str = "info") -> str:
    """
    Corporate callout container (clean border, subtle background, zero emojis).
    level: 'info' | 'warning' | 'danger' | 'success' | 'neutral'
    """
    configs = {
        "info": {"bg": "#F0F9FF", "border": "#BAE6FD", "left": "#0284C7", "title": "#0369A1", "text": "#0C4A6E"},
        "warning": {"bg": "#FFFBEB", "border": "#FDE68A", "left": "#D97706", "title": "#B45309", "text": "#78350F"},
        "danger": {"bg": "#FEF2F2", "border": "#FECACA", "left": "#DC2626", "title": "#B91C1C", "text": "#7F1D1D"},
        "success": {"bg": "#F0FDF4", "border": "#BBF7D0", "left": "#16A34A", "title": "#15803D", "text": "#14532D"},
        "neutral": {"bg": "#F8FAFC", "border": "#E2E8F0", "left": "#64748B", "title": "#334155", "text": "#475569"},
    }
    cfg = configs.get(level.lower(), configs["info"])
    title_html = (
        f'<p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: {cfg["title"]}; text-transform: uppercase; letter-spacing: 0.05em;">{title}</p>'
        if title else ""
    )
    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="{cfg['bg']}" style="background-color: {cfg['bg']}; border: 1px solid {cfg['border']}; border-left: 4px solid {cfg['left']}; border-radius: 8px;">
        <tr>
            <td style="padding: 14px 18px;">
                {title_html}
                <p style="margin: 0; font-size: 13px; color: {cfg['text']}; line-height: 1.6;">{text}</p>
            </td>
        </tr>
    </table>
    """


def hero_section_html(
    headline: str,
    subtitle: str = "",
    badge_label: str = "",
    badge_color: str = "",
    badge_bg: str = "",
    hero_bg: str = "#F8FAFC",
) -> str:
    """Reusable hero header block matching executive design."""
    badge_html = ""
    if badge_label:
        b_color = badge_color or "#0F766E"
        b_bg = badge_bg or "#CCFBF1"
        badge_html = f'<div style="margin-bottom: 12px;">{status_badge_html(badge_label, b_color, b_bg)}</div>'

    sub_html = ""
    if subtitle:
        sub_html = f'<p style="margin: 0; font-size: 14px; color: #475569;">{subtitle}</p>'

    return f"""
    <tr>
        <td class="hero-section" bgcolor="{hero_bg}" style="padding: 36px 36px 24px 36px; text-align: center; background-color: {hero_bg};">
            {badge_html}
            <h1 style="margin: 0 0 8px 0; font-size: 23px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; line-height: 1.3;">
                {headline}
            </h1>
            {sub_html}
        </td>
    </tr>
    """

