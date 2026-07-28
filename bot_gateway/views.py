"""Telegram webhook endpoint."""

from __future__ import annotations

import html
import json
import logging
import re

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from bot_gateway.adapters import telegram_api
from bot_gateway.models import BotSession
from bot_gateway.services import BotReply, BotService

logger = logging.getLogger(__name__)
service = BotService()


def _secret_ok(request) -> bool:
    expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    if not expected:
        return bool(getattr(settings, "DEBUG", False))
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return provided == expected


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _send_reply(chat_id, reply: BotReply) -> None:
    result = telegram_api.send_message(
        chat_id,
        reply.text,
        parse_mode="HTML",
        reply_markup=reply.reply_markup,
    )
    if not result.get("ok"):
        telegram_api.send_message(
            chat_id,
            _strip_html(reply.text),
            parse_mode="",
            reply_markup=reply.reply_markup,
        )


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    """POST /api/bot/telegram/ — Telegram Update webhook."""

    def get(self, request):
        configured = bool(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
        return JsonResponse(
            {
                "service": "teamzen-telegram-bot",
                "configured": configured,
                "status": "ok",
            }
        )

    def post(self, request):
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
            return JsonResponse({"ok": False, "error": "bot_not_configured"}, status=503)

        if not _secret_ok(request):
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

        try:
            update = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        try:
            self._dispatch(update)
        except Exception:
            logger.exception("Telegram webhook dispatch failed")
        return HttpResponse("ok")

    def _dispatch(self, update: dict) -> None:
        if "callback_query" in update:
            self._handle_callback(update["callback_query"])
            return
        message = update.get("message") or update.get("edited_message")
        if message:
            self._handle_message(message)

    def _handle_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return

        # Live location for geofenced check-in / check-out
        location = message.get("location")
        if location and location.get("latitude") is not None:
            reply = service.handle_location(
                BotSession.PLATFORM_TELEGRAM,
                str(chat_id),
                float(location["latitude"]),
                float(location["longitude"]),
            )
            _send_reply(chat_id, reply)
            return

        text = message.get("text") or message.get("caption") or ""
        if not text:
            telegram_api.send_message(
                chat_id,
                "I currently support text and location messages. Try /help.",
            )
            return

        reply = service.handle_text(BotSession.PLATFORM_TELEGRAM, str(chat_id), text)
        _send_reply(chat_id, reply)

    def _handle_callback(self, callback: dict) -> None:
        callback_id = callback.get("id")
        data = callback.get("data") or ""
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        message_id = message.get("message_id")

        if chat_id is None:
            if callback_id:
                telegram_api.answer_callback_query(callback_id, "Missing chat")
            return

        reply, ok = service.handle_callback(
            BotSession.PLATFORM_TELEGRAM,
            str(chat_id),
            data,
        )

        if callback_id:
            telegram_api.answer_callback_query(
                callback_id,
                text=("Done" if ok else (reply.text or "")[:180]),
                show_alert=not ok and data.startswith("lv:"),
            )

        # Leave approvals: edit the original request message
        if data.startswith("lv:") and message_id:
            original = message.get("text") or ""
            updated = (
                f"{html.escape(original, quote=False)}\n\n"
                f"———\n{html.escape(reply.text, quote=False)}"
            )
            telegram_api.edit_message_text(chat_id, message_id, updated)
            return

        # Menu quick actions: send a fresh reply (keeps reply keyboard)
        _send_reply(chat_id, reply)
