"""Platform adapter registry for bot_gateway."""

from __future__ import annotations

from bot_gateway.models import BotSession


def get_adapter(platform: str):
    """Return the thin API module for a platform (telegram | slack | whatsapp)."""
    if platform == BotSession.PLATFORM_SLACK:
        from bot_gateway.adapters import slack_api

        return slack_api
    if platform == BotSession.PLATFORM_WHATSAPP:
        from bot_gateway.adapters import whatsapp_api

        return whatsapp_api
    from bot_gateway.adapters import telegram_api

    return telegram_api
