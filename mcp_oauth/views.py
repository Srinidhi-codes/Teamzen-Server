"""Browser connect pages: login, OTP, device code entry, consent, success."""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from mcp_oauth.tokens import (
    cache_device_plaintext,
    issue_bound_mcp_token,
    normalize_scopes,
    set_jwt_cookies,
)
from organizations.models import MCP_SCOPE_CHOICES, MCPAuthCode, MCPDeviceCode
from users.authentication import CookieJWTAuthentication

User = get_user_model()


def _authenticate_request(request):
    """Return user from CookieJWT if present."""
    try:
        result = CookieJWTAuthentication().authenticate(request)
        if result:
            return result[0]
    except Exception:
        pass
    return None


def _mcp_public_url(request=None) -> str:
    """
    Public MCP streamable-HTTP URL for Cursor mcp.json snippets.
    Prefer MCP_PUBLIC_URL, then MCP_SERVER_URL, else local default.
    """
    for key in ("MCP_PUBLIC_URL", "MCP_SERVER_URL"):
        val = (os.environ.get(key) or "").strip().rstrip("/")
        if val:
            return val if val.endswith("/mcp") else f"{val}/mcp"
    return "http://localhost:8001/mcp"


def _success_ctx(request=None, **extra) -> dict:
    ctx = {"mcp_url": _mcp_public_url(request), "denied": False, "token": None, "device_flow": False}
    ctx.update(extra)
    return ctx


def _next_url(request, default_name="mcp_oauth:connect"):
    nxt = request.GET.get("next") or request.POST.get("next") or ""
    if nxt.startswith("/mcp/"):
        return nxt
    return reverse(default_name)


class ConnectHomeView(View):
    """Manual connect: login → consent → show token once."""

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = _authenticate_request(request)
        if not user:
            return redirect(
                reverse("mcp_oauth:login") + "?" + urlencode({"next": reverse("mcp_oauth:connect")})
            )
        return redirect(reverse("mcp_oauth:consent"))


class LoginView(View):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = _authenticate_request(request)
        if user:
            return redirect(_next_url(request, "mcp_oauth:consent"))
        return render(
            request,
            "mcp_oauth/login.html",
            {"next": request.GET.get("next", reverse("mcp_oauth:consent")), "error": None},
        )

    def post(self, request):
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        nxt = _next_url(request, "mcp_oauth:consent")
        user = authenticate(username=email, password=password)
        if not user:
            return render(
                request,
                "mcp_oauth/login.html",
                {"next": nxt, "error": "Invalid email or password", "email": email},
                status=400,
            )
        if getattr(user, "is_totp_enabled", False):
            import uuid

            temp = str(uuid.uuid4())
            cache.set(f"temp_totp_session_{temp}", user.id, timeout=300)
            return render(
                request,
                "mcp_oauth/totp.html",
                {"temp_token": temp, "next": nxt, "error": None},
            )
        resp = redirect(nxt)
        set_jwt_cookies(resp, user, request)
        return resp


class OTPView(View):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return render(
            request,
            "mcp_oauth/otp.html",
            {
                "next": request.GET.get("next", reverse("mcp_oauth:consent")),
                "error": None,
                "sent": False,
                "email": "",
            },
        )

    def post(self, request):
        email = (request.POST.get("email") or "").strip().lower()
        action = request.POST.get("action") or "send"
        nxt = _next_url(request, "mcp_oauth:consent")

        if action == "send":
            if not email:
                return render(
                    request,
                    "mcp_oauth/otp.html",
                    {"next": nxt, "error": "Email required", "sent": False, "email": email},
                    status=400,
                )
            try:
                User.objects.get(email__iexact=email, is_active=True)
            except User.DoesNotExist:
                return render(
                    request,
                    "mcp_oauth/otp.html",
                    {"next": nxt, "error": "No account for that email", "sent": False, "email": email},
                    status=400,
                )
            import random

            code = f"{random.randint(100000, 999999)}"
            cache.set(f"otp_{email}", code, timeout=300)
            try:
                from notifications.email_backends import BrevoHTTPBackend
                from temp_email.otp_email import get_otp_email_html
                from django.core.mail import EmailMultiAlternatives
                from django.conf import settings

                html = get_otp_email_html(code)
                msg = EmailMultiAlternatives(
                    subject="Teamzen MCP login code",
                    body=f"Your code is {code}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@teamzen.app"),
                    to=[email],
                )
                msg.attach_alternative(html, "text/html")
                try:
                    BrevoHTTPBackend().send_messages([msg])
                except Exception:
                    msg.send(fail_silently=True)
            except Exception:
                from django.conf import settings as djsettings

                if djsettings.DEBUG:
                    return render(
                        request,
                        "mcp_oauth/otp.html",
                        {
                            "next": nxt,
                            "error": None,
                            "sent": True,
                            "email": email,
                            "dev_otp": code,
                        },
                    )
            return render(
                request,
                "mcp_oauth/otp.html",
                {"next": nxt, "error": None, "sent": True, "email": email},
            )

        # verify
        otp = (request.POST.get("otp") or "").strip()
        cached = cache.get(f"otp_{email}")
        if not cached or str(cached) != otp:
            return render(
                request,
                "mcp_oauth/otp.html",
                {"next": nxt, "error": "Invalid or expired OTP", "sent": True, "email": email},
                status=400,
            )
        cache.delete(f"otp_{email}")
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return render(
                request,
                "mcp_oauth/otp.html",
                {"next": nxt, "error": "User not found", "sent": False, "email": email},
                status=400,
            )
        if getattr(user, "is_totp_enabled", False):
            import uuid

            temp = str(uuid.uuid4())
            cache.set(f"temp_totp_session_{temp}", user.id, timeout=300)
            return render(
                request,
                "mcp_oauth/totp.html",
                {"temp_token": temp, "next": nxt, "error": None},
            )
        resp = redirect(nxt)
        set_jwt_cookies(resp, user, request)
        return resp


