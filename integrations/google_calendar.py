"""Google Calendar OAuth + API helpers (Sequence 6 MVP)."""

from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from integrations.models import GoogleCalendarConnection

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events"
OAUTH_STATE_TTL = 600


def is_configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "")
    )


def _oauth_state_key(state: str) -> str:
    return f"gcal_oauth_state_{state}"


def build_authorize_url(user_id: int) -> str:
    if not is_configured():
        raise RuntimeError("Google Calendar OAuth is not configured")
    state = secrets.token_urlsafe(24)
    cache.set(_oauth_state_key(state), user_id, timeout=OAUTH_STATE_TTL)
    params = {
        "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, state: str) -> GoogleCalendarConnection:
    user_id = cache.get(_oauth_state_key(state))
    if not user_id:
        raise ValueError("Invalid or expired OAuth state")
    cache.delete(_oauth_state_key(state))

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or "access_token" not in data:
            raise RuntimeError(data.get("error_description") or data.get("error") or "token_exchange_failed")

    expires_in = int(data.get("expires_in") or 3600)
    refresh = data.get("refresh_token") or ""
    conn, _ = GoogleCalendarConnection.objects.get_or_create(user_id=user_id)
    if refresh:
        conn.refresh_token = refresh
    elif not conn.refresh_token:
        raise RuntimeError("No refresh_token returned; revoke access and reconnect")
    conn.access_token = data["access_token"]
    conn.token_expiry = timezone.now() + timedelta(seconds=expires_in - 60)
    conn.calendar_id = conn.calendar_id or "primary"
    conn.save()
    return conn


def disconnect_user(user_id: int) -> bool:
    deleted, _ = GoogleCalendarConnection.objects.filter(user_id=user_id).delete()
    return deleted > 0


def _refresh_access_token(conn: GoogleCalendarConnection) -> str:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "refresh_token": conn.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or "access_token" not in data:
            raise RuntimeError(data.get("error_description") or "refresh_failed")
    expires_in = int(data.get("expires_in") or 3600)
    conn.access_token = data["access_token"]
    conn.token_expiry = timezone.now() + timedelta(seconds=expires_in - 60)
    conn.save(update_fields=["access_token", "token_expiry", "updated_at"])
    return conn.access_token


def get_access_token(conn: GoogleCalendarConnection) -> str:
    if conn.access_token_valid:
        return conn.access_token
    return _refresh_access_token(conn)


def _auth_headers(conn: GoogleCalendarConnection) -> dict[str, str]:
    return {"Authorization": f"Bearer {get_access_token(conn)}"}


def get_connection(user_id: int) -> Optional[GoogleCalendarConnection]:
    return GoogleCalendarConnection.objects.filter(user_id=user_id).first()


def create_leave_event(leave) -> Optional[str]:
    """
    Create an all-day Google Calendar event for an approved leave.
    Returns google event id or None. Soft-fails on errors.
    """
    try:
        conn = get_connection(leave.user_id)
        if not conn:
            return None
        # All-day end is exclusive
        end_exclusive = leave.to_date + timedelta(days=1)
        body = {
            "summary": f"Leave: {leave.leave_type.name}",
            "description": (leave.reason or "")[:2000],
            "start": {"date": leave.from_date.isoformat()},
            "end": {"date": end_exclusive.isoformat()},
            "transparency": "opaque",
        }
        cal_id = conn.calendar_id or "primary"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events",
                headers=_auth_headers(conn),
                json=body,
            )
            data = resp.json()
            if resp.status_code >= 400:
                logger.warning("GCal create event failed: %s", data)
                return None
            return data.get("id")
    except Exception:
        logger.exception("GCal create_leave_event failed leave=%s", getattr(leave, "id", None))
        return None


def delete_leave_event(leave) -> bool:
    event_id = getattr(leave, "google_event_id", None) or ""
    if not event_id:
        return False
    try:
        conn = get_connection(leave.user_id)
        if not conn:
            return False
        cal_id = conn.calendar_id or "primary"
        with httpx.Client(timeout=30.0) as client:
            resp = client.delete(
                f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events/{event_id}",
                headers=_auth_headers(conn),
            )
            return resp.status_code in (200, 204, 404, 410)
    except Exception:
        logger.exception("GCal delete_leave_event failed leave=%s", getattr(leave, "id", None))
        return False


def list_busy_events(user_id: int, start: date, end: date) -> list[dict[str, Any]]:
    """
    List calendar events overlapping [start, end] inclusive (all-day friendly).
    Returns [{summary, start, end}, ...]. Empty if not connected.
    """
    conn = get_connection(user_id)
    if not conn:
        return []
    try:
        time_min = datetime.combine(start, datetime.min.time(), tzinfo=dt_timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        # end exclusive for query: day after end
        time_max = (
            datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        cal_id = conn.calendar_id or "primary"
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "50",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events",
                headers=_auth_headers(conn),
                params=params,
            )
            data = resp.json()
            if resp.status_code >= 400:
                logger.warning("GCal list events failed: %s", data)
                return []
        events = []
        for item in data.get("items") or []:
            start_obj = item.get("start") or {}
            end_obj = item.get("end") or {}
            events.append(
                {
                    "summary": item.get("summary") or "(busy)",
                    "start": start_obj.get("date") or start_obj.get("dateTime") or "",
                    "end": end_obj.get("date") or end_obj.get("dateTime") or "",
                }
            )
        return events
    except Exception:
        logger.exception("GCal list_busy_events failed user=%s", user_id)
        return []
