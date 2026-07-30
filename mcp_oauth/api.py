"""JSON OAuth endpoints for MCP device + authorization-code grants."""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from mcp_oauth.tokens import (
    issue_bound_mcp_token,
    issue_jwt_access,
    normalize_scopes,
    pop_device_plaintext,
)
from organizations.models import MCPAuthCode, MCPDeviceCode


class DeviceCodeThrottle(AnonRateThrottle):
    rate = "30/hour"


class TokenThrottle(AnonRateThrottle):
    rate = "120/hour"


def _public_base(request) -> str:
    return request.build_absolute_uri("/").rstrip("/")


def _make_user_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


@method_decorator(csrf_exempt, name="dispatch")
class DeviceCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [DeviceCodeThrottle]
    authentication_classes = []

    def post(self, request):
        client_id = (request.data.get("client_id") or "cursor").strip()[:128]
        scope_raw = request.data.get("scope") or ""
        if isinstance(scope_raw, list):
            scopes = normalize_scopes(scope_raw)
        else:
            scopes = normalize_scopes(str(scope_raw).replace(",", " ").split())

        device_code = secrets.token_urlsafe(32)
        # Ensure unique user_code
        for _ in range(10):
            user_code = _make_user_code()
            if not MCPDeviceCode.objects.filter(user_code=user_code).exists():
                break
        else:
            return Response({"error": "server_error"}, status=500)

        expires_in = 600
        interval = 5
        row = MCPDeviceCode.objects.create(
            device_code=device_code,
            user_code=user_code,
            client_id=client_id,
            scopes=scopes,
            interval=interval,
            expires_at=timezone.now() + timedelta(seconds=expires_in),
        )

        base = _public_base(request)
        verify = f"{base}/mcp/connect/device/"
        return Response(
            {
                "device_code": row.device_code,
                "user_code": row.user_code,
                "verification_uri": verify,
                "verification_uri_complete": f"{verify}?user_code={row.user_code}",
                "expires_in": expires_in,
                "interval": interval,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class TokenView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TokenThrottle]
    authentication_classes = []

    def post(self, request):
        grant = (
            request.data.get("grant_type")
            or request.POST.get("grant_type")
            or ""
        ).strip()

        if grant == "urn:ietf:params:oauth:grant-type:device_code":
            return self._device_grant(request)
        if grant == "authorization_code":
            return self._auth_code_grant(request)
        return Response(
            {"error": "unsupported_grant_type"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _device_grant(self, request):
        device_code = (
            request.data.get("device_code") or request.POST.get("device_code") or ""
        ).strip()
        if not device_code:
            return Response({"error": "invalid_request"}, status=400)

        try:
            row = MCPDeviceCode.objects.select_related("user", "access_token").get(
                device_code=device_code
            )
        except MCPDeviceCode.DoesNotExist:
            return Response({"error": "invalid_grant"}, status=400)

        if row.expires_at <= timezone.now():
            if row.status == MCPDeviceCode.STATUS_PENDING:
                row.status = MCPDeviceCode.STATUS_EXPIRED
                row.save(update_fields=["status"])
            return Response({"error": "expired_token"}, status=400)

        if row.status == MCPDeviceCode.STATUS_PENDING:
            return Response(
                {"error": "authorization_pending"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if row.status == MCPDeviceCode.STATUS_DENIED:
            return Response({"error": "access_denied"}, status=400)
        if row.status != MCPDeviceCode.STATUS_APPROVED:
            return Response({"error": "invalid_grant"}, status=400)

        if row.token_issued:
            return Response({"error": "invalid_grant"}, status=400)

        plaintext = pop_device_plaintext(device_code)
        if not plaintext:
            # Re-issue only if we somehow lost cache but have bound token model
            # (cannot recover plaintext) — force re-auth
            return Response(
                {"error": "invalid_grant", "error_description": "token already consumed or lost"},
                status=400,
            )

        row.token_issued = True
        row.save(update_fields=["token_issued"])

        jwt_access, _ = issue_jwt_access(row.user)
        expires_in = 90 * 24 * 3600
        if row.access_token and row.access_token.expires_at:
            expires_in = max(
                0,
                int((row.access_token.expires_at - timezone.now()).total_seconds()),
            )

        return Response(
            {
                "access_token": plaintext,
                "token_type": "Bearer",
                "expires_in": expires_in,
                "scope": " ".join(row.scopes or []),
                "jwt_access": jwt_access,
            }
        )

    def _auth_code_grant(self, request):
        code = (request.data.get("code") or request.POST.get("code") or "").strip()
        redirect_uri = (
            request.data.get("redirect_uri") or request.POST.get("redirect_uri") or ""
        ).strip()
        if not code:
            return Response({"error": "invalid_request"}, status=400)

        try:
            row = MCPAuthCode.objects.select_related("user").get(code=code)
        except MCPAuthCode.DoesNotExist:
            return Response({"error": "invalid_grant"}, status=400)

        if row.used_at or row.expires_at <= timezone.now():
            return Response({"error": "invalid_grant"}, status=400)
        if redirect_uri and row.redirect_uri and redirect_uri != row.redirect_uri:
            return Response({"error": "invalid_grant"}, status=400)

        token, plaintext = issue_bound_mcp_token(
            user=row.user,
            scopes=row.scopes,
            name=f"MCP OAuth ({row.client_id})",
        )
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        jwt_access, _ = issue_jwt_access(row.user)

        return Response(
            {
                "access_token": plaintext,
                "token_type": "Bearer",
                "expires_in": 90 * 24 * 3600,
                "scope": " ".join(row.scopes or []),
                "jwt_access": jwt_access,
            }
        )
