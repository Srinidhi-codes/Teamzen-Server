"""
AI Engine Graph — Teamzen LangGraph Agent
==========================================
Uses MCP (Model Context Protocol) for tool discovery when the MCP server
is running, with an automatic fallback to the legacy LangChain @tool list
if MCP is unavailable (e.g., local dev without the server running).
"""

from typing import Annotated, Sequence, TypedDict, Union, List, Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from django.conf import settings
from datetime import date
from .models import PolicyDocument, AIConfiguration
from pgvector.django import L2Distance
import json
import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server configuration
# ---------------------------------------------------------------------------
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp")
MCP_ENABLED = os.environ.get("MCP_ENABLED", "true").lower() == "true"
MCP_MULTI_SERVER = os.environ.get("MCP_MULTI_SERVER", "false").lower() == "true"
MCP_INTERNAL_SECRET = os.environ.get("MCP_INTERNAL_SECRET", "").strip()
MCP_ATTENDANCE_URL = os.environ.get("MCP_ATTENDANCE_URL", "http://localhost:8002/mcp")
MCP_LEAVES_URL = os.environ.get("MCP_LEAVES_URL", "http://localhost:8003/mcp")
MCP_PAYROLL_URL = os.environ.get("MCP_PAYROLL_URL", "http://localhost:8004/mcp")
MCP_POLICY_URL = os.environ.get("MCP_POLICY_URL", "http://localhost:8005/mcp")


def _mcp_headers(
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    user_role: Optional[str] = None,
) -> dict:
    """Headers for LangGraph -> MCP (internal secret + logged-in identity)."""
    headers: dict = {}
    if MCP_INTERNAL_SECRET:
        headers["X-MCP-Internal-Secret"] = MCP_INTERNAL_SECRET
    if user_id is not None:
        headers["X-MCP-User-Id"] = str(user_id)
    if organization_id is not None:
        headers["X-MCP-Organization-Id"] = str(organization_id)
    if user_role:
        headers["X-MCP-User-Role"] = str(user_role)
    return headers


def _mcp_server_config(
    url: str,
    *,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    user_role: Optional[str] = None,
) -> dict:
    cfg = {
        "url": url,
        "transport": "streamable_http",
    }
    headers = _mcp_headers(user_id, organization_id, user_role)
    if headers:
        cfg["headers"] = headers
    return cfg


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
    organization_id: int
    user_role: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    payslip_context: Optional[str]
    page_path: Optional[str]
    app_context: Optional[str]  # 'user' | 'admin' — which frontend host is chatting


# ---------------------------------------------------------------------------
# Legacy fallback tools (used when MCP server is not running)
# ---------------------------------------------------------------------------
def _get_legacy_tools():
    """Return the original LangChain @tool list as fallback."""
    from .tools import (
        get_leave_balances, apply_for_leave, get_attendance_today,
        search_policies, get_leave_types, mark_attendance,
        check_team_availability, get_user_details, get_team_stats, list_pending_leaves,
        cancel_leave, suggest_leave_window, get_attendance_trends,
        generate_monthly_summary, get_latest_payslip, get_payslip,
        explain_deduction, salary_forecast, compare_payslips, get_payroll_history,
        get_team_pulse, list_pending_corrections, confirm_attendance_correction,
        review_attendance_correction,
        check_payroll_anomalies, check_calendar_conflicts,
        get_my_onboarding_status, list_pending_onboarding_tasks,
        explain_onboarding_task, get_required_documents, complete_onboarding_task_tool,
        suggest_onboarding_checklist, polish_offer_letter_draft, suggest_route,
    )
    return [
        get_leave_balances, apply_for_leave, get_attendance_today,
        search_policies, get_leave_types, mark_attendance,
        check_team_availability, get_user_details, get_team_stats, list_pending_leaves,
        cancel_leave, suggest_leave_window, get_attendance_trends,
        generate_monthly_summary, get_latest_payslip, get_payslip,
        explain_deduction, salary_forecast, compare_payslips, get_payroll_history,
        get_team_pulse, list_pending_corrections, confirm_attendance_correction,
        review_attendance_correction, check_payroll_anomalies, check_calendar_conflicts,
        get_my_onboarding_status, list_pending_onboarding_tasks,
        explain_onboarding_task, get_required_documents, complete_onboarding_task_tool,
        suggest_onboarding_checklist, polish_offer_letter_draft, suggest_route,
    ]


