"""Non-streaming LangGraph runner for bot channels."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from django.utils import timezone
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

# Dedicated pool so ASGI request threads never nest sync_to_async on themselves.
_AGENT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bot-agent")


def _get_history(user_id: int, context: str = "telegram"):
    from django.conf import settings
    from langchain_community.chat_message_histories import (
        ChatMessageHistory,
        RedisChatMessageHistory,
    )
    from ai_engine.views import _MEMORY_CHAT_HISTORIES

    session_id = f"chat_{user_id}_{context}"

    if getattr(settings, "USE_INMEMORY_CHANNELS", False):
        if session_id not in _MEMORY_CHAT_HISTORIES:
            _MEMORY_CHAT_HISTORIES[session_id] = ChatMessageHistory()
        return _MEMORY_CHAT_HISTORIES[session_id]

    try:
        history = RedisChatMessageHistory(
            session_id=session_id,
            url=settings.REDIS_URL,
            ttl=86400,
        )
        _ = history.messages
        return history
    except Exception as e:
        logger.warning("Redis bot chat history unavailable (%s); using memory fallback", e)
        if session_id not in _MEMORY_CHAT_HISTORIES:
            _MEMORY_CHAT_HISTORIES[session_id] = ChatMessageHistory()
        return _MEMORY_CHAT_HISTORIES[session_id]


def run_agent_for_user(
    user,
    query: str,
    *,
    context: str = "telegram",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> str:
    """
    Invoke the same LangGraph agent used by the web assistant and return
    the final assistant text (no SSE streaming).

    Runs in a worker thread to avoid Daphne/ASGI
    "CurrentThreadExecutor" nesting errors with sync_to_async.
    """
    history_manager = _get_history(user.id, context=context)
    existing = list(history_manager.messages)
    all_messages = existing + [HumanMessage(content=query)]

    org_id = user.organization_id if user.organization_id else 0
    user_role = getattr(user, "role", None) or "employee"
    initial_state = {
        "messages": all_messages,
        "user_id": user.id,
        "organization_id": org_id,
        "user_role": user_role,
        "latitude": latitude or 0,
        "longitude": longitude or 0,
        "payslip_context": None,
        "page_path": "",
        "app_context": "user",
    }

    def _run() -> str:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> str:
            from ai_engine.graph import build_graph

            compiled_app, _mcp = await build_graph(
                organization_id=org_id,
                user_id=user.id,
                user_role=user_role,
            )
            content_accumulated = ""
            async for event in compiled_app.astream_events(initial_state, version="v2"):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    from ai_engine.views import _normalize_llm_content

                    chunk = _normalize_llm_content(event["data"]["chunk"].content)
                    if chunk:
                        content_accumulated += chunk
            return content_accumulated

        try:
            return loop.run_until_complete(_collect())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    try:
        content = _AGENT_POOL.submit(_run).result(timeout=120)
    except Exception:
        logger.exception("Bot agent invocation failed for user=%s", user.id)
        raise

    now_iso = timezone.now().isoformat()
    history_manager.add_message(
        HumanMessage(content=query, additional_kwargs={"timestamp": now_iso})
    )
    history_manager.add_message(
        AIMessage(content=content or "", additional_kwargs={"timestamp": now_iso})
    )
    return content or "I couldn't generate a response. Please try again."


def clear_bot_history(user_id: int, context: str = "telegram") -> None:
    history = _get_history(user_id, context=context)
    history.clear()
