"""Telegram Bot API thin client (webhook-friendly, no long-polling)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _token() -> str:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    return token


def api_url(method: str) -> str:
    return f"{TELEGRAM_API}/bot{_token()}/{method}"


def call(method: str, payload: dict[str, Any], *, timeout: float = 30.0) -> dict:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(api_url(method), json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram API %s failed: %s", method, data)
            return data
    except Exception:
        logger.exception("Telegram API call failed: %s", method)
        return {"ok": False, "description": "network_error"}


def send_message(
    chat_id: str | int,
    text: str,
    *,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    disable_web_page_preview: bool = True,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return call("sendMessage", payload)


def answer_callback_query(
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> dict:
    return call(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_query_id,
            "text": text[:200],
            "show_alert": show_alert,
        },
    )


def edit_message_text(
    chat_id: str | int,
    message_id: int,
    text: str,
    *,
    parse_mode: str = "HTML",
) -> dict:
    return call(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4000],
            "parse_mode": parse_mode,
            "reply_markup": {"inline_keyboard": []},
        },
    )


def leave_approval_keyboard(leave_id: int) -> dict:
    """Inline keyboard — one-tap approve/reject."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"lv:{leave_id}:a"},
                {"text": "❌ Reject", "callback_data": f"lv:{leave_id}:r"},
            ]
        ]
    }


def main_menu_keyboard() -> dict:
    """Persistent reply keyboard under the chat input."""
    return {
        "keyboard": [
            [{"text": "✅ Check-in"}, {"text": "🏁 Check-out"}],
            [{"text": "🏖 Leave Balance"}, {"text": "📍 Attendance"}],
            [{"text": "📝 Apply Leave"}, {"text": "📋 My Pending Leaves"}],
            [{"text": "💰 Payslip"}, {"text": "❓ Help"}],
            [{"text": "🚪 Logout"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def location_request_keyboard() -> dict:
    """One-time keyboard that asks Telegram for live GPS."""
    return {
        "keyboard": [
            [{"text": "📍 Share my location", "request_location": True}],
            [{"text": "❌ Cancel"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def remove_keyboard() -> dict:
    return {"remove_keyboard": True}


def quick_actions_inline() -> dict:
    """Inline shortcuts under a welcome/help message."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Check-in", "callback_data": "menu:checkin"},
                {"text": "🏁 Check-out", "callback_data": "menu:checkout"},
            ],
            [
                {"text": "🏖 Balance", "callback_data": "menu:balance"},
                {"text": "📍 Attendance", "callback_data": "menu:attendance"},
            ],
            [
                {"text": "📝 Apply Leave", "callback_data": "menu:apply"},
                {"text": "💰 Payslip", "callback_data": "menu:payslip"},
            ],
            [
                {"text": "📋 Pending Leaves", "callback_data": "menu:pending"},
            ],
        ]
    }


def set_webhook(url: str, secret_token: str = "") -> dict:
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return call("setWebhook", payload)


def delete_webhook() -> dict:
    return call("deleteWebhook", {"drop_pending_updates": True})
