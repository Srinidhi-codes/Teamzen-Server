import os
import re
from urllib.parse import urlparse


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


_LAST_SEEN_FRONTEND_URL = ""
_LAST_SEEN_ADMIN_URL = ""


def _is_production() -> bool:
    import os
    try:
        from django.conf import settings
        if not getattr(settings, "DEBUG", True):
            return True
    except Exception:
        pass
    prod_env_keys = [
        "RENDER", "VERCEL", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME",
        "KUBERNETES_SERVICE_HOST", "DYNO", "HEROKU_APP_NAME"
    ]
    if any(os.getenv(k) for k in prod_env_keys):
        return True
    if os.getenv("DEBUG", "False").lower() not in ("true", "1", "yes"):
        return True
    return False


def _derive_client_from_admin(admin_url: str) -> str:
    """Transform an admin domain/URL into the corresponding client portal domain."""
    if not admin_url:
        return ""
    url = admin_url.rstrip("/")
    if "-admin" in url:
        return url.replace("-admin", "-client")
    if "admin." in url:
        return url.replace("admin.", "", 1)
    if ":3001" in url:
        return url.replace(":3001", ":3000")
    return url


def _extract_url_from_request(request, is_admin: bool = False) -> str:
    """Extract and derive portal URL from an incoming HttpRequest."""
    if not request:
        return ""
    try:
        # 1. Custom explicit header
        meta = getattr(request, "META", {}) or {}
        headers = getattr(request, "headers", {}) or {}
        custom_header = (
            meta.get("HTTP_X_FRONTEND_URL")
            or headers.get("x-frontend-url")
            or headers.get("X-Frontend-Url")
        )
        if custom_header and not is_admin:
            clean = str(custom_header).strip().rstrip("/")
            if clean:
                return clean

        custom_admin_header = (
            meta.get("HTTP_X_ADMIN_URL")
            or headers.get("x-admin-url")
            or meta.get("HTTP_X_ADMIN_ORIGIN")
        )
        if custom_admin_header and is_admin:
            clean = str(custom_admin_header).strip().rstrip("/")
            if clean:
                return clean

        # 2. Origin or Referer header
        origin = (
            meta.get("HTTP_ORIGIN")
            or headers.get("origin")
            or meta.get("HTTP_REFERER")
            or headers.get("referer")
            or ""
        ).strip()

        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            if parsed.scheme and parsed.netloc:
                base_origin = f"{parsed.scheme}://{parsed.netloc}"
                if is_admin:
                    return base_origin
                else:
                    return _derive_client_from_admin(base_origin)

        # 3. Request host itself (if not backend)
        host = request.get_host()
        if host and "8000" not in host and "backend" not in host:
            scheme = "https" if request.is_secure() else "http"
            base_host = f"{scheme}://{host}"
            if is_admin:
                return base_host
            return _derive_client_from_admin(base_host)
    except Exception:
        pass
    return ""


