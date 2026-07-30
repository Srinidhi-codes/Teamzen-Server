"""Telegram + Slack webhook endpoints."""

from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import parse_qs

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from bot_gateway.adapters import slack_api, telegram_api
from bot_gateway.models import BotSession
from bot_gateway.services import BotReply, BotService

logger = logging.getLogger(__name__)
service = BotService()


def _telegram_secret_ok(request) -> bool:
    expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    if not expected:
        return bool(getattr(settings, "DEBUG", False))
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return provided == expected


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _send_telegram_reply(chat_id, reply: BotReply) -> None:
    text = reply.rendered_text() if hasattr(reply, "rendered_text") else reply.text
    result = telegram_api.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=reply.reply_markup,
    )
    if not result.get("ok"):
        telegram_api.send_message(
            chat_id,
            _strip_html(text),
            parse_mode="",
            reply_markup=reply.reply_markup,
        )


def _send_slack_reply(chat_id, reply: BotReply) -> None:
    text = reply.rendered_text() if hasattr(reply, "rendered_text") else reply.text
    slack_api.send_message(
        chat_id,
        text,
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

        if not _telegram_secret_ok(request):
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

        location = message.get("location")
        if location and location.get("latitude") is not None:
            reply = service.handle_location(
                BotSession.PLATFORM_TELEGRAM,
                str(chat_id),
                float(location["latitude"]),
                float(location["longitude"]),
            )
            _send_telegram_reply(chat_id, reply)
            return

        text = message.get("text") or message.get("caption") or ""
        if not text:
            telegram_api.send_message(
                chat_id,
                "I currently support text and location messages. Try /help.",
            )
            return

        reply = service.handle_text(BotSession.PLATFORM_TELEGRAM, str(chat_id), text)
        _send_telegram_reply(chat_id, reply)

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

        if data.startswith("lv:") and message_id:
            original = message.get("text") or ""
            updated = (
                f"{html.escape(original, quote=False)}\n\n"
                f"———\n{html.escape(reply.text, quote=False)}"
            )
            telegram_api.edit_message_text(chat_id, message_id, updated)
            return

        _send_telegram_reply(chat_id, reply)


@method_decorator(csrf_exempt, name="dispatch")
class SlackWebhookView(View):
    """
    POST /api/bot/slack/ — Slack Events API, slash commands, and interactivity.
    Configure this URL for Event Subscriptions, Slash Commands, and Interactivity.
    """

    def get(self, request):
        return JsonResponse(
            {
                "service": "teamzen-slack-bot",
                "configured": slack_api.is_configured(),
                "status": "ok",
                "scopes": [
                    "chat:write",
                    "commands",
                    "im:history",
                    "users:read",
                    "app_mentions:read",
                ],
            }
        )

    def post(self, request):
        if not slack_api.is_configured():
            return JsonResponse({"ok": False, "error": "bot_not_configured"}, status=503)

        body = request.body
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not slack_api.verify_request(body, timestamp, signature):
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

        content_type = (request.content_type or "").lower()

        # Slash commands + interactivity use form-urlencoded
        if "application/x-www-form-urlencoded" in content_type:
            return self._handle_form(request)

        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        # URL verification challenge
        if payload.get("type") == "url_verification":
            return JsonResponse({"challenge": payload.get("challenge", "")})

        if payload.get("type") == "event_callback":
            try:
                self._handle_event(payload.get("event") or {})
            except Exception:
                logger.exception("Slack event dispatch failed")
            return HttpResponse("ok")

        return HttpResponse("ok")

    def _handle_form(self, request):
        form = parse_qs(request.body.decode("utf-8"), keep_blank_values=True)

        # Interactivity payload
        if "payload" in form:
            try:
                payload = json.loads(form["payload"][0])
            except Exception:
                return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)
            try:
                self._handle_interaction(payload)
            except Exception:
                logger.exception("Slack interaction failed")
            return HttpResponse("")

        # Slash command
        command = (form.get("command") or [""])[0]
        text = (form.get("text") or [""])[0]
        user_id = (form.get("user_id") or [""])[0]
        if not user_id:
            return JsonResponse({"response_type": "ephemeral", "text": "Missing user"})

        mapped = slack_api.slash_command_map(command, text)
        reply = service.handle_text(BotSession.PLATFORM_SLACK, str(user_id), mapped)
        return JsonResponse(
            {
                "response_type": "ephemeral",
                "text": reply.rendered_text(),
                "blocks": (reply.reply_markup or {}).get("blocks"),
            }
        )

    def _handle_event(self, event: dict) -> None:
        etype = event.get("type")
        # Ignore bot messages / message edits noise
        if event.get("bot_id") or event.get("subtype") in (
            "bot_message",
            "message_changed",
            "message_deleted",
        ):
            return

        if etype in ("message", "app_mention"):
            # Only DMs for message; app_mention can be channels
            channel_type = event.get("channel_type") or ""
            if etype == "message" and channel_type and channel_type != "im":
                return
            user_id = event.get("user")
            text = event.get("text") or ""
            if not user_id:
                return
            # Strip bot mention for app_mention
            text = re.sub(r"<@[^>]+>\s*", "", text).strip()
            if not text:
                text = "/help"
            reply = service.handle_text(BotSession.PLATFORM_SLACK, str(user_id), text)
            channel = event.get("channel") or user_id
            _send_slack_reply(channel, reply)

    def _handle_interaction(self, payload: dict) -> None:
        user = payload.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            return

        actions = payload.get("actions") or []
        if not actions:
            return
        action = actions[0]
        data = action.get("value") or action.get("action_id") or ""

        reply, ok = service.handle_callback(
            BotSession.PLATFORM_SLACK,
            str(user_id),
            data,
        )

        channel = (payload.get("channel") or {}).get("id") or user_id
        message_ts = (payload.get("message") or {}).get("ts")

        if data.startswith("lv:") and message_ts:
            original = (payload.get("message") or {}).get("text") or ""
            updated = f"{original}\n\n———\n{reply.rendered_text()}"
            slack_api.update_message(channel, message_ts, updated, blocks=[])
            return

        _send_slack_reply(channel, reply)