class TOTPView(View):
    def post(self, request):
        import pyotp

        temp = request.POST.get("temp_token") or ""
        code = (request.POST.get("code") or "").strip()
        nxt = _next_url(request, "mcp_oauth:consent")
        user_id = cache.get(f"temp_totp_session_{temp}")
        if not user_id:
            return render(
                request,
                "mcp_oauth/totp.html",
                {"temp_token": temp, "next": nxt, "error": "Session expired — login again"},
                status=400,
            )
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return redirect(reverse("mcp_oauth:login"))
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code, valid_window=1):
            return render(
                request,
                "mcp_oauth/totp.html",
                {"temp_token": temp, "next": nxt, "error": "Invalid authenticator code"},
                status=400,
            )
        cache.delete(f"temp_totp_session_{temp}")
        resp = redirect(nxt)
        set_jwt_cookies(resp, user, request)
        return resp


class DeviceEntryView(View):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return render(
            request,
            "mcp_oauth/device.html",
            {
                "user_code": request.GET.get("user_code", ""),
                "error": None,
            },
        )

    def post(self, request):
        user_code = (request.POST.get("user_code") or "").strip().upper()
        try:
            row = MCPDeviceCode.objects.get(user_code=user_code)
        except MCPDeviceCode.DoesNotExist:
            return render(
                request,
                "mcp_oauth/device.html",
                {"user_code": user_code, "error": "Invalid code"},
                status=400,
            )
        if row.expires_at <= timezone.now() or row.status != MCPDeviceCode.STATUS_PENDING:
            return render(
                request,
                "mcp_oauth/device.html",
                {"user_code": user_code, "error": "Code expired or already used"},
                status=400,
            )
        request.session["mcp_device_user_code"] = user_code
        user = _authenticate_request(request)
        if not user:
            return redirect(
                reverse("mcp_oauth:login")
                + "?"
                + urlencode({"next": reverse("mcp_oauth:consent")})
            )
        return redirect(reverse("mcp_oauth:consent"))


