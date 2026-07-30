"""Slack Web API thin client (Events API + slash commands + interactivity)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _token() -> str:
    token = (getattr(settings, "SLACK_BOT_TOKEN", "") or "").strip().strip('"').strip("'")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured")
    return token


def _client():
    from slack_sdk import WebClient

    return WebClient(token=_token())


def verify_request(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature. In DEBUG with no secret, allow."""
    secret = (getattr(settings, "SLACK_SIGNING_SECRET", "") or "").strip().strip('"').strip("'")
    if not secret:
        return bool(getattr(settings, "DEBUG", False))
    if not timestamp or not signature:
        logger.warning("Slack verify missing timestamp or signature header")
        return False
    try:
        from slack_sdk.signature import SignatureVerifier

        verifier = SignatureVerifier(signing_secret=secret)
        ok = verifier.is_valid(
            body=body if isinstance(body, bytes) else body.encode("utf-8"),
            timestamp=timestamp,
            signature=signature,
        )
        if not ok:
            logger.warning(
                "Slack signature mismatch (check SLACK_SIGNING_SECRET matches "
                "Basic Information → Signing Secret; no quotes/spaces in env)"
            )
        return ok
    except Exception:
        logger.exception("Slack signature verification error")
        return False


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "mrkdwn",
    reply_markup: Optional[dict] = None,
    **_kwargs: Any,
) -> dict:
    """
    Post a DM/channel message.
    reply_markup for Slack is Block Kit: {"blocks": [...]} or {"attachments": ...}.
    """
    try:
        client = _client()
        kwargs: dict[str, Any] = {
            "channel": str(chat_id),
            "text": (text or "")[:3900],
        }
        if reply_markup and isinstance(reply_markup, dict):
            if "blocks" in reply_markup:
                kwargs["blocks"] = reply_markup["blocks"]
            if "attachments" in reply_markup:
                kwargs["attachments"] = reply_markup["attachments"]
        result = client.chat_postMessage(**kwargs)
        return {"ok": bool(result.get("ok")), "data": result.data if hasattr(result, "data") else dict(result)}
    except Exception:
        logger.exception("Slack send_message failed chat=%s", chat_id)
        return {"ok": False, "description": "slack_error"}


def update_message(
    chat_id: str | int,
    ts: str,
    text: str,
    *,
    blocks: Optional[list] = None,
) -> dict:
    try:
        client = _client()
        kwargs: dict[str, Any] = {
            "channel": str(chat_id),
            "ts": ts,
            "text": (text or "")[:3900],
        }
        if blocks is not None:
            kwargs["blocks"] = blocks
        result = client.chat_update(**kwargs)
        return {"ok": bool(result.get("ok"))}
    except Exception:
        logger.exception("Slack update_message failed")
        return {"ok": False}


def leave_approval_keyboard(leave_id: int) -> dict:
    return {
        "blocks": [
            {
                "type": "actions",
                "block_id": f"lv_actions_{leave_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": f"lv:{leave_id}:a",
                        "value": f"lv:{leave_id}:a",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": f"lv:{leave_id}:r",
                        "value": f"lv:{leave_id}:r",
                    },
                ],
            }
        ]
    }


def main_menu_keyboard() -> Optional[dict]:
    """Slack has no persistent reply keyboard — use Block Kit shortcuts."""
    return quick_actions_inline()


def location_request_keyboard() -> Optional[dict]:
    """Slack cannot request GPS; return None (caller explains web/coords)."""
    return None


def remove_keyboard() -> Optional[dict]:
    return None


def quick_actions_inline() -> dict:
    return {
        "blocks": [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Leave Balance"},
                        "action_id": "menu:balance",
                        "value": "menu:balance",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Attendance"},
                        "action_id": "menu:attendance",
                        "value": "menu:attendance",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Payslip"},
                        "action_id": "menu:payslip",
                        "value": "menu:payslip",
                    },
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Apply Leave"},
                        "action_id": "menu:apply",
                        "value": "menu:apply",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Pending Leaves"},
                        "action_id": "menu:pending",
                        "value": "menu:pending",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Help"},
                        "action_id": "menu:help",
                        "value": "menu:help",
                    },
                ],
            },
        ]
    }


def slash_command_map(command: str, text: str) -> str:
    """Map slash command (+ optional text) to a BotService text/menu action string."""
    cmd = (command or "").strip().lower().lstrip("/")
    arg = (text or "").strip().lower()
    if cmd in ("leave", "leaves", "teamzen-leave"):
        return "apply leave" if not arg else f"apply leave {arg}"
    if cmd in ("checkin", "teamzen-checkin"):
        return "check-in"
    if cmd in ("checkout", "teamzen-checkout"):
        return "check-out"
    if cmd in ("payslip", "teamzen-payslip"):
        return "payslip"
    if cmd in ("balance", "teamzen-balance"):
        return "leave balance"
    if cmd in ("teamzen", "hr"):
        if arg in ("leave", "apply"):
            return "apply leave"
        if arg in ("checkin", "check-in"):
            return "check-in"
        if arg in ("checkout", "check-out"):
            return "check-out"
        if arg in ("payslip", "pay"):
            return "payslip"
        if arg in ("balance",):
            return "leave balance"
        if arg in ("help", ""):
            return "/help"
        return arg or "/help"
    return text or "/help"


def post_response_url(response_url: str, payload: dict[str, Any]) -> bool:
    """Post a delayed slash-command / interaction reply (within Slack's 30m window)."""
    if not response_url:
        return False
    try:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(response_url, json=payload)
            return 200 <= resp.status_code < 300
    except Exception:
        logger.exception("Slack response_url post failed")
        return False


def slash_payload(text: str, reply_markup: Optional[dict] = None) -> dict[str, Any]:
    """Build a valid slash-command response (omit null blocks)."""
    payload: dict[str, Any] = {
        "response_type": "ephemeral",
        "text": (text or "Done.")[:3900],
    }
    blocks = (reply_markup or {}).get("blocks") if isinstance(reply_markup, dict) else None
    if blocks:
        payload["blocks"] = blocks
    return payload


def is_configured() -> bool:
    return bool((getattr(settings, "SLACK_BOT_TOKEN", "") or "").strip().strip('"').strip("'"))