# ---------------------------------------------------------------------------
# MCP tool loader (async)
# ---------------------------------------------------------------------------
async def _get_mcp_tools(
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    user_role: Optional[str] = None,
):
    """
    Connect to Teamzen MCP server(s) and retrieve tools.
    Passes logged-in user identity headers so the MCP server can overwrite tool args.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        kw = dict(
            user_id=user_id,
            organization_id=organization_id,
            user_role=user_role,
        )
        if MCP_MULTI_SERVER:
            servers = {
                "attendance": _mcp_server_config(MCP_ATTENDANCE_URL, **kw),
                "leaves": _mcp_server_config(MCP_LEAVES_URL, **kw),
                "payroll": _mcp_server_config(MCP_PAYROLL_URL, **kw),
                "policy": _mcp_server_config(MCP_POLICY_URL, **kw),
            }
        else:
            servers = {
                "teamzen": _mcp_server_config(MCP_SERVER_URL, **kw),
            }

        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
        logger.info(
            "[MCP] Loaded %s tools from %s (user=%s org=%s)",
            len(tools),
            "multi-server" if MCP_MULTI_SERVER else MCP_SERVER_URL,
            user_id,
            organization_id,
        )
        return tools, None
    except Exception as e:
        logger.warning(f"[MCP] Server unavailable ({e}), falling back to legacy tools.")
        return None, None


# ---------------------------------------------------------------------------
# LLM Factory
# ---------------------------------------------------------------------------
def get_llm(organization_id: int):
    """Load the appropriate LLM based on organization AI configuration."""
    config = AIConfiguration.objects.filter(
        organization_id=organization_id, is_active=True
    ).first()

    model_name = config.model_name if config else "gpt-4o-mini"
    temp = config.temperature if config else 0
    max_tokens = config.max_tokens if config else 1024

    # Remap retired provider model IDs so older org configs keep working
    model_name = AIConfiguration.LEGACY_MODEL_MAP.get(model_name, model_name)

    # Free-tier Groq 8B has a low TPM cap — keep completions small
    if _is_token_constrained_model(model_name):
        max_tokens = min(int(max_tokens or 1024), 512)

    if "gemini" in model_name:
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not configured. Set it in the backend environment "
                "to use Gemini models."
            )
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temp,
            google_api_key=api_key,
            max_output_tokens=max_tokens,
            streaming=True,
        )

    if "llama" in model_name or "mixtral" in model_name:
        from langchain_groq import ChatGroq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Set it in the backend environment "
                "to use Groq / Llama models."
            )
        return ChatGroq(
            model=model_name,
            temperature=temp,
            groq_api_key=api_key,
            max_tokens=max_tokens,
            streaming=True,
        )

    openai_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in the backend environment "
            "to use OpenAI models."
        )
    return ChatOpenAI(
        model=model_name,
        temperature=temp,
        openai_api_key=openai_key,
        max_tokens=max_tokens,
        streaming=True,
    )


def resolve_model_name(organization_id: int) -> str:
    """Return the effective model id for an org (after legacy remaps)."""
    config = AIConfiguration.objects.filter(
        organization_id=organization_id, is_active=True
    ).first()
    model_name = config.model_name if config else "gpt-4o-mini"
    return AIConfiguration.LEGACY_MODEL_MAP.get(model_name, model_name)


def _is_token_constrained_model(model_name: str) -> bool:
    """Groq free-tier small models have low TPM (~6k) — full agent payloads fail."""
    name = (model_name or "").lower()
    return name in {
        "llama-3.1-8b-instant",
        "llama3-8b-8192",
        "llama-3-8b-8192",
    } or ("8b" in name and ("llama" in name or "groq" in name))


# Essential tools only — keeps tool schemas under Groq 8B TPM limits
_CORE_TOOL_NAMES = frozenset(
    {
        "get_leave_balances",
        "get_leave_types",
        "apply_for_leave",
        "list_pending_leaves",
        "cancel_leave",
        "get_attendance_today",
        "mark_attendance",
        "search_policies",
        "get_user_details",
        "get_latest_payslip",
        "get_payslip",
        "explain_deduction",
        "get_my_onboarding_status",
        "list_pending_onboarding_tasks",
        "get_required_documents",
        "suggest_route",
    }
)


def _tool_name(tool) -> str:
    return (
        getattr(tool, "name", None)
        or getattr(getattr(tool, "metadata", None), "name", None)
        or getattr(tool, "__name__", "")
        or ""
    )


def _filter_tools_for_model(tools: list, model_name: str) -> list:
    if not _is_token_constrained_model(model_name):
        return tools
    filtered = [t for t in tools if _tool_name(t) in _CORE_TOOL_NAMES]
    if not filtered:
        filtered = list(tools)[:8]
    logger.info(
        "[Graph] Constrained model %s — using %s/%s tools",
        model_name,
        len(filtered),
        len(tools),
    )
    return filtered


def _trim_messages_for_model(messages: Sequence[BaseMessage], model_name: str) -> list:
    """Keep recent turns only for TPM-limited models; cap long tool payloads."""
    msgs = list(messages or [])
    if not _is_token_constrained_model(model_name):
        return msgs

    msgs = msgs[-6:]
    trimmed = []
    for m in msgs:
        content = getattr(m, "content", None)
        if not (isinstance(content, str) and len(content) > 1200):
            trimmed.append(m)
            continue
        short = content[:1200] + "\n…[truncated]"
        if isinstance(m, ToolMessage):
            trimmed.append(
                ToolMessage(content=short, tool_call_id=getattr(m, "tool_call_id", ""))
            )
        elif isinstance(m, HumanMessage):
            trimmed.append(HumanMessage(content=short))
        elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            trimmed.append(AIMessage(content=short))
        else:
            trimmed.append(m)
    return trimmed


# ---------------------------------------------------------------------------
# System Prompt Builder
# ---------------------------------------------------------------------------
def _build_system_prompt(state: AgentState, *, compact: bool = False) -> str:
    user_id = state.get("user_id")
    org_id = state.get("organization_id")
    lat = state.get("latitude")
    lon = state.get("longitude")

    user_role = state.get("user_role") or "employee"
    app_context = (state.get("app_context") or "user").lower()
    if app_context not in ("admin", "user"):
        app_context = "user"

    if compact:
        prompt = (
            "You are Teamzen HR assistant. Use tools for leave, attendance, payslips, and policies. "
            f"user_id={user_id}, role={user_role}, organization_id={org_id}, "
            f"app={app_context}, lat={lat}, lon={lon}, today={date.today().isoformat()}. "
            "Always pass user_id/organization_id to tools. "
            "Do not invent payslip or policy facts — use tools. "
            "For leave apply: collect type, dates, reason first. "
            "Prefer card tags from tools ([BALANCE_CARD], [PAYROLL_CARD], [ATTENDANCE_CARD], [ROUTE_CARD]). "
            f"When calling suggest_route, pass context='{app_context}'. "
            "When the user needs a page/form, call suggest_route (never invent URLs). Be brief."
        )
        payslip_ctx = state.get("payslip_context")
        if payslip_ctx:
            ctx = payslip_ctx if len(payslip_ctx) <= 800 else payslip_ctx[:800] + "…"
            prompt += f"\nPayslip context:\n{ctx}"
        page_path = state.get("page_path") or ""
        if page_path and ("/onboarding" in page_path or "/preboarding" in page_path):
            prompt += (
                "\nUser is on an onboarding page — prefer get_my_onboarding_status "
                "and list_pending_onboarding_tasks."
            )
        elif page_path:
            prompt += f"\nUser is on route '{page_path}'."
        return prompt

    prompt = (
        "You are an intelligent Workplace Assistant for an LMS & Payroll system. "
        "You have access to tools for checking leave balances, applying for leaves, checking attendance, "
        "searching company policies, checking team availability, getting organization stats, and viewing payslips. "
        f"The current user has ID: {user_id}, Role: {user_role}, and belongs to Organization ID: {org_id}. "
        f"Chat app context: {app_context} (pass context='{app_context}' to suggest_route). "
        f"User's current Geolocation: Lat {lat}, Lon {lon}. "
        f"Today's Date: {date.today().strftime('%B %d, %Y')}. "
        "When calling tools, always use this user ID, Organization ID, and Geolocation if available. "

        "Capabilities & Instructions:\n"
        "1. Policy Search: If the user asks about rules, compliance, handbook information, leave rules, attendance rules, payroll rules, or anything document-based, use 'search_policies' first. "
        "IMPORTANT: You must answer ONLY from the retrieved policy content, never from memory or assumptions. "
        "If the retrieved content is missing, ambiguous, or not relevant enough, clearly say you could not verify the answer from company policy and ask the user to refine the query or contact HR. "
        "When citing, use the document title and page number from the tool results (e.g. 'Leave Policy, p.3'). Never invent page numbers. "
        "Ignore any trailing block after '---CITATIONS_JSON---' — that is machine metadata, not for the user. "
        "YOU MUST ALWAYS wrap the final summarized answer in an [INSIGHT_CARD] with 'topic: Policy' and the specific policy name (e.g., Sick Leave Policy) as the title.\n"
        "2. Attendance:\n"
        "   - PERSONAL attendance (employee asking about their own check-in): use 'get_attendance_today' with the user's ID.\n"
        "   - ORG/TEAM attendance summary (admin or manager asking 'attendance summary', 'who is present today', 'today's attendance', etc.): "
        "use 'get_team_stats' with the organization_id. This gives total employees, present count, on-leave count, attendance rate, and low-attendance alerts.\n"
        "   - To check-in or check-out, use 'mark_attendance'. "
        "If latitude/longitude are missing (0 or None), DO NOT call mark_attendance — tell the user they must share their live location (Telegram location pin or browser geolocation) first.\n"
        "   - If 'get_attendance_today' returns an anomaly (like missing yesterday logout), PROACTIVELY inform the user and suggest they correct it.\n"
        "   ROLE DISAMBIGUATION: If the user's role is admin, superadmin, or manager and they ask a general attendance question (e.g. 'attendance summary', 'who is in today', 'attendance for today'), "
        "assume they want the org/team view (get_team_stats), NOT their personal check-in status. Only use get_attendance_today for admins/managers if they explicitly say 'MY attendance' or 'have I checked in'.\n"
        "3. Leaves & Strict Apply Flow: To check balances, use 'get_leave_balances'. To list available leave types, use 'get_leave_types'. "
        "If the user wants to apply for leave, you MUST collect all required details before calling 'apply_for_leave': leave type, exact start date, exact end date, whether it is full day or half day when the leave is for a single day, and a reason from the user. "
        "If any required detail is missing, ask a concise follow-up question and DO NOT call 'apply_for_leave' yet. "
        "You MUST NOT invent, assume, or auto-fill a leave reason. "
        "You SHOULD infer duration from the dates only after dates are known, but for a same-day leave you must clarify whether it is full day, first half, or second half if the user did not specify. "
        "When the user provides dates for a leave request, call 'check_team_availability' before submission and summarize the result to the user. "
        "Also call 'check_calendar_conflicts' for the same dates when Google Calendar may be connected; treat conflicts as advisory (do not block apply). "
        "AVAILABILITY REPORTING: When reporting team availability, ALWAYS use an [INSIGHT_CARD] with 'topic: Team Availability'. Include whether colleagues are already on leave and whether coverage looks clear or busy. "
        "SUBMISSION RULE: Only submit the leave after required details are present and you have reported team availability. Once everything is complete, tell the user you are submitting it now, then call 'apply_for_leave'. "
        "LEAVE MANAGEMENT: If the user wants to cancel a leave, use 'list_pending_leaves' first to show them their pending requests with PENDING_LEAVE_CARDs, then use 'cancel_leave' with the specific ID they choose.\n"
        "4. Payslip / Salary: For the latest slip use 'get_latest_payslip'. For a named month use 'get_payslip' with month (1-12) and year. "
        "To list available months use 'get_payroll_history'. To explain PF/PT/LOP/TDS use 'explain_deduction'. "
        "For 'if I take N unpaid days how much do I lose?' use 'salary_forecast'. "
        "To compare two months use 'compare_payslips' (use get_payroll_history first if months are unclear). "
        "ALWAYS present payslip data via the [PAYROLL_CARD] returned by the tool. "
        "Do NOT invent payslip numbers. Do NOT substitute attendance trends, monthly team summaries, or leave balances for a payslip request.\n"
        "5. User profile: If the user asks who they are, their profile, employee details, department, designation, or manager, use 'get_user_details'. "
        "Managers/HR/admins looking up someone else may pass lookup_email, lookup_employee_id, or lookup_user_id.\n"
        "6. Team Analytics: If the user (Admin/Manager) asks about organization status or trends, use 'get_team_stats'. This tool now also identifies employees with low attendance.\n"
        "REPORTS: If a manager asks for a report or summary for a specific month (e.g., 'Give me the February report'), use 'generate_monthly_summary'. Use the result to present an [INSIGHT_CARD].\n"
        "7. Leave Recommendations: If the user asks for advice on when to take a leave, or if they have a high leave balance, use 'suggest_leave_window'.\n"
        "8. Attendance Trends & Anomalies: Use 'get_attendance_trends' to detect patterns in user attendance (laters, missing checkouts, or drop in rate).\n"
        "9. Team Pulse: If a manager asks for team pulse, weekly team digest, or attendance summary for the team, use 'get_team_pulse' with organization_id and user_id.\n"
        "10. Attendance Corrections: If the user mentions missing checkout, square-off, or pending corrections, call 'list_pending_corrections' first and present CORRECTION_CARDs. "
        "To confirm a draft, call 'confirm_attendance_correction' (optional logout_time HH:MM). "
        "Managers approving/rejecting use 'review_attendance_correction' with decision approved|rejected.\n"
        "11. Payroll Anomalies: Admins can ask 'check payroll anomalies'. Use 'check_payroll_anomalies' with organization_id, month, year to scan for LOP spikes, net pay swings, double deductions, zero net, missing salary structures, and new-joiner pro-rata issues.\n"
        "12. Onboarding: For new-hire checklist questions use 'get_my_onboarding_status', 'list_pending_onboarding_tasks', "
        "'explain_onboarding_task', and 'get_required_documents'. "
        "To mark a task done use 'complete_onboarding_task_tool'. "
        "For handbook/policy questions during onboarding (including 'acknowledge handbook' tasks), use 'search_policies'. "
        "HR/Admin can use 'suggest_onboarding_checklist' to draft templates and 'polish_offer_letter_draft' for offer wording.\n"
        "13. In-app navigation: When the user needs a screen or form (apply leave UI, punch/geofence, upload docs, "
        "view full payslip page, open policies PDF list, HR hire board, etc.), call 'suggest_route' AFTER answering. "
        "Prefer finishing with in-chat tools (balances, status, explanations) when that fully solves the ask. "
        "MUST call suggest_route when the user needs camera, selfie punch, geofence/GPS check-in, file/document upload, "
        "PDF download pages, maps, or a multi-field form they cannot complete in chat — do not pretend chat can replace those UIs. "
        "Never invent URLs — only allowlisted paths via the tool. "
        "Employee paths: /leaves?action=apply, /leaves, /leaves/approvals, /attendance, "
        "/attendance/attendance-correction, /payroll, /onboarding, /policies, /dashboard, /team, /profile. "
        "Admin paths: /onboarding, /onboarding/templates, /onboarding/letters, /leaves?tab=requests, "
        "/employees, /attendance, /payroll, /policies, /settings, /dashboard. "
        "Pass context='admin' when the chat context is admin; otherwise context='user'. "
        "Output the [ROUTE_CARD] from the tool exactly.\n"

        "Formatting Instructions:\n"
        "1. CRITICAL: When explaining or summarizing a payslip, you MUST produce a [PAYROLL_CARD] as your FIRST action. DO NOT use plain text for the breakdown.\n"
        "   Example: [PAYROLL_CARD] month: May | year: 2026 | gross: 35000 | net: 34800 | deductions: 200 | worked_days: 31 | lop: 0 | earnings_breakdown: {Basic Pay:25000, HRA:10000} | deductions_breakdown: {Professional Tax:200} [/PAYROLL_CARD]\n"
        "2. Be professional, concise, and helpful. Stay tightly focused on the user's request and the tool output. Do not add unrelated advice. Use MARKDOWN for headers, lists, and inline bold text outside of cards.\n"
        "   CRITICAL: Always output each breakdown item (like Gross Earnings, Net Pay, Worked Days) on a new line using a clean bullet point (e.g. '- **Gross Earnings:** Rs 35,000') to ensure proper vertical spacing and alignment.\n"
        "3. CRITICAL: When presenting leave balances, you MUST use the [BALANCE_CARD] tag. DO NOT print leave balances in a plain text list or markdown list. Output a separate [BALANCE_CARD] for EACH leave type balance retrieved from the tool. You MUST include ALL five fields (Name, Total, Used, Pending, Available) inside each card tag.\n"
        "   Example: If the tool returns a balance for Casual Leave (Total 10, Used 1.5, Pending 1.0, Available 7.5), you must output exactly:\n"
        "   [BALANCE_CARD] Name: Casual Leave | Total: 10.0 | Used: 1.5 | Pending: 1.0 | Available: 7.5 [/BALANCE_CARD]\n"
        "4. When marking attendance or reporting attendance success/error, use:\n"
        "   [ATTENDANCE_CARD] Action: {Check-in/out} | Status: {status} | Time: {time} | Office: {office} [/ATTENDANCE_CARD]\n"
        "5. For proactive insights (availability, anomalies, trends, or policy details), ALWAYS use:\n"
        "   [INSIGHT_CARD] title: {Title} | message: {Reasoning/Message} | type: {info/warning/stats} | topic: {Topic} | stats: {Key1:Val1, Key2:Val2} [/INSIGHT_CARD]\n"
        "   [ERROR_CARD] title: {Title} | message: {The helpful error message} [/ERROR_CARD]\n"
        "6. Never claim a policy rule, leave rule, payroll rule, or attendance rule unless it came from a tool result or explicit application context. If unsure, say so clearly.\n"
        "7. When listing pending attendance corrections, output the [CORRECTION_CARD] tags returned by the tool exactly (do not convert them to plain text).\n"
        "8. When suggesting navigation, output the [ROUTE_CARD] from 'suggest_route' exactly:\n"
        "   [ROUTE_CARD] path: /leaves?action=apply | label: Request leave | reason: Open the leave form to submit [/ROUTE_CARD]\n"
    )

    payslip_ctx = state.get("payslip_context")
    if payslip_ctx:
        prompt += (
            f"\n\n--- PAYSLIP CONTEXT ---\n"
            f"The user is currently viewing the following payslip. Answer any questions about their salary, "
            f"deductions, or LOP based ONLY on this data:\n{payslip_ctx}"
        )

    page_path = state.get("page_path") or ""
    if page_path and (
        "/onboarding" in page_path or "/preboarding" in page_path
    ):
        prompt += (
            "\n\n--- PAGE CONTEXT ---\n"
            f"The user is on route '{page_path}'. Prioritize onboarding tools "
            "(get_my_onboarding_status, list_pending_onboarding_tasks, get_required_documents, "
            "explain_onboarding_task) and policy search for handbook questions. "
            "Help them complete the next pending checklist item. "
            "If they need the checklist UI, suggest_route to /onboarding."
        )
    elif page_path and "/leaves" in page_path:
        prompt += (
            "\n\n--- PAGE CONTEXT ---\n"
            f"The user is on '{page_path}'. Prefer leave tools (balances, apply, pending, cancel). "
            "If they need the request form UI, suggest_route to /leaves?action=apply."
        )
    elif page_path and "/attendance" in page_path:
        prompt += (
            "\n\n--- PAGE CONTEXT ---\n"
            f"The user is on '{page_path}'. Prefer attendance tools. "
            "For missing checkout UI use suggest_route to /attendance/attendance-correction."
        )
    elif page_path and "/payroll" in page_path:
        prompt += (
            "\n\n--- PAGE CONTEXT ---\n"
            f"The user is on '{page_path}'. Prefer payslip tools (get_latest_payslip, explain_deduction)."
        )
    elif page_path:
        prompt += (
            "\n\n--- PAGE CONTEXT ---\n"
            f"The user is on route '{page_path}'. Bias tools to that page's domain when relevant."
        )

    return prompt


# ---------------------------------------------------------------------------
# Graph Builder (async, MCP-aware)
# ---------------------------------------------------------------------------
async def build_graph(
    organization_id: int,
    user_id: Optional[int] = None,
    user_role: Optional[str] = None,
):
    """
    Builds a compiled LangGraph workflow.
    Attempts to load tools from the MCP server first; falls back to legacy tools.
    Passes the logged-in user identity to MCP so tool args cannot be spoofed.
    Returns (compiled_app, mcp_client_or_None).
    """
    mcp_client = None
    tools = []

    if MCP_ENABLED:
        tools, mcp_client = await _get_mcp_tools(
            user_id=user_id,
            organization_id=organization_id,
            user_role=user_role,
        )

    if not tools:
        tools = _get_legacy_tools()
        logger.info("[Graph] Using legacy LangChain tools.")

    from asgiref.sync import sync_to_async
    model_name = await sync_to_async(resolve_model_name)(organization_id)
    tools = _filter_tools_for_model(tools, model_name)
    compact = _is_token_constrained_model(model_name)

    tool_node = ToolNode(tools)
    llm_base = await sync_to_async(get_llm)(organization_id)
    llm = llm_base.bind_tools(tools)

    def call_model(state: AgentState):
        system_prompt = _build_system_prompt(state, compact=compact)
        messages = _trim_messages_for_model(state["messages"], model_name)
        response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    compiled = workflow.compile()
    return compiled, mcp_client


# ---------------------------------------------------------------------------
# Module-level compiled app (legacy path — used if MCP is disabled)
# Kept for backward compatibility with any code that does `from .graph import app`
# ---------------------------------------------------------------------------
def _build_legacy_app():
    """Synchronously build the graph with legacy tools (used at import time)."""
    tools_all = _get_legacy_tools()

    def call_model(state: AgentState):
        org_id = state.get("organization_id", 0)
        model_name = resolve_model_name(org_id)
        tools = _filter_tools_for_model(tools_all, model_name)
        llm = get_llm(org_id).bind_tools(tools)
        system_prompt = _build_system_prompt(
            state, compact=_is_token_constrained_model(model_name)
        )
        messages = _trim_messages_for_model(state["messages"], model_name)
        response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    # ToolNode needs a static list; use full set — agent only binds filtered tools per call
    workflow.add_node("tools", ToolNode(tools_all))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    return workflow.compile()


# Lazy-initialized legacy fallback (only used if views.py imports `app` directly)
app = _build_legacy_app()