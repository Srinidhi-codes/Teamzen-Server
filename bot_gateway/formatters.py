"""Convert GenUI card markup from the LangGraph agent into bot-friendly text."""

from __future__ import annotations

import html
import re

from bot_gateway.models import BotSession


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in body.split("|"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _escape(text: str) -> str:
    return html.escape(text or "", quote=False)


def html_to_mrkdwn(text: str) -> str:
    """Convert simple Telegram HTML tags to Slack mrkdwn."""
    if not text:
        return ""
    out = text
    out = re.sub(r"<b>(.*?)</b>", r"*\1*", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<strong>(.*?)</strong>", r"*\1*", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<i>(.*?)</i>", r"_\1_", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<em>(.*?)</em>", r"_\1_", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<code>(.*?)</code>", r"`\1`", out, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<[^>]+>", "", out)
    out = html.unescape(out)
    return out


def format_for_platform(text: str, platform: str) -> str:
    """Adapt HTML bot text for the target platform."""
    if platform in (BotSession.PLATFORM_SLACK, BotSession.PLATFORM_WHATSAPP):
        return html_to_mrkdwn(text)
    return text


def format_for_bot(ai_response: str) -> str:
    """
    Strip [CARD] syntax and produce Telegram HTML text.
    Falls back to plain escaped text when no cards are present.
    """
    if not ai_response:
        return "I didn't get a response. Please try again."

    text = ai_response

    def replace_payroll(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        month = _escape(f.get("month", ""))
        year = _escape(f.get("year", ""))
        lines = [
            f"<b>Payslip — {month} {year}</b>",
            f"Gross: ₹{_escape(f.get('gross', ''))}",
            f"Net Pay: ₹{_escape(f.get('net', ''))}",
            f"Deductions: ₹{_escape(f.get('deductions', ''))}",
        ]
        if f.get("worked_days"):
            lines.append(f"Worked days: {_escape(f['worked_days'])}")
        if f.get("lop"):
            lines.append(f"LOP: {_escape(f['lop'])}")
        return "\n".join(lines)

    def replace_balance(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        name = _escape(f.get("Name", "Leave"))
        available = _escape(f.get("Available", "?"))
        total = _escape(f.get("Total", "?"))
        used = _escape(f.get("Used", "?"))
        pending = _escape(f.get("Pending", "?"))
        return (
            f"🏖 <b>{name}</b>\n"
            f"Available: {available} · Total: {total} · Used: {used} · Pending: {pending}"
        )

    def replace_attendance(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        action = _escape(f.get("Action", "Attendance"))
        status = _escape(f.get("Status", ""))
        time_s = _escape(f.get("Time", ""))
        office = _escape(f.get("Office", ""))
        extra = []
        if f.get("Distance"):
            extra.append(f"Distance: {_escape(f['Distance'])}")
        if f.get("Hours"):
            extra.append(f"Hours: {_escape(f['Hours'])}")
        tail = (" · " + " · ".join(extra)) if extra else ""
        office_bit = f" @ {office}" if office else ""
        return f"✅ <b>{action}</b>: {status}{office_bit}\n{time_s}{tail}".strip()

    def replace_insight(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        title = _escape(f.get("title", "Insight"))
        message = _escape(f.get("message", ""))
        topic = _escape(f.get("topic", ""))
        header = f"<b>{title}</b>" + (f" ({topic})" if topic else "")
        return f"💡 {header}\n{message}"

    def replace_error(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        title = _escape(f.get("title", "Error"))
        message = _escape(f.get("message", ""))
        return f"⚠️ <b>{title}</b>\n{message}"

    def replace_pending_leave(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        leave_id = _escape(f.get("id", f.get("ID", "?")))
        leave_type = _escape(f.get("type", f.get("Type", "Leave")))
        dates = _escape(f.get("dates", f.get("Dates", "")))
        return f"📋 Pending #{leave_id}: <b>{leave_type}</b> {dates}".strip()

    def replace_correction(match: re.Match) -> str:
        f = _parse_fields(match.group(1))
        corr_id = _escape(f.get("id", "?"))
        corr_date = _escape(f.get("date", ""))
        suggested = _escape(f.get("suggested_logout", f.get("suggested logout", "—")))
        return (
            f"⏱ Correction #{corr_id}: <b>{corr_date}</b> "
            f"suggested logout {suggested}. "
            f"Reply: confirm correction {corr_id}"
        ).strip()

    replacements = [
        (r"\[PAYROLL_CARD\](.*?)\[/PAYROLL_CARD\]", replace_payroll),
        (r"\[BALANCE_CARD\](.*?)\[/BALANCE_CARD\]", replace_balance),
        (r"\[ATTENDANCE_CARD\](.*?)\[/ATTENDANCE_CARD\]", replace_attendance),
        (r"\[INSIGHT_CARD\](.*?)\[/INSIGHT_CARD\]", replace_insight),
        (r"\[ERROR_CARD\](.*?)\[/ERROR_CARD\]", replace_error),
        (r"\[PENDING_LEAVE_CARD\](.*?)\[/PENDING_LEAVE_CARD\]", replace_pending_leave),
        (r"\[CORRECTION_CARD\](.*?)\[/CORRECTION_CARD\]", replace_correction),
    ]

    for pattern, replacer in replacements:
        text = re.sub(pattern, replacer, text, flags=re.DOTALL | re.IGNORECASE)

    # Remaining markdown → Telegram HTML
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Escape leftover angle brackets that aren't our tags
    # (cards already emit escaped content; keep simple strip of raw <script>)
    text = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)

    return text.strip() or "Done."
