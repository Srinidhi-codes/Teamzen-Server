"""WhatsApp Cloud API thin client (Meta Graph API)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def _token() -> str:
    token = (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip().strip('"').strip("'")
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")
    return token


def _phone_number_id() -> str:
    pid = (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
    if not pid:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID is not configured")
    return pid


def _api_version() -> str:
    return (getattr(settings, "WHATSAPP_API_VERSION", "") or "v21.0").strip()


def is_configured() -> bool:
    return bool(
        (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip()
        and (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
    )


def normalize_chat_id(raw: str | int) -> str:
    """WhatsApp wa_id / from field → digits only (E.164 without +)."""
    return re.sub(r"\D", "", str(raw or ""))


def verify_signature(body: bytes, signature_header: str) -> bool:
    """
    Verify X-Hub-Signature-256 from Meta.
    In DEBUG with no app secret, allow (local tunnel testing).
    """
    secret = (getattr(settings, "WHATSAPP_APP_SECRET", "") or "").strip().strip('"').strip("'")
    if not secret:
        return bool(getattr(settings, "DEBUG", False))
    if not signature_header:
        logger.warning("WhatsApp verify missing X-Hub-Signature-256")
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    ok = hmac.compare_digest(expected, signature_header.strip())
    if not ok:
        logger.warning("WhatsApp signature mismatch")
    return ok


def _messages_url() -> str:
    return (
        f"https://graph.facebook.com/{_api_version()}/"
        f"{_phone_number_id()}/messages"
    )


def call(payload: dict[str, Any], *, timeout: float = 30.0) -> dict:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                _messages_url(),
                headers={
                    "Authorization": f"Bearer {_token()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                logger.warning(
                    "WhatsApp API failed status=%s body=%s",
                    resp.status_code,
                    data,
                )
                return {"ok": False, "description": data, "status": resp.status_code}
            return {"ok": True, "data": data}
    except Exception:
        logger.exception("WhatsApp API call failed")
        return {"ok": False, "description": "network_error"}


def _html_to_whatsapp(text: str) -> str:
    """Convert Telegram-style HTML to WhatsApp formatting (*bold*, _italic_)."""
    if not text:
        return ""
    out = text
    out = re.sub(r"<b>(.*?)</b>", r"*\1*", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<strong>(.*?)</strong>", r"*\1*", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<i>(.*?)</i>", r"_\1_", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<em>(.*?)</em>", r"_\1_", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<code>(.*?)</code>", r"```\1```", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<[^>]+>", "", out)
    return out.strip()


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "whatsapp",
    reply_markup: Optional[dict] = None,
    **_kwargs: Any,
) -> dict:
    """
    Send a text or interactive message.
    reply_markup may be:
      - {"interactive": {...}}  full interactive object (body filled from text if missing)
      - None → plain text
    """
    to = normalize_chat_id(chat_id)
    if not to:
        return {"ok": False, "description": "missing_chat_id"}

    body_text = _html_to_whatsapp(text or "")[:4096] or "Done."

    if reply_markup and isinstance(reply_markup, dict) and reply_markup.get("interactive"):
        interactive = dict(reply_markup["interactive"])
        # Interactive body max is 1024; send full text first when longer.
        if len(body_text) > 1024:
            text_result = call(
                {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "text",
                    "text": {"preview_url": False, "body": body_text},
                }
            )
            interactive["body"] = {"text": "Choose an action:"}
            interactive_result = call(
                {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "interactive",
                    "interactive": interactive,
                }
            )
            return {
                "ok": bool(text_result.get("ok") and interactive_result.get("ok")),
                "data": {
                    "text": text_result.get("data"),
                    "interactive": interactive_result.get("data"),
                },
            }

        if "body" not in interactive:
            interactive["body"] = {"text": body_text}
        elif isinstance(interactive.get("body"), dict) and not interactive["body"].get("text"):
            interactive["body"] = {**interactive["body"], "text": body_text}
        return call(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            }
        )

    return call(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body_text},
        }
    )


def leave_approval_keyboard(leave_id: int) -> dict:
    """Interactive reply buttons — Approve / Reject (max 3 buttons)."""
    return {
        "interactive": {
            "type": "button",
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": f"lv:{leave_id}:a", "title": "Approve"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": f"lv:{leave_id}:r", "title": "Reject"},
                    },
                ]
            },
        }
    }


def _menu_rows() -> list[dict]:
    return [
        {"id": "menu:checkin", "title": "Check-in", "description": "Geofenced check-in"},
        {"id": "menu:checkout", "title": "Check-out", "description": "Geofenced check-out"},
        {"id": "menu:balance", "title": "Leave Balance", "description": "View balances"},
        {"id": "menu:attendance", "title": "Attendance", "description": "Today's status"},
        {"id": "menu:apply", "title": "Apply Leave", "description": "Start leave apply"},
        {"id": "menu:pending", "title": "Pending Leaves", "description": "Your requests"},
        {"id": "menu:payslip", "title": "Payslip", "description": "Latest payslip"},
        {"id": "menu:help", "title": "Help", "description": "What I can do"},
    ]


def main_menu_keyboard() -> dict:
    """List message — WhatsApp has no persistent reply keyboard."""
    return {
        "interactive": {
            "type": "list",
            "action": {
                "button": "Menu",
                "sections": [
                    {
                        "title": "HR actions",
                        "rows": _menu_rows(),
                    }
                ],
            },
        }
    }


def quick_actions_inline() -> dict:
    return main_menu_keyboard()


def location_request_keyboard() -> Optional[dict]:
    """Cloud API cannot force a location pin; caller asks user to share location."""
    return None


def remove_keyboard() -> Optional[dict]:
    return None
