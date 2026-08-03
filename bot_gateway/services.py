"""Bot auth, session management, message routing, and leave approval actions."""

from __future__ import annotations

import html
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from bot_gateway.adapters.registry import get_adapter
from bot_gateway.agent import clear_bot_history, run_agent_for_user
from bot_gateway.formatters import format_for_bot, format_for_platform
from bot_gateway.models import BotSession
from users.models import CustomUser

logger = logging.getLogger(__name__)


@dataclass
class BotReply:
    text: str
    reply_markup: Optional[dict] = None
    platform: str = BotSession.PLATFORM_TELEGRAM

    def rendered_text(self) -> str:
        return format_for_platform(self.text, self.platform)


WELCOME = (
    "Welcome to <b>Teamzen HR Assistant</b>\n\n"
    "Please enter your registered work <b>email</b> or <b>phone number</b> to continue."
)

WELCOME_SLACK = (
    "Welcome to <b>Teamzen HR Assistant</b>\n\n"
    "Sign in with slash commands (DMs may not be delivered until Events are enabled):\n"
    "1. <code>/teamzen your@work-email.com</code>\n"
    "2. Check your email for a 6-digit OTP\n"
    "3. <code>/teamzen 123456</code> (paste the OTP)\n\n"
    "Then try <code>/balance</code> or <code>/leaves</code>."
)

HELP_TEXT = (
    "Tap a button below, or type freely.\n\n"
    "I can help with leave, attendance, payslips, and policies.\n\n"
    "Telegram: /start · /help · /logout · /clear\n"
    "WhatsApp: send hi · Menu button · share location for check-in\n"
    "Slack: /teamzen start · /teamzen you@email.com · /teamzen 123456 · "
    "/leaves · /balance · /payslip"
)

SIGN_IN_HINT_TELEGRAM = "Please sign in first — send /start and verify with OTP."
SIGN_IN_HINT_WHATSAPP = (
    "Please sign in first — send <b>hi</b> or your work email, "
    "then enter the 6-digit OTP from email."
)
SIGN_IN_HINT_SLACK = (
    "Please sign in first:\n"
    "1. <code>/teamzen start</code>\n"
    "2. <code>/teamzen your@work-email.com</code>\n"
    "3. <code>/teamzen 123456</code> (OTP from email)"
)


def _welcome(platform: str) -> str:
    if platform == BotSession.PLATFORM_SLACK:
        return WELCOME_SLACK
    return WELCOME


def _sign_in_hint(platform: str) -> str:
    if platform == BotSession.PLATFORM_SLACK:
        return SIGN_IN_HINT_SLACK
    if platform == BotSession.PLATFORM_WHATSAPP:
        return SIGN_IN_HINT_WHATSAPP
    return SIGN_IN_HINT_TELEGRAM

# Reply-keyboard labels → action keys
MENU_LABELS = {
    "✅ check-in": "checkin",
    "check-in": "checkin",
    "checkin": "checkin",
    "🏁 check-out": "checkout",
    "check-out": "checkout",
    "checkout": "checkout",
    "🏖 leave balance": "balance",
    "leave balance": "balance",
    "📍 attendance": "attendance",
    "attendance": "attendance",
    "📝 apply leave": "apply",
    "apply leave": "apply",
    "📋 my pending leaves": "pending",
    "my pending leaves": "pending",
    "💰 payslip": "payslip",
    "payslip": "payslip",
    "❓ help": "help",
    "help": "help",
    "🚪 logout": "logout",
    "logout": "logout",
    "❌ cancel": "cancel_location",
    "cancel": "cancel_location",
}


def _attendance_action_key(platform: str, chat_id: str) -> str:
    return f"bot_attendance_action_{platform}_{chat_id}"


def _session_ttl() -> timedelta:
    hours = int(getattr(settings, "BOT_SESSION_TTL_HOURS", 8) or 8)
    return timedelta(hours=hours)


def _otp_cache_key(platform: str, chat_id: str) -> str:
    return f"bot_otp_{platform}_{chat_id}"


