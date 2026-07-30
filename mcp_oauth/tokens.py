"""Helpers to mint user-bound MCP API tokens and set JWT cookies."""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Iterable, Optional

from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from mcp_servers.shared import hash_token
from organizations.models import MCP_SCOPE_CHOICES, MCPApiToken


DEFAULT_MCP_SCOPES = list(MCP_SCOPE_CHOICES)
DEVICE_PLAINTEXT_CACHE_PREFIX = "mcp_oauth_device_plaintext:"
DEVICE_PLAINTEXT_TTL = 600  # 10 minutes


def normalize_scopes(scopes: Optional[Iterable[str]]) -> list[str]:
    if not scopes:
        return list(DEFAULT_MCP_SCOPES)
    out = []
    for s in scopes:
        s = (s or "").strip()
        if s and s in MCP_SCOPE_CHOICES and s not in out:
            out.append(s)
    return out or list(DEFAULT_MCP_SCOPES)


def issue_bound_mcp_token(
    *,
    user,
    scopes: Optional[Iterable[str]] = None,
    name: str = "MCP Sign-in",
    days: int = 90,
) -> tuple[MCPApiToken, str]:
    """
    Create a user-bound MCPApiToken. Returns (model, plaintext_once).
    """
    if not user.organization_id:
        raise ValueError("User has no organization")

    plaintext = f"tzm_{secrets.token_urlsafe(32)}"
    expires_at = timezone.now() + timedelta(days=days) if days else None
    token = MCPApiToken.objects.create(
        organization_id=user.organization_id,
        name=name,
        token_prefix=plaintext[:12],
        token_hash=hash_token(plaintext),
        scopes=normalize_scopes(scopes),
        bound_user=user,
        created_by=user,
        expires_at=expires_at,
    )
    return token, plaintext


def issue_jwt_access(user) -> tuple[str, str]:
    """Return (access, refresh) SimpleJWT strings."""
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    access["refresh_jti"] = refresh["jti"]
    return str(access), str(refresh)


def cache_device_plaintext(device_code: str, plaintext: str) -> None:
    cache.set(
        f"{DEVICE_PLAINTEXT_CACHE_PREFIX}{device_code}",
        plaintext,
        timeout=DEVICE_PLAINTEXT_TTL,
    )


def pop_device_plaintext(device_code: str) -> Optional[str]:
    key = f"{DEVICE_PLAINTEXT_CACHE_PREFIX}{device_code}"
    val = cache.get(key)
    if val:
        cache.delete(key)
    return val


def set_jwt_cookies(response, user, request=None):
    """Attach Teamzen access/refresh cookies to a Django HttpResponse."""
    from users.views import get_cookie_settings
    from users.utils import create_user_session

    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    access["refresh_jti"] = refresh["jti"]

    cookie_settings = get_cookie_settings()
    response.set_cookie(
        key="access_token",
        value=str(access),
        max_age=30 * 60,
        **cookie_settings,
    )
    response.set_cookie(
        key="refresh_token",
        value=str(refresh),
        max_age=7 * 24 * 60 * 60,
        **cookie_settings,
    )
    response.set_cookie(
        key="session_can_refresh",
        value="true",
        max_age=7 * 24 * 60 * 60,
        **get_cookie_settings(httponly=False),
    )

    if request is not None:
        try:
            create_user_session(user, refresh, request)
        except Exception:
            pass
    return response