def resolve_portal_url(path: str = "", is_admin: bool = False, request=None) -> str:
    """
    Dynamically resolve portal URL from environment variables, incoming request, or Django settings.
    Ensures email action buttons and links point to deployed environments in emails, never broken localhost.
    """
    global _LAST_SEEN_FRONTEND_URL, _LAST_SEEN_ADMIN_URL
    import os

    base = ""

    # Priority 1: Explicit deployed / public URL from environment variables
    if is_admin:
        base = (
            os.getenv("DEPLOYED_ADMIN_URL")
            or os.getenv("PUBLIC_ADMIN_URL")
            or os.getenv("NEXT_PUBLIC_ADMIN_URL")
            or os.getenv("FRONTEND_ADMIN_URL")
            or os.getenv("ADMIN_FRONTEND_URL")
            or ""
        )
    else:
        base = (
            os.getenv("DEPLOYED_FRONTEND_URL")
            or os.getenv("PUBLIC_FRONTEND_URL")
            or os.getenv("DEPLOYED_CLIENT_URL")
            or os.getenv("PUBLIC_CLIENT_URL")
            or os.getenv("NEXT_PUBLIC_FRONTEND_URL")
            or os.getenv("NEXT_PUBLIC_CLIENT_URL")
            or ""
        )

    # Priority 2: Attempt extraction from active request (if not localhost)
    if not base and request:
        extracted = _extract_url_from_request(request, is_admin=is_admin)
        if extracted and "localhost" not in extracted and "127.0.0.1" not in extracted:
            base = extracted
            if is_admin:
                _LAST_SEEN_ADMIN_URL = extracted
            else:
                _LAST_SEEN_FRONTEND_URL = extracted

    # Priority 3: Check recently seen non-localhost dynamic domain
    if not base:
        if is_admin and _LAST_SEEN_ADMIN_URL and "localhost" not in _LAST_SEEN_ADMIN_URL:
            base = _LAST_SEEN_ADMIN_URL
        elif not is_admin and _LAST_SEEN_FRONTEND_URL and "localhost" not in _LAST_SEEN_FRONTEND_URL:
            base = _LAST_SEEN_FRONTEND_URL

    # Priority 4: Search trusted origins in settings
    if not base:
        try:
            from django.conf import settings
            origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", [])) + list(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
            for orig in origins:
                if orig and orig.startswith("https://") and "localhost" not in orig:
                    if is_admin and ("admin" in orig or "3001" in orig):
                        base = orig
                        break
                    elif not is_admin and "admin" not in orig:
                        base = orig
                        break
            if not base:
                for orig in origins:
                    if orig and orig.startswith("https://") and "localhost" not in orig:
                        base = orig if is_admin else _derive_client_from_admin(orig)
                        break
        except Exception:
            pass

    # Priority 5: Fallback to official deployed portal URLs (so emails never point to broken localhost)
    allow_local = os.getenv("ALLOW_LOCALHOST_IN_EMAILS", "False").lower() in ("true", "1")
    if not base:
        if allow_local:
            base = os.getenv("FRONTEND_ADMIN_URL", "http://localhost:3001") if is_admin else os.getenv("CLIENT_URL", "http://localhost:3000")
        else:
            base = (
                "https://teamzen-admin-v2-beta.vercel.app"
                if is_admin
                else "https://teamzen-client-v2-beta.vercel.app"
            )

    # Sanity check: if base ended up as localhost and allow_local is False, force deployed domain
    if not allow_local and ("localhost" in base or "127.0.0.1" in base):
        base = (
            "https://teamzen-admin-v2-beta.vercel.app"
            if is_admin
            else "https://teamzen-client-v2-beta.vercel.app"
        )

    base = str(base).strip().rstrip("/")
    if path:
        clean_path = str(path).strip().lstrip("/")
        return f"{base}/{clean_path}"
    return base


