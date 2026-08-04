"""AI helpers for onboarding: template copilot + offer polish."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

VALID_ROLES = {"hr", "it", "manager", "hire"}
VALID_PHASES = {"preboarding", "day1", "week1", "day30", "day90"}
VALID_DOC_CATS = {
    "",
    "id_proof",
    "pan",
    "aadhaar",
    "bank_proof",
    "education",
    "offer",
    "signed_policy",
    "other",
}


def _extract_json_array(text: str) -> list[Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            return data["tasks"]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return []


def suggest_onboarding_tasks(
    organization_id: int,
    prompt: str,
    *,
    employment_type: str = "",
    department: str = "",
) -> list[dict]:
    """
    Ask the org LLM for a checklist of onboarding tasks.
    Returns normalized dicts ready for UpsertTaskDefinition / UI preview.
    """
    from ai_engine.graph import get_llm
    from ai_engine.views import _normalize_llm_content
    from langchain_core.messages import HumanMessage, SystemMessage

    system = (
        "You are an HR onboarding designer for Teamzen. "
        "Given a hiring scenario, propose a practical onboarding checklist. "
        "Return ONLY a JSON array of objects with keys: "
        "title (string), description (string), assignee_role "
        "(one of: hire, hr, it, manager), phase "
        "(one of: preboarding, day1, week1, day30, day90), "
        "due_offset_days (int, days relative to join date, negative = before), "
        "requires_document_category (empty string or one of: "
        "id_proof, pan, aadhaar, bank_proof, education, offer, signed_policy, other), "
        "is_required (boolean). "
        "Propose 8–14 tasks covering preboarding KYC through day 30/90. "
        "No markdown, no commentary."
    )
    user_msg = (
        f"Scenario: {prompt.strip()}\n"
        f"Employment type: {employment_type or 'unspecified'}\n"
        f"Department: {department or 'unspecified'}"
    )

    llm = get_llm(organization_id)
    result = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=user_msg)]
    )
    text = _normalize_llm_content(getattr(result, "content", result)).strip()
    items = _extract_json_array(text)

    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        role = str(item.get("assignee_role") or "hire").lower().strip()
        if role not in VALID_ROLES:
            role = "hire"
        phase = str(item.get("phase") or "preboarding").lower().strip()
        if phase not in VALID_PHASES:
            phase = "preboarding"
        doc = str(item.get("requires_document_category") or "").strip()
        if doc not in VALID_DOC_CATS:
            doc = ""
        try:
            offset = int(item.get("due_offset_days", 0))
        except (TypeError, ValueError):
            offset = 0
        normalized.append(
            {
                "title": title[:255],
                "description": str(item.get("description") or "")[:2000],
                "assignee_role": role,
                "phase": phase,
                "due_offset_days": offset,
                "requires_document_category": doc,
                "is_required": bool(item.get("is_required", True)),
                "sort_order": (i + 1) * 10,
            }
        )
    return normalized


def polish_offer_letter(
    organization_id: int,
    body_html: str,
    *,
    tone: str = "professional",
) -> str:
    """Rewrite offer letter HTML body while keeping merge fields intact."""
    from ai_engine.graph import get_llm
    from ai_engine.views import _normalize_llm_content
    from langchain_core.messages import HumanMessage, SystemMessage

    system = (
        f"You polish employment offer letters. Tone: {tone}. "
        "Preserve ALL merge fields exactly as written "
        "(e.g. {{employee_name}}, {{designation}}, {{join_date}}, {{company_name}}, "
        "{{department}}, {{manager_name}}). "
        "Return ONLY HTML body content (no <html>/<body> wrappers, no markdown fences)."
    )
    llm = get_llm(organization_id)
    result = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=body_html[:8000]),
        ]
    )
    text = _normalize_llm_content(getattr(result, "content", result)).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:html)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text
