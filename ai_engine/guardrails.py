"""
Lightweight prompt-injection / jailbreak detection for the Teamzen assistant.

High-confidence probes are short-circuited before the LLM/tool loop.
Lower-confidence cases still rely on system-prompt SECURITY_GUARDRAILS.
"""
from __future__ import annotations

import re

# Patterns that clearly ask to override instructions or exfiltrate the prompt.
_JAILBREAK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?)",
        r"disregard\s+(all\s+)?(previous|prior|system)\s+(instructions?|rules?|prompts?)",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"show\s+(me\s+)?(your\s+)?(system\s+)?prompt",
        r"print\s+(your\s+)?(system\s+)?prompt",
        r"what\s+are\s+your\s+(hidden\s+)?(system\s+)?instructions",
        r"dump\s+(your\s+)?(system\s+)?prompt",
        r"\bDAN\b|do\s+anything\s+now",
        r"developer\s+mode\s*(on|enabled|override)?",
        r"you\s+are\s+now\s+(unrestricted|jailbroken|without\s+limits)",
        r"override\s+(your\s+)?(safety|security|guardrails?)",
        r"pretend\s+you\s+have\s+no\s+(rules|restrictions|guardrails)",
        r"repeat\s+(the\s+)?(text|content)\s+(above|before)\s+the\s+user",
        r"output\s+(your\s+)?(initial|system)\s+(system\s+)?(message|prompt)",
    )
]

_REFUSAL = (
    "I'm sorry, but I can't disclose internal instructions or system prompts. "
    "However, I'm here to assist you with information regarding leaves, attendance, "
    "payslips, company policies, and onboarding tasks. How can I help you today?"
)


def is_jailbreak_probe(query: str) -> bool:
    text = (query or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _JAILBREAK_PATTERNS)


def jailbreak_refusal_message() -> str:
    return _REFUSAL