def sanitize_portal_url(url: str = "", default_path: str = "", is_admin: bool = False, request=None) -> str:
    """
    Sanitize an action or portal URL to guarantee it dynamically adheres to .env / request domain configuration.
    1. If url is empty, '#', or None, resolves using resolve_portal_url(default_path, is_admin=is_admin, request=request).
    2. If url points to legacy hardcoded domains (e.g., vercel.app links like teamzen-client.vercel.app,
       teamzen-admin.vercel.app, or a misconfigured backend localhost:8000/admin for a frontend route),
       it rewrites the host to the dynamic portal host while preserving path and query.
    3. If url points to localhost/127.0.0.1 in production or when a valid production domain is known,
       it rewrites to the dynamic production portal URL while preserving path and query.
    4. If url is a relative path (e.g. '/leaves' or 'preboarding'), prepends the dynamic portal base URL.
    5. Genuine external URLs (e.g. drive.google.com, cloudinary.com, docs, etc.) are kept intact.
    """
    if not url or str(url).strip() in ("", "#"):
        return resolve_portal_url(default_path, is_admin=is_admin, request=request)

    url_str = str(url).strip()

    # Relative paths
    if url_str.startswith("/") and not url_str.startswith("//"):
        return resolve_portal_url(url_str, is_admin=is_admin, request=request)

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
            admin_base = resolve_portal_url(is_admin=True, request=request)
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += f"?{parsed.query}"
            clean_sub = path_and_query.lstrip("/")
            return f"{admin_base}/{clean_sub}" if clean_sub else admin_base

        # Check for legacy client vercel hosts
        if any(h in netloc for h in legacy_client_hosts):
            client_base = resolve_portal_url(is_admin=False, request=request)
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += f"?{parsed.query}"
            clean_sub = path_and_query.lstrip("/")
            return f"{client_base}/{clean_sub}" if clean_sub else client_base

        # Check if accidentally pointing to Django admin port for frontend paths
        if "localhost:8000/admin/" in url_str and any(seg in url_str for seg in ["settings", "leaves", "moderation", "dashboard"]):
            target_admin_base = resolve_portal_url(is_admin=True, request=request)
            rel = url_str.split("localhost:8000/admin/", 1)[-1].lstrip("/")
            return f"{target_admin_base}/{rel}"

        # Check for localhost / 127.0.0.1 (always rewrite to deployed portal in emails unless explicitly allowed)
        is_local_host = any(lh in netloc for lh in ["localhost", "127.0.0.1", "0.0.0.0"])
        allow_local = os.getenv("ALLOW_LOCALHOST_IN_EMAILS", "False").lower() in ("true", "1")
        if is_local_host and not allow_local:
            target_base = resolve_portal_url(is_admin=is_admin, request=request)
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += f"?{parsed.query}"
            clean_sub = path_and_query.lstrip("/")
            return f"{target_base}/{clean_sub}" if clean_sub else target_base

        # If it's already an absolute URL with scheme (http/https), return it
        if parsed.scheme in ("http", "https"):
            return url_str

        # If it doesn't have scheme and doesn't look like domain (no dot in first segment), treat as path
        if not parsed.scheme and "/" in url_str:
            return resolve_portal_url(url_str, is_admin=is_admin, request=request)

    except Exception:
        pass

    return url_str or resolve_portal_url(default_path, is_admin=is_admin, request=request)


def sanitize_brand_label(text: str) -> str:
    """Clean company / brand text, stripping copyright symbols, bullets, and accidental duplicates."""
    if not text:
        return "Teamzen HRMS"
    # Remove copyright, bullet, and pipe characters
    cleaned = re.sub(r"[©\u00a9\u2022•|]", " ", str(text))
    # Deduplicate repeated words (e.g. "Teamzen Teamzen" -> "Teamzen")
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    deduped = []
    for t in tokens:
        if not deduped or t.lower() != deduped[-1].lower():
            deduped.append(t)
    res = " ".join(deduped)
    return res or "Teamzen HRMS"


