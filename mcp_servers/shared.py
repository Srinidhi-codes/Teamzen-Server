"""
Django bootstrap + MCP auth / audit helpers for Teamzen MCP servers.

Identity model:
  - Internal (LangGraph): X-MCP-Internal-Secret + X-MCP-User-Id + X-MCP-Organization-Id
  - API token: Bearer tzm_… optionally bound_user (required for user-scoped tools)
  - JWT: Bearer <SimpleJWT access> → that user
  - Tool args user_id / organization_id / approver_id are overwritten from auth context
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

_bootstrapped = False
logger = logging.getLogger(__name__)

_auth_ctx: ContextVar[Optional["MCPAuthContext"]] = ContextVar("mcp_auth_ctx", default=None)
_server_name_ctx: ContextVar[str] = ContextVar("mcp_server_name", default="teamzen-hr")


@dataclass
class MCPAuthContext:
    is_internal: bool = False
    token_id: Optional[int] = None
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    scopes: list[str] = field(default_factory=list)
    auth_ok: bool = False
    error: Optional[str] = None

    @property
    def identity_bound(self) -> bool:
        return self.user_id is not None


def bootstrap_django():
    global _bootstrapped
    if _bootstrapped:
        return
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    django.setup()
    _bootstrapped = True


def get_auth() -> MCPAuthContext:
    return _auth_ctx.get() or MCPAuthContext()


def set_server_name(name: str) -> None:
    _server_name_ctx.set(name)


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _auth_required() -> bool:
    return os.environ.get("MCP_AUTH_REQUIRED", "false").lower() == "true"


def _header(headers: dict[str, str], *names: str) -> str:
    for n in names:
        v = headers.get(n) or headers.get(n.lower()) or headers.get(n.title())
        if v:
            return str(v).strip()
    return ""


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _load_user(user_id: int):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(id=user_id, is_active=True).select_related("organization").first()


def _try_jwt_user(plaintext: str) -> Optional[MCPAuthContext]:
    """Resolve SimpleJWT access token to a user identity."""
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError
    except Exception:
        return None

    try:
        access = AccessToken(plaintext)
        uid = access.get("user_id")
        if not uid:
            return None
        user = _load_user(int(uid))
        if not user:
            return MCPAuthContext(auth_ok=False, error="JWT user not found or inactive")
        return MCPAuthContext(
            is_internal=False,
            user_id=user.id,
            organization_id=getattr(user, "organization_id", None),
            user_role=getattr(user, "role", None),
            scopes=["*"],
            auth_ok=True,
        )
    except Exception:
        return None


def resolve_auth_from_headers(headers: dict[str, str]) -> MCPAuthContext:
    """
    Resolve auth + identity from HTTP headers.
    """
    from django.utils import timezone
    from organizations.models import MCPApiToken

    internal_secret = os.environ.get("MCP_INTERNAL_SECRET", "").strip()
    provided_internal = _header(headers, "x-mcp-internal-secret", "X-MCP-Internal-Secret")

    if internal_secret and provided_internal and provided_internal == internal_secret:
        uid = _parse_int(_header(headers, "x-mcp-user-id", "X-MCP-User-Id"))
        oid = _parse_int(_header(headers, "x-mcp-organization-id", "X-MCP-Organization-Id"))
        role = _header(headers, "x-mcp-user-role", "X-MCP-User-Role") or None
        if uid:
            user = _load_user(uid)
            if not user:
                return MCPAuthContext(auth_ok=False, error="X-MCP-User-Id not found or inactive")
            if oid and user.organization_id and int(oid) != int(user.organization_id):
                return MCPAuthContext(
                    auth_ok=False,
                    error="X-MCP-Organization-Id does not match user organization",
                )
            return MCPAuthContext(
                is_internal=True,
                auth_ok=True,
                scopes=["*"],
                user_id=user.id,
                organization_id=user.organization_id or oid,
                user_role=role or getattr(user, "role", None),
            )
        # Internal secret without user: allowed only when identity not enforced for ops
        return MCPAuthContext(is_internal=True, auth_ok=True, scopes=["*"])

    auth_header = _header(headers, "authorization", "Authorization")
    if auth_header.lower().startswith("bearer "):
        plaintext = auth_header[7:].strip()
        if plaintext:
            # 1) Org API token
            digest = hash_token(plaintext)
            token = (
                MCPApiToken.objects.select_related("organization", "bound_user")
                .filter(token_hash=digest, is_active=True)
                .first()
            )
            if token is not None:
                if token.expires_at and token.expires_at <= timezone.now():
                    if _auth_required():
                        return MCPAuthContext(auth_ok=False, error="MCP API token expired")
                else:
                    MCPApiToken.objects.filter(pk=token.pk).update(
                        last_used_at=timezone.now()
                    )
                    uid = token.bound_user_id
                    role = None
                    if token.bound_user_id:
                        role = getattr(token.bound_user, "role", None)
                    # Optional acting user override only if token has no bound_user
                    if uid is None:
                        acting = _parse_int(
                            _header(headers, "x-mcp-acting-user-id", "X-MCP-Acting-User-Id")
                        )
                        if acting:
                            acting_user = _load_user(acting)
                            if not acting_user:
                                return MCPAuthContext(
                                    auth_ok=False, error="Acting user not found"
                                )
                            if acting_user.organization_id != token.organization_id:
                                return MCPAuthContext(
                                    auth_ok=False,
                                    error="Acting user not in token organization",
                                )
                            uid = acting_user.id
                            role = getattr(acting_user, "role", None)
                    return MCPAuthContext(
                        is_internal=False,
                        token_id=token.id,
                        organization_id=token.organization_id,
                        user_id=uid,
                        user_role=role,
                        scopes=list(token.scopes or []),
                        auth_ok=True,
                    )

            # 2) SimpleJWT access token
            jwt_ctx = _try_jwt_user(plaintext)
            if jwt_ctx is not None:
                return jwt_ctx

            if _auth_required():
                return MCPAuthContext(auth_ok=False, error="Invalid MCP API token or JWT")

    if not _auth_required():
        # Dev open mode — no trusted identity
        return MCPAuthContext(is_internal=True, auth_ok=True, scopes=["*"])

    return MCPAuthContext(
        auth_ok=False,
        error=(
            "Missing credentials. Provide Authorization: Bearer <token|JWT> "
            "or X-MCP-Internal-Secret with X-MCP-User-Id."
        ),
    )


def _args_digest(payload: dict) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _write_audit(
    *,
    tool_name: str,
    payload: dict,
    success: bool,
    error_message: str,
    latency_ms: int,
    actor_user_id: Optional[int],
) -> None:
    try:
        from organizations.models import MCPApiToken, MCPAuditLog

        ctx = get_auth()
        token = None
        org_id = ctx.organization_id
        if ctx.token_id:
            token = MCPApiToken.objects.filter(pk=ctx.token_id).first()
            if token and org_id is None:
                org_id = token.organization_id

        MCPAuditLog.objects.create(
            organization_id=org_id,
            token=token,
            server_name=_server_name_ctx.get(),
            tool_name=tool_name,
            actor_user_id=actor_user_id,
            args_digest=_args_digest(payload),
            success=success,
            error_message=(error_message or "")[:2000],
            latency_ms=latency_ms,
            is_internal=ctx.is_internal,
        )
    except Exception:
        logger.exception("Failed to write MCP audit log for %s", tool_name)


def _bind_identity(payload: dict, ctx: MCPAuthContext) -> tuple[dict, Optional[str]]:
    """
    Overwrite identity fields from trusted auth context.
    Returns (payload, error_message_or_None).
    """
    out = dict(payload)

    if ctx.organization_id is not None and "organization_id" in out:
        out["organization_id"] = ctx.organization_id

    if ctx.user_id is not None:
        if "user_id" in out:
            out["user_id"] = ctx.user_id
        if "approver_id" in out:
            out["approver_id"] = ctx.user_id
        return out, None

    # No bound user — always block user-scoped tools (even in open/dev mode).
    # Previously open mode allowed LLM-supplied user_id, which leaked payslips.
    needs_user = "user_id" in out or "approver_id" in out
    if needs_user:
        return out, (
            "Authenticated user required. Use a user-bound MCP token (--user), "
            "JWT Bearer, X-MCP-Acting-User-Id, or X-MCP-User-Id with internal secret."
        )
    return out, None


def invoke_tool(
    langchain_tool,
    payload: dict,
    *,
    required_scope: str,
    tool_name: Optional[str] = None,
) -> Any:
    """
    Enforce auth + scope + identity binding, invoke tool, write audit.
    """
    name = tool_name or getattr(langchain_tool, "name", "unknown")
    ctx = get_auth()
    started = time.perf_counter()

    if not ctx.auth_ok:
        msg = ctx.error or "Unauthorized"
        _write_audit(
            tool_name=name,
            payload=payload,
            success=False,
            error_message=msg,
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=None,
        )
        return f"Error: {msg}"

    if not ctx.is_internal and "*" not in ctx.scopes and required_scope not in ctx.scopes:
        msg = f"Missing scope '{required_scope}'"
        _write_audit(
            tool_name=name,
            payload=payload,
            success=False,
            error_message=msg,
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=ctx.user_id,
        )
        return f"Error: {msg}"

    bound, bind_err = _bind_identity(payload, ctx)
    if bind_err:
        _write_audit(
            tool_name=name,
            payload=bound,
            success=False,
            error_message=bind_err,
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=ctx.user_id,
        )
        return f"Error: {bind_err}"

    # Org mismatch after binding should not happen; keep as safety net
    org_in_payload = bound.get("organization_id")
    if (
        ctx.organization_id
        and org_in_payload is not None
        and int(org_in_payload) != int(ctx.organization_id)
    ):
        msg = "organization_id does not match authenticated organization"
        _write_audit(
            tool_name=name,
            payload=bound,
            success=False,
            error_message=msg,
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=ctx.user_id,
        )
        return f"Error: {msg}"

    actor = bound.get("user_id") or bound.get("approver_id") or ctx.user_id

    # Bind AI actor ContextVar so tools ignore spoofed user_id even if args slip through
    actor_token = None
    try:
        from ai_engine.actor_context import set_actor, reset_actor

        if ctx.user_id is not None:
            actor_token = set_actor(
                ctx.user_id,
                organization_id=ctx.organization_id,
                role=ctx.user_role,
            )
    except Exception:
        logger.exception("Failed to set AI actor context for %s", name)

    try:
        result = langchain_tool.invoke(bound)
        _write_audit(
            tool_name=name,
            payload=bound,
            success=True,
            error_message="",
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=actor if isinstance(actor, int) else None,
        )
        return result
    except Exception as exc:
        _write_audit(
            tool_name=name,
            payload=bound,
            success=False,
            error_message=str(exc),
            latency_ms=int((time.perf_counter() - started) * 1000),
            actor_user_id=actor if isinstance(actor, int) else None,
        )
        raise
    finally:
        if actor_token is not None:
            try:
                from ai_engine.actor_context import reset_actor

                reset_actor(actor_token)
            except Exception:
                pass


def create_mcp(name: str, instructions: str, port: int):
    from mcp.server.fastmcp import FastMCP

    set_server_name(name)
    return FastMCP(
        name=name,
        instructions=instructions,
        host="0.0.0.0",
        port=port,
        streamable_http_path="/mcp",
    )


def _header_map(scope_headers: list) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in scope_headers:
        try:
            k = key.decode("latin-1") if isinstance(key, (bytes, bytearray)) else str(key)
            v = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
            out[k.lower()] = v
            out[k] = v
        except Exception:
            continue
    return out


class MCPAuthMiddleware:
    """Pure ASGI middleware that sets MCPAuthContext from request headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = _header_map(scope.get("headers") or [])
            try:
                ctx = resolve_auth_from_headers(headers)
            except Exception as exc:
                logger.exception("MCP auth resolve failed")
                ctx = MCPAuthContext(auth_ok=False, error=str(exc))
            token = _auth_ctx.set(ctx)
            try:
                await self.app(scope, receive, send)
            finally:
                _auth_ctx.reset(token)
        else:
            await self.app(scope, receive, send)


def run_mcp(mcp, *, server_name: Optional[str] = None) -> None:
    import uvicorn

    if server_name:
        set_server_name(server_name)

    app = mcp.streamable_http_app()
    app = MCPAuthMiddleware(app)

    host = getattr(mcp.settings, "host", None) or "0.0.0.0"
    port = getattr(mcp.settings, "port", None) or int(os.environ.get("MCP_SERVER_PORT", 8001))
    print(f"[MCP] Starting {server_name or mcp.name} on http://{host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port)