def _looks_like_email(text: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text))


def _normalize_phone(text: str) -> str:
    return re.sub(r"[^\d+]", "", text)


def _escape(text: str) -> str:
    return html.escape(text or "", quote=False)


def _menu_markup(platform: str = BotSession.PLATFORM_TELEGRAM):
    return get_adapter(platform).main_menu_keyboard()


def _inline_menu(platform: str = BotSession.PLATFORM_TELEGRAM):
    return get_adapter(platform).quick_actions_inline()


def _reply(platform: str, text: str, reply_markup: Optional[dict] = None) -> BotReply:
    return BotReply(text=text, reply_markup=reply_markup, platform=platform)


class BotService:
    """Platform-agnostic bot orchestration (Telegram + Slack + WhatsApp)."""

    def get_or_create_session(self, platform: str, chat_id: str) -> BotSession:
        session, _ = BotSession.objects.get_or_create(
            platform=platform,
            chat_id=str(chat_id),
            defaults={"auth_state": BotSession.AUTH_AWAITING_IDENTITY},
        )
        if session.is_verified and not session.is_active:
            session.mark_expired()
        return session

    def get_verified_session_for_user(
        self, user_id: int, platform: str = BotSession.PLATFORM_TELEGRAM
    ) -> Optional[BotSession]:
        session = (
            BotSession.objects.filter(
                user_id=user_id,
                platform=platform,
                is_verified=True,
            )
            .order_by("-updated_at")
            .first()
        )
        if session and session.is_active:
            return session
        return None

    def handle_text(self, platform: str, chat_id: str, text: str) -> BotReply:
        text = (text or "").strip()
        if not text:
            return _reply(platform, "Please send a text message.")

        session = self.get_or_create_session(platform, chat_id)
        lower = text.lower().strip()

        if lower in ("/start", "start") or (
            not session.is_active and lower in ("hi", "hello")
        ):
            return self._restart_auth(session)

        # Map reply-keyboard taps (and synonyms) before auth checks where needed
        menu_key = MENU_LABELS.get(lower)
        if menu_key == "logout" or lower in ("/logout",):
            return self._logout(session)
        if menu_key == "help" or lower in ("/help", "help"):
            if session.is_active:
                return _reply(platform, HELP_TEXT, reply_markup=_inline_menu(platform))
            return _reply(platform, _welcome(platform))

        if menu_key and not session.is_active:
            return _reply(platform, _sign_in_hint(platform))

        if lower in ("/clear", "clear"):
            if session.is_active:
                clear_bot_history(session.user_id)
                return _reply(
                    platform,
                    "Conversation memory cleared. Ask me anything.",
                    reply_markup=_menu_markup(platform),
                )
            return _reply(platform, _welcome(platform))

        if not session.is_active:
            msg = self._handle_auth_flow(session, text)
            session.refresh_from_db()
            if session.is_active:
                return _reply(platform, msg, reply_markup=_menu_markup(platform))
            return _reply(platform, msg)

        if menu_key:
            return self._handle_menu_action(session, menu_key)

        # Free-text check-in / check-out → location flow (geofence required)
        if re.search(r"\bcheck[\s-]?out\b", lower):
            return self._request_location(session, "check-out")
        if re.search(r"\bcheck[\s-]?in\b", lower):
            return self._request_location(session, "check-in")

        # Slack: accept "lat,lng" when a check-in/out is pending
        if platform == BotSession.PLATFORM_SLACK:
            coords = self._parse_coords(text)
            if coords:
                lat, lng = coords
                return self.handle_location(platform, chat_id, lat, lng)

        approval_reply = self._try_text_approval(session, text)
        if approval_reply is not None:
            return _reply(platform, approval_reply, reply_markup=_menu_markup(platform))

        return self._handle_agent_message(session, text)

    @staticmethod
    def _parse_coords(text: str) -> Optional[tuple[float, float]]:
        m = re.match(
            r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$",
            text or "",
        )
        if not m:
            return None
        return float(m.group(1)), float(m.group(2))

    def handle_location(
        self,
        platform: str,
        chat_id: str,
        latitude: float,
        longitude: float,
    ) -> BotReply:
        """Process a shared location for pending check-in/out."""
        session = self.get_or_create_session(platform, chat_id)
        if not session.is_active:
            return _reply(platform, _sign_in_hint(platform))

        action = cache.get(_attendance_action_key(platform, chat_id))
        if not action:
            return _reply(
                platform,
                "Got your location. Tap <b>Check-in</b> or <b>Check-out</b> first, "
                "then share location when asked.",
                reply_markup=_menu_markup(platform),
            )

        cache.delete(_attendance_action_key(platform, chat_id))
        return _reply(
            platform,
            self._perform_attendance(session.user, action, latitude, longitude),
            reply_markup=_menu_markup(platform),
        )

    def handle_callback(
        self,
        platform: str,
        chat_id: str,
        callback_data: str,
    ) -> tuple[BotReply, bool]:
        """
        Handle inline button taps.
        Returns (reply, ok). For leave approvals, ok indicates success.
        """
        data = callback_data or ""
        if data.startswith("menu:"):
            session = self.get_or_create_session(platform, chat_id)
            if not session.is_active:
                return _reply(platform, _sign_in_hint(platform)), False
            action = data.split(":", 1)[1]
            return self._handle_menu_action(session, action), True

        if data.startswith("lv:"):
            text, ok = self.handle_leave_callback(platform, chat_id, data)
            return _reply(platform, text, reply_markup=_menu_markup(platform)), ok

        return _reply(platform, "Unknown action."), False

    def handle_leave_callback(
        self,
        platform: str,
        chat_id: str,
        callback_data: str,
        *,
        from_user_name: str = "",
    ) -> tuple[str, bool]:
        session = self.get_or_create_session(platform, chat_id)
        if not session.is_active:
            return (_sign_in_hint(platform), False)

        parts = (callback_data or "").split(":")
        if len(parts) != 3 or parts[0] != "lv":
            return ("Unknown action.", False)

        try:
            leave_id = int(parts[1])
        except ValueError:
            return ("Invalid leave request.", False)

        action = parts[2]
        if action == "a":
            return self._approve_leave(session.user, leave_id)
        if action == "r":
            return self._reject_leave(session.user, leave_id)
        return ("Unknown action.", False)

    # ---------------------------------------------------------------- menu
    def _handle_menu_action(self, session: BotSession, action: str) -> BotReply:
        platform = session.platform
        action = (action or "").lower().strip()
        if action in ("checkin", "check-in"):
            return self._request_location(session, "check-in")
        if action in ("checkout", "check-out"):
            return self._request_location(session, "check-out")
        if action == "cancel_location":
            cache.delete(_attendance_action_key(session.platform, session.chat_id))
            return _reply(platform, "Cancelled.", reply_markup=_menu_markup(platform))
        if action == "balance":
            return _reply(
                platform,
                self._quick_leave_balance(session.user),
                reply_markup=_menu_markup(platform),
            )
        if action == "attendance":
            return _reply(
                platform,
                self._quick_attendance(session.user),
                reply_markup=_menu_markup(platform),
            )
        if action == "pending":
            return _reply(
                platform,
                self._quick_pending_leaves(session.user),
                reply_markup=_menu_markup(platform),
            )
        if action == "payslip":
            return _reply(
                platform,
                self._quick_payslip(session.user),
                reply_markup=_menu_markup(platform),
            )
        if action == "apply":
            return self._handle_agent_message(
                session,
                "I want to apply for leave. Ask me for leave type, dates, and reason.",
            )
        if action == "help":
            return _reply(platform, HELP_TEXT, reply_markup=_inline_menu(platform))
        if action == "logout":
            return self._logout(session)
        return _reply(platform, "Unknown menu action.", reply_markup=_menu_markup(platform))

    def _request_location(self, session: BotSession, action: str) -> BotReply:
        platform = session.platform
        adapter = get_adapter(platform)

        if not session.user.office_location_id:
            return _reply(
                platform,
                "You don't have an assigned office location. Please contact HR.",
                reply_markup=_menu_markup(platform),
            )

        cache.set(
            _attendance_action_key(session.platform, session.chat_id),
            action,
            timeout=300,
        )
        label = "check in" if action == "check-in" else "check out"
        if platform == BotSession.PLATFORM_SLACK:
            return _reply(
                platform,
                f"To <b>{label}</b>, I need your live location for geofence verification.\n"
                f"Reply with coordinates as <code>latitude,longitude</code> "
                f"(e.g. <code>12.9716,77.5946</code>), or use the Teamzen web/mobile app.\n"
                f"Request expires in 5 minutes.",
                reply_markup=_menu_markup(platform),
            )
        if platform == BotSession.PLATFORM_WHATSAPP:
            return _reply(
                platform,
                f"To <b>{label}</b>, I need your live location for geofence verification.\n"
                f"Tap the <b>📎</b> attachment → <b>Location</b> → "
                f"<b>Send your current location</b>.\n"
                f"Request expires in 5 minutes.",
                reply_markup=_menu_markup(platform),
            )
        return _reply(
            platform,
            f"To <b>{label}</b>, I need your live location for geofence verification.\n"
            f"Tap <b>Share my location</b> below (expires in 5 minutes).",
            reply_markup=adapter.location_request_keyboard(),
        )

    def _perform_attendance(
        self, user: CustomUser, action: str, latitude: float, longitude: float
    ) -> str:
        from attendance.services import check_in_user, check_out_user, org_requires_face

        if org_requires_face(user):
            return (
                "🔒 <b>Face attendance required</b>\n"
                "Your organization requires face verification. "
                "Please punch from the Teamzen web or mobile app."
            )

        try:
            now_time = timezone.localtime().time().strftime("%H:%M:%S")
            if action == "check-in":
                attendance, distance = check_in_user(
                    user, user.office_location.id, latitude, longitude, now_time
                )
                return (
                    f"✅ <b>Check-in</b> recorded\n"
                    f"Status: {_escape(str(attendance.status))}\n"
                    f"Time: {now_time}\n"
                    f"Office: {_escape(user.office_location.name)}\n"
                    f"Distance: {int(distance)}m"
                )
            attendance, distance = check_out_user(user, latitude, longitude, now_time)
            return (
                f"🏁 <b>Check-out</b> recorded\n"
                f"Status: {_escape(str(attendance.status))}\n"
                f"Time: {now_time}\n"
                f"Office: {_escape(user.office_location.name)}\n"
                f"Hours: {attendance.worked_hours}\n"
                f"Distance: {int(distance)}m"
            )
        except Exception as e:
            logger.exception("Bot attendance failed user=%s action=%s", user.id, action)
            return f"⚠️ Could not complete {action}: {_escape(str(e))}"

    def _quick_payslip(self, user: CustomUser) -> str:
        from payroll.models import Payslip

        payslip = (
            Payslip.objects.filter(user_id=user.id, status__in=["published", "paid"])
            .select_related("payroll_run")
            .prefetch_related("components")
            .order_by("-payroll_run__year", "-payroll_run__month", "-created_at")
            .first()
        )
        if not payslip:
            payslip = (
                Payslip.objects.filter(user_id=user.id)
                .select_related("payroll_run")
                .prefetch_related("components")
                .order_by("-payroll_run__year", "-payroll_run__month", "-created_at")
                .first()
            )
        if not payslip:
            return "No payslip found yet. Contact HR if you expected one."

        run = payslip.payroll_run
        lines = [
            f"<b>Payslip — {run.month}/{run.year}</b> ({_escape(payslip.status)})",
            f"Gross: ₹{payslip.gross_earnings}",
            f"Deductions: ₹{payslip.total_deductions}",
            f"Net Pay: ₹{payslip.net_pay}",
            f"Worked days: {payslip.worked_days} · LOP: {payslip.lop_days}",
        ]
        comps = list(payslip.components.all())
        if comps:
            lines.append("\n<b>Breakdown</b>")
            for c in comps:
                lines.append(f"• {_escape(c.component_name)} ({_escape(c.component_type)}): ₹{c.amount}")
        return "\n".join(lines)

    def _quick_leave_balance(self, user: CustomUser) -> str:
        from leaves.models import LeaveBalance

        year = date.today().year
        balances = LeaveBalance.objects.filter(
            user_id=user.id, year=year
        ).select_related("leave_type")
        if not balances:
            return "No leave balances found for this year. Contact HR if this looks wrong."

        lines = [f"<b>Leave balance ({year})</b>\n"]
        for bal in balances:
            lines.append(
                f"🏖 <b>{_escape(bal.leave_type.name)}</b>\n"
                f"Available: {bal.get_available_balance()} · "
                f"Total: {bal.total_entitled} · "
                f"Used: {bal.used} · "
                f"Pending: {bal.pending_approval}"
            )
        return "\n\n".join(lines)

    def _quick_attendance(self, user: CustomUser) -> str:
        from attendance.models import AttendanceRecord

        today = date.today()
        record = AttendanceRecord.objects.filter(
            user_id=user.id, attendance_date=today
        ).first()
        if not record:
            return f"📍 <b>Attendance — {today}</b>\nYou have not checked in yet today."

        login = record.login_time.strftime("%H:%M") if record.login_time else "—"
        logout = record.logout_time.strftime("%H:%M") if record.logout_time else "—"
        hours = record.worked_hours if record.worked_hours is not None else "—"
        status = record.status or ""
        return (
            f"📍 <b>Attendance — {today}</b>\n"
            f"Status: {_escape(str(status))}\n"
            f"Check-in: {login}\n"
            f"Check-out: {logout}\n"
            f"Hours: {hours}"
        )

    def _quick_pending_leaves(self, user: CustomUser) -> str:
        from leaves.models import LeaveRequest

        requests = (
            LeaveRequest.objects.filter(user_id=user.id, _status="pending")
            .select_related("leave_type")
            .order_by("-from_date")
        )
        if not requests:
            return "You have no pending leave requests."

        lines = ["<b>Pending leave requests</b>\n"]
        for r in requests:
            lines.append(
                f"📋 #{r.id} <b>{_escape(r.leave_type.name)}</b>\n"
                f"{r.from_date} → {r.to_date} ({r.duration_days} days)\n"
                f"Reason: {_escape(r.reason or '—')}"
            )
        return "\n\n".join(lines)

    # ------------------------------------------------------------------ auth
    def _restart_auth(self, session: BotSession) -> BotReply:
        adapter = get_adapter(session.platform)
        session.is_verified = False
        session.auth_state = BotSession.AUTH_AWAITING_IDENTITY
        session.user = None
        session.pending_identity = None
        session.expires_at = None
        session.save(
            update_fields=[
                "is_verified",
                "auth_state",
                "user",
                "pending_identity",
                "expires_at",
                "updated_at",
            ]
        )
        return _reply(session.platform, _welcome(session.platform), reply_markup=adapter.remove_keyboard())

    def _logout(self, session: BotSession) -> BotReply:
        adapter = get_adapter(session.platform)
        if session.user_id:
            try:
                clear_bot_history(session.user_id)
            except Exception:
                pass
        session.mark_expired()
        return _reply(
            session.platform,
            (
                "You've been logged out. "
                + (
                    "Type <b>start</b> or run <b>/teamzen start</b> to sign in again."
                    if session.platform == BotSession.PLATFORM_SLACK
                    else (
                        "Send <b>hi</b> to sign in again."
                        if session.platform == BotSession.PLATFORM_WHATSAPP
                        else "Send /start to sign in again."
                    )
                )
            ),
            reply_markup=adapter.remove_keyboard(),
        )

    def _handle_auth_flow(self, session: BotSession, text: str) -> str:
        if session.auth_state == BotSession.AUTH_AWAITING_OTP:
            return self._verify_otp(session, text)
        return self._start_otp(session, text)

    def _find_user(self, identity: str) -> Optional[CustomUser]:
        identity = identity.strip()
        if _looks_like_email(identity):
            return CustomUser.objects.filter(email__iexact=identity, is_active=True).first()

        phone = _normalize_phone(identity)
        if len(phone) >= 8:
            digits = re.sub(r"\D", "", phone)
            return (
                CustomUser.objects.filter(is_active=True)
                .filter(
                    Q(phone_number__iexact=phone)
                    | Q(phone_number__endswith=digits[-10:])
                )
                .first()
            )
        return None

    def _start_otp(self, session: BotSession, identity: str) -> str:
        user = self._find_user(identity)
        generic = (
            "If that account exists, an OTP has been sent to the registered email. "
            "Please enter the 6-digit code."
        )
        if not user:
            session.auth_state = BotSession.AUTH_AWAITING_IDENTITY
            session.pending_identity = None
            session.save(update_fields=["auth_state", "pending_identity", "updated_at"])
            return (
                "I couldn't match that to an active employee. "
                "Please enter your registered work email or phone number."
            )

        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        cache.set(_otp_cache_key(session.platform, session.chat_id), otp, timeout=300)

        session.auth_state = BotSession.AUTH_AWAITING_OTP
        session.pending_identity = user.email
        session.user = None
        session.is_verified = False
        session.save(
            update_fields=[
                "auth_state",
                "pending_identity",
                "user",
                "is_verified",
                "updated_at",
            ]
        )

        email_ok = False
        try:
            self._send_otp_email(user, otp)
            email_ok = True
        except Exception:
            logger.exception("Failed to send bot OTP email to %s", user.email)

        if session.platform == BotSession.PLATFORM_TELEGRAM and not email_ok:
            if getattr(settings, "DEBUG", False):
                logger.warning("[bot_gateway] DEBUG OTP for %s: %s", user.email, otp)
            try:
                from bot_gateway.adapters import telegram_api

                telegram_api.send_message(
                    session.chat_id,
                    (
                        f"Your Teamzen login code is <b>{otp}</b>\n"
                        f"Valid for 5 minutes. Reply with this code to continue."
                    ),
                )
                return (
                    "Email delivery is temporarily blocked (Brevo IP allowlist). "
                    "I sent your OTP in this chat instead — enter the 6-digit code."
                )
            except Exception:
                logger.exception("Telegram OTP fallback also failed")
                return (
                    "I found your account but could not send the OTP. "
                    "Authorize your IP in Brevo, then try again: "
                    "https://app.brevo.com/security/authorised_ips"
                )

        if session.platform == BotSession.PLATFORM_WHATSAPP and not email_ok:
            if getattr(settings, "DEBUG", False):
                logger.warning("[bot_gateway] DEBUG OTP for %s: %s", user.email, otp)
            try:
                from bot_gateway.adapters import whatsapp_api

                whatsapp_api.send_message(
                    session.chat_id,
                    (
                        f"Your Teamzen login code is *{otp}*\n"
                        f"Valid for 5 minutes. Reply with this code to continue."
                    ),
                )
                return (
                    "Email delivery failed. I sent your OTP in this chat — "
                    "enter the 6-digit code."
                )
            except Exception:
                logger.exception("WhatsApp OTP fallback also failed")

        if session.platform == BotSession.PLATFORM_SLACK and not email_ok:
            if getattr(settings, "DEBUG", False):
                logger.warning("[bot_gateway] DEBUG OTP for %s: %s", user.email, otp)
                return (
                    f"Email delivery failed. DEBUG OTP: <b>{otp}</b> "
                    f"(valid 5 minutes)."
                )

        if not email_ok:
            return (
                "I found your account but could not send the OTP email. "
                "Please try again in a moment or contact HR."
            )

        return generic

    def _send_otp_email(self, user: CustomUser, otp: str) -> None:
        from notifications.email_backends import BrevoHTTPBackend
        from temp_email.otp_email import get_otp_email_html

        employee_name = f"{user.first_name} {user.last_name}".strip() or "Employee"
        html_content = get_otp_email_html(
            employee_name=employee_name,
            otp_code=otp,
            expiry_minutes=5,
        )
        email_msg = EmailMultiAlternatives(
            subject="Your Teamzen Bot Login OTP",
            body=(
                f"Hi {employee_name},\n\n"
                f"Your Teamzen bot security code is {otp}. "
                f"It is valid for 5 minutes.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            connection=BrevoHTTPBackend(),
        )
        email_msg.attach_alternative(html_content, "text/html")
        email_msg.send(fail_silently=False)

    def _verify_otp(self, session: BotSession, code: str) -> str:
        # After verify we return plain text; handle_text wraps verified users
        # with menu via a special path — return marker handled below.
        code = re.sub(r"\s+", "", code)
        if not re.fullmatch(r"\d{6}", code):
            return "Please enter the 6-digit OTP. Or send /start to restart."

        cached = cache.get(_otp_cache_key(session.platform, session.chat_id))
        if not cached or cached != code:
            return "Invalid or expired OTP. Request a new one with /start."

        cache.delete(_otp_cache_key(session.platform, session.chat_id))

        user = None
        if session.pending_identity:
            user = CustomUser.objects.filter(
                email__iexact=session.pending_identity, is_active=True
            ).first()
        if not user:
            return "Session expired. Please send /start and try again."

        session.user = user
        session.is_verified = True
        session.auth_state = BotSession.AUTH_VERIFIED
        session.pending_identity = None
        session.expires_at = timezone.now() + _session_ttl()
        session.save(
            update_fields=[
                "user",
                "is_verified",
                "auth_state",
                "pending_identity",
                "expires_at",
                "updated_at",
            ]
        )

        name = _escape((user.first_name or user.email).strip())
        return (
            f"✅ Verified! Hi {name}, I'm your Teamzen HR Assistant.\n\n"
            f"{HELP_TEXT}"
        )

    # --------------------------------------------------------------- agent
    def _handle_agent_message(self, session: BotSession, text: str) -> BotReply:
        try:
            context = {
                BotSession.PLATFORM_SLACK: "slack",
                BotSession.PLATFORM_WHATSAPP: "whatsapp",
            }.get(session.platform, "telegram")
            raw = run_agent_for_user(session.user, text, context=context)
            return _reply(
                session.platform,
                format_for_bot(raw),
                reply_markup=_menu_markup(session.platform),
            )
        except Exception:
            logger.exception("Agent failed for bot user=%s", session.user_id)
            return _reply(
                session.platform,
                "Sorry — I hit an error talking to the assistant. "
                "Please try again in a moment.",
                reply_markup=_menu_markup(session.platform),
            )

    # ----------------------------------------------------------- approvals
    def _try_text_approval(self, session: BotSession, text: str) -> Optional[str]:
        m = re.match(r"^(approve|reject)\s+#?(\d+)\s*(.*)$", text.strip(), re.I)
        if not m:
            return None
        action, leave_id, reason = m.group(1).lower(), int(m.group(2)), m.group(3).strip()
        if action == "approve":
            msg, _ = self._approve_leave(session.user, leave_id)
            return msg
        msg, _ = self._reject_leave(session.user, leave_id, comments=reason or None)
        return msg

    def _can_manage_leave(self, actor: CustomUser, leave) -> bool:
        if actor.role in ("admin", "superadmin", "hr"):
            return True
        if actor.role == "manager" and leave.user.manager_id == actor.id:
            return True
        return False

    def _approve_leave(self, actor: CustomUser, leave_id: int) -> tuple[str, bool]:
        from leaves.models import LeaveRequest
        from leaves.services import approve_leave_request

        try:
            leave = LeaveRequest.objects.select_related("user", "leave_type").get(id=leave_id)
        except LeaveRequest.DoesNotExist:
            return ("Leave request not found.", False)

        if leave._status != "pending":
            return (f"This request is already {leave._status}.", False)

        if not self._can_manage_leave(actor, leave):
            return ("You are not allowed to approve this request.", False)

        try:
            approve_leave_request(leave, actor)
        except Exception as e:
            logger.exception("Approve leave failed")
            return (f"Could not approve: {e}", False)

        self._notify_employee_bots(
            leave.user_id,
            (
                f"✅ Your <b>{leave.leave_type.name}</b> leave "
                f"({leave.from_date} → {leave.to_date}) was approved by {actor.first_name}."
            ),
        )
        return (
            f"Approved leave #{leave.id} for {leave.user.first_name} "
            f"({leave.leave_type.name}, {leave.from_date} → {leave.to_date}).",
            True,
        )

    def _reject_leave(
        self, actor: CustomUser, leave_id: int, comments: Optional[str] = None
    ) -> tuple[str, bool]:
        from leaves.models import LeaveRequest
        from leaves.services import reject_leave_request

        try:
            leave = LeaveRequest.objects.select_related("user", "leave_type").get(id=leave_id)
        except LeaveRequest.DoesNotExist:
            return ("Leave request not found.", False)

        if leave._status != "pending":
            return (f"This request is already {leave._status}.", False)

        if not self._can_manage_leave(actor, leave):
            return ("You are not allowed to reject this request.", False)

        try:
            reject_leave_request(leave, actor, comments=comments)
        except Exception as e:
            logger.exception("Reject leave failed")
            return (f"Could not reject: {e}", False)

        self._notify_employee_bots(
            leave.user_id,
            (
                f"❌ Your <b>{leave.leave_type.name}</b> leave "
                f"({leave.from_date} → {leave.to_date}) was rejected by {actor.first_name}."
            ),
        )
        return (
            f"Rejected leave #{leave.id} for {leave.user.first_name}.",
            True,
        )

    def _notify_employee_bots(self, user_id: int, html_text: str) -> None:
        try:
            from notifications.proactive import notify_bot_user

            notify_bot_user(user_id, html_text)
        except Exception:
            logger.exception("Failed to notify employee via bots user_id=%s", user_id)

    def notify_managers_of_leave(self, leave) -> None:
        from leaves.models import LeaveRequest
        from notifications.utils import get_management_ids

        if not isinstance(leave, LeaveRequest):
            leave = LeaveRequest.objects.select_related(
                "user", "user__department", "leave_type"
            ).get(pk=leave.pk)
        else:
            _ = leave.user
            _ = leave.leave_type

        recipient_ids = get_management_ids(leave.user)
        if not recipient_ids:
            return

        dept = ""
        if getattr(leave.user, "department", None):
            dept = f" ({leave.user.department.name})"

        body = (
            f"📋 <b>Leave Request</b>\n\n"
            f"From: {leave.user.first_name} {leave.user.last_name}{dept}\n"
            f"Type: {leave.leave_type.name}\n"
            f"Dates: {leave.from_date} → {leave.to_date}\n"
            f"Days: {leave.duration_days}\n"
            f"Reason: {leave.reason or '—'}\n\n"
            f"Tap a button below, or reply <code>APPROVE {leave.id}</code> / "
            f"<code>REJECT {leave.id}</code>"
        )

        sessions = BotSession.objects.filter(
            user_id__in=recipient_ids,
            platform__in=[
                BotSession.PLATFORM_TELEGRAM,
                BotSession.PLATFORM_SLACK,
                BotSession.PLATFORM_WHATSAPP,
            ],
            is_verified=True,
        )
        for session in sessions:
            if not session.is_active:
                continue
            try:
                adapter = get_adapter(session.platform)
                keyboard = adapter.leave_approval_keyboard(leave.id)
                adapter.send_message(
                    session.chat_id,
                    format_for_platform(body, session.platform),
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception(
                    "Failed to send leave approval to %s chat=%s",
                    session.platform,
                    session.chat_id,
                )