def get_base_template(
    title: str,
    body_content: str,
    accent_color: str = "#0F766E",
    accent_light: str = "#CCFBF1",
    logo_url: str = "",
    footer_text: str = "Teamzen HRMS",
    company_url: str = "",
    show_header_title: bool = True,
    header_subtitle: str = "",
    eyebrow_text: str = "",
) -> str:
    """Generate the base responsive HTML email template matching Teamzen executive design."""
    safe_company_url = sanitize_portal_url(company_url)
    clean_footer_text = sanitize_brand_label(footer_text)

    # Clean eyebrow tag (e.g. TEAMZEN or ACME CORP)
    raw_eyebrow = eyebrow_text or clean_footer_text
    clean_eyebrow = sanitize_brand_label(raw_eyebrow)
    # Remove redundant suffix like HRMS / Workspace from eyebrow tag for ultra-clean header
    clean_eyebrow = re.sub(r"\b(HRMS|Workspace|Portal|System)\b", "", clean_eyebrow, flags=re.IGNORECASE).strip() or "TEAMZEN"

    resolved_logo = resolve_email_logo_url(logo_url)
    logo_html = (
        f'<img src="{resolved_logo}" alt="{clean_footer_text}" width="120" height="42" '
        f'style="display: block; max-width: 120px; max-height: 42px; height: auto; object-fit: contain; '
        f'background: #FFFFFF; border-radius: 8px; margin-left: auto;" />'
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

    # Wrap naked body_content in table row with executive padding if not already table markup
    stripped_body = (body_content or "").strip()
    if stripped_body and not stripped_body.lower().startswith("<tr"):
        formatted_body = f"""
        <tr>
            <td class="content-block" bgcolor="#FFFFFF" style="padding: 28px 36px 28px 36px; background-color: #FFFFFF; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                {stripped_body}
            </td>
        </tr>
        """
    else:
        formatted_body = stripped_body

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
            .header {{ padding: 24px 36px 20px 36px; background-color: #FFFFFF !important; border-bottom: 1px solid #F1F5F9; }}
            .content {{ padding: 0; background-color: #FFFFFF !important; }}
            .footer {{ padding: 24px 36px; background-color: #F8FAFC !important; border-top: 1px solid #E2E8F0; text-align: center; }}
            .eyebrow {{ margin: 0 0 6px 0; color: {accent_color} !important; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.12em; }}
            .title {{ margin: 0; color: #0F172A !important; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }}
            p {{ font-size: 15px; color: #334155 !important; line-height: 1.65; margin: 0 0 16px 0; }}
            .footer-note {{ color: #64748B !important; font-size: 12px; margin: 0 0 12px 0; line-height: 1.5; }}
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
                .header, .footer {{ padding: 20px 20px; }}
                .hero-section {{ padding: 24px 20px 18px 20px !important; }}
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
                    <td class="header" bgcolor="#FFFFFF" style="padding: 24px 36px 18px 36px; background-color: #FFFFFF; border-bottom: 1px solid #F1F5F9;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                                <td style="vertical-align: middle;">
                                    <p class="eyebrow" style="margin: 0 0 6px 0; color: {accent_color}; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.12em; line-height: 1.2;">{clean_eyebrow}</p>
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
                        {formatted_body}
                        </table>
                    </td>
                </tr>
                <tr>
                    <td class="footer" bgcolor="#F8FAFC" style="padding: 24px 36px; background-color: #F8FAFC; border-top: 1px solid #E2E8F0; text-align: center;">
                        <p class="footer-note" style="margin: 0 0 12px 0; color: #64748B; font-size: 12px; line-height: 1.5;">This notification was delivered securely by {clean_footer_text}. If you did not expect this message, please notify your system administrator.</p>
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


def button_html(text: str, url: str, bg_color: str = "#0F766E", text_color: str = "#FFFFFF") -> str:
    """Bulletproof corporate button component matching Teamzen theme.
    Includes auto-healing guardrail to prevent inverted args (url, text) or raw URLs in button text.
    """
    arg1 = str(text or "").strip()
    arg2 = str(url or "").strip()

    def looks_like_url(val: str) -> bool:
        if not val:
            return False
        v_low = val.lower()
        return (
            v_low.startswith(("http://", "https://", "www.", "/", "#"))
            or "://" in v_low
            or ".vercel.app" in v_low
            or ".com" in v_low
            or ".io" in v_low
            or ".net" in v_low
            or ".org" in v_low
        )

    is_arg1_url = looks_like_url(arg1)
    is_arg2_url = looks_like_url(arg2)

    if is_arg1_url and not is_arg2_url:
        # Inverted! arg1 is URL, arg2 is button text
        btn_label = arg2 or "Open in Portal"
        btn_url = arg1
    elif not is_arg1_url and is_arg2_url:
        btn_label = arg1 or "Open in Portal"
        btn_url = arg2
    elif is_arg1_url and is_arg2_url:
        # Both are URLs - fallback label to prevent raw URL inside button
        btn_label = "Open in Portal"
        btn_url = arg2 or arg1
    else:
        btn_label = arg1 or "Open in Portal"
        btn_url = arg2 or "/"

    # Safety: Never allow a raw URL to be displayed as button text
    if looks_like_url(btn_label):
        btn_label = "Open in Portal"

    safe_url = sanitize_portal_url(btn_url)

    return (
        f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display: inline-block; margin: 0;">'
        f'<tr><td align="center" style="border-radius: 8px; background-color: {bg_color};">'
        f'<a href="{safe_url}" target="_blank" style="background-color: {bg_color}; color: {text_color} !important; '
        f'text-decoration: none; padding: 13px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; '
        f'display: inline-block; text-align: center; letter-spacing: -0.2px; '
        f'font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">'
        f'{btn_label} &rarr;'
        f'</a>'
        f'</td></tr></table>'
    )


def info_row_html(label: str, value: str, icon: str = "", accent_color: str = "#0F766E") -> str:
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


def status_badge_html(text: str, text_color: str = "#0F766E", bg_color: str = "#FFFFFF") -> str:
    """Clean, high-contrast pill status badge matching Image 4."""
    return (
        f'<span style="background-color: {bg_color}; color: {text_color}; padding: 5px 14px; '
        f'border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; '
        f'letter-spacing: 0.08em; display: inline-block; border: 1px solid rgba(15, 118, 110, 0.15); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);">{text}</span>'
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
        "info": {"bg": "#F0FDF4", "border": "#A7F3D0", "left": "#0F766E", "title": "#0F766E", "text": "#115E59"},
        "warning": {"bg": "#FFFBEB", "border": "#FDE68A", "left": "#D97706", "title": "#B45309", "text": "#78350F"},
        "danger": {"bg": "#FEF2F2", "border": "#FECACA", "left": "#DC2626", "title": "#B91C1C", "text": "#7F1D1D"},
        "success": {"bg": "#F0FDF4", "border": "#A7F3D0", "left": "#0F766E", "title": "#0F766E", "text": "#115E59"},
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
    badge_color: str = "#0F766E",
    badge_bg: str = "#FFFFFF",
    hero_bg: str = "#CCFBF1",
) -> str:
    """Reusable hero header block matching executive design in Image 4."""
    # Fix headline capitalization cleanly
    clean_headline = (headline or "").strip()
    if clean_headline.lower() in ("requested", "leave requested", "new leave request"):
        clean_headline = "Leave Request Submitted"
    elif clean_headline.lower() == "approved":
        clean_headline = "Leave Request Approved"
    elif clean_headline.lower() == "rejected":
        clean_headline = "Leave Request Declined"
    elif clean_headline.lower() == "cancelled":
        clean_headline = "Leave Request Cancelled"
    elif clean_headline.islower() or clean_headline == clean_headline.lower():
        clean_headline = clean_headline.replace("_", " ").title()

    badge_html = ""
    if badge_label:
        badge_html = f'<div style="margin-bottom: 14px;">{status_badge_html(badge_label, badge_color or "#0F766E", badge_bg or "#FFFFFF")}</div>'

    sub_html = ""
    if subtitle:
        sub_html = f'<p style="margin: 0; font-size: 14px; color: #475569;">{subtitle}</p>'

    return f"""
    <tr>
        <td class="hero-section" bgcolor="{hero_bg}" style="padding: 36px 36px 28px 36px; text-align: center; background-color: {hero_bg};">
            {badge_html}
            <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; line-height: 1.3;">
                {clean_headline}
            </h1>
            {sub_html}
        </td>
    </tr>
    """