class ConsentView(View):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = _authenticate_request(request)
        if not user:
            return redirect(
                reverse("mcp_oauth:login")
                + "?"
                + urlencode({"next": reverse("mcp_oauth:consent")})
            )
        if not user.organization_id:
            return render(
                request,
                "mcp_oauth/error.html",
                {"message": "Your account has no organization. Contact an admin."},
            )
        device_code_row = None
        user_code = request.session.get("mcp_device_user_code")
        if user_code:
            device_code_row = MCPDeviceCode.objects.filter(
                user_code=user_code, status=MCPDeviceCode.STATUS_PENDING
            ).first()

        return render(
            request,
            "mcp_oauth/consent.html",
            {
                "user": user,
                "scopes": MCP_SCOPE_CHOICES,
                "selected_scopes": list(MCP_SCOPE_CHOICES),
                "device": device_code_row,
                "client_id": (device_code_row.client_id if device_code_row else "cursor"),
                "error": None,
            },
        )

    def post(self, request):
        user = _authenticate_request(request)
        if not user:
            return redirect(reverse("mcp_oauth:login"))
        if not user.organization_id:
            return render(
                request,
                "mcp_oauth/error.html",
                {"message": "Your account has no organization."},
            )

        action = request.POST.get("action") or "approve"
        scopes = normalize_scopes(request.POST.getlist("scopes"))
        user_code = request.session.get("mcp_device_user_code")
        device = None
        if user_code:
            device = MCPDeviceCode.objects.filter(user_code=user_code).first()

        if action == "deny":
            if device and device.status == MCPDeviceCode.STATUS_PENDING:
                device.status = MCPDeviceCode.STATUS_DENIED
                device.save(update_fields=["status"])
            request.session.pop("mcp_device_user_code", None)
            return render(request, "mcp_oauth/success.html", _success_ctx(request, denied=True))

        # approve
        token, plaintext = issue_bound_mcp_token(
            user=user,
            scopes=scopes,
            name=f"MCP Sign-in ({device.client_id if device else 'manual'})",
        )

        if device and device.status == MCPDeviceCode.STATUS_PENDING:
            if device.expires_at <= timezone.now():
                device.status = MCPDeviceCode.STATUS_EXPIRED
                device.save(update_fields=["status"])
                return render(
                    request,
                    "mcp_oauth/error.html",
                    {"message": "Device code expired. Start again from Cursor."},
                )
            device.status = MCPDeviceCode.STATUS_APPROVED
            device.user = user
            device.organization_id = user.organization_id
            device.scopes = scopes
            device.access_token = token
            device.save(
                update_fields=["status", "user", "organization", "scopes", "access_token"]
            )
            cache_device_plaintext(device.device_code, plaintext)
            request.session.pop("mcp_device_user_code", None)
            # Device clients poll for token — don't show plaintext unless manual
            return render(
                request,
                "mcp_oauth/success.html",
                _success_ctx(request, device_flow=True),
            )

        # Manual connect: show token once
        return render(
            request,
            "mcp_oauth/success.html",
            _success_ctx(request, token=plaintext, scopes=scopes),
        )


class AuthorizeRedirectView(View):
    """
    GET /mcp/oauth/authorize — OAuth authorize for redirect clients.
    Query: client_id, redirect_uri, scope, state, response_type=code
    """

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = _authenticate_request(request)
        params = request.GET.copy()
        if not user:
            q = urlencode({"next": request.get_full_path()})
            return redirect(reverse("mcp_oauth:login") + "?" + q)

        if (params.get("response_type") or "code") != "code":
            return render(
                request,
                "mcp_oauth/error.html",
                {"message": "Only response_type=code is supported."},
            )

        request.session["mcp_oauth_authorize"] = {
            "client_id": params.get("client_id") or "cursor",
            "redirect_uri": params.get("redirect_uri") or "",
            "scope": params.get("scope") or "",
            "state": params.get("state") or "",
        }
        return redirect(reverse("mcp_oauth:consent_oauth"))

    def post(self, request):
        return self.get(request)


class ConsentOAuthView(View):
    """Consent that redirects with ?code= for authorization_code grant."""

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = _authenticate_request(request)
        if not user:
            return redirect(reverse("mcp_oauth:login"))
        meta = request.session.get("mcp_oauth_authorize") or {}
        scopes = normalize_scopes((meta.get("scope") or "").replace(",", " ").split())
        return render(
            request,
            "mcp_oauth/consent.html",
            {
                "user": user,
                "scopes": MCP_SCOPE_CHOICES,
                "selected_scopes": scopes or list(MCP_SCOPE_CHOICES),
                "device": None,
                "client_id": meta.get("client_id") or "cursor",
                "oauth_redirect": True,
                "error": None,
            },
        )

    def post(self, request):
        user = _authenticate_request(request)
        if not user or not user.organization_id:
            return redirect(reverse("mcp_oauth:login"))
        meta = request.session.get("mcp_oauth_authorize") or {}
        action = request.POST.get("action") or "approve"
        redirect_uri = meta.get("redirect_uri") or ""
        state = meta.get("state") or ""

        if action == "deny" or not redirect_uri:
            request.session.pop("mcp_oauth_authorize", None)
            if redirect_uri:
                sep = "&" if "?" in redirect_uri else "?"
                return redirect(f"{redirect_uri}{sep}error=access_denied&state={state}")
            return render(request, "mcp_oauth/success.html", _success_ctx(request, denied=True))

        scopes = normalize_scopes(request.POST.getlist("scopes"))
        code = secrets.token_urlsafe(32)
        MCPAuthCode.objects.create(
            code=code,
            client_id=meta.get("client_id") or "cursor",
            redirect_uri=redirect_uri,
            scopes=scopes,
            user=user,
            organization_id=user.organization_id,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        request.session.pop("mcp_oauth_authorize", None)
        sep = "&" if "?" in redirect_uri else "?"
        return redirect(f"{redirect_uri}{sep}code={code}&state={state}")
