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

# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
    organization_id: int
    latitude: Optional[float]
    longitude: Optional[float]
    payslip_context: Optional[str]


# ---------------------------------------------------------------------------
# Legacy fallback tools (used when MCP server is not running)
# ---------------------------------------------------------------------------
def _get_legacy_tools():
    """Return the original LangChain @tool list as fallback."""
    from .tools import (
        get_leave_balances, apply_for_leave, get_attendance_today,
        search_policies, get_leave_types, mark_attendance,
        check_team_availability, get_team_stats, list_pending_leaves,
        cancel_leave, suggest_leave_window, get_attendance_trends,
        generate_monthly_summary, get_latest_payslip,
    )
    return [
        get_leave_balances, apply_for_leave, get_attendance_today,
        search_policies, get_leave_types, mark_attendance,
        check_team_availability, get_team_stats, list_pending_leaves,
        cancel_leave, suggest_leave_window, get_attendance_trends,
        generate_monthly_summary, get_latest_payslip,
    ]


# ---------------------------------------------------------------------------
# MCP tool loader (async)
# ---------------------------------------------------------------------------
async def _get_mcp_tools():
    """
    Connect to the Teamzen MCP server and retrieve all tools.
    Returns (tools, None) since v0.2+ no longer uses a context manager.
    Returns (None, None) if the server is unreachable.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({
            "teamzen": {
                "url": MCP_SERVER_URL,
                "transport": "streamable_http",
            }
        })
        # v0.2+: no context manager, call get_tools() directly
        tools = await client.get_tools()
        logger.info(f"[MCP] Loaded {len(tools)} tools from {MCP_SERVER_URL}")
        return tools, None  # No client to close in v0.2+
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

    if "gemini" in model_name:
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temp,
            google_api_key=api_key,
            streaming=True,
        )

    elif "llama" in model_name or "mixtral" in model_name:
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        return ChatGroq(
            model=model_name,
            temperature=temp,
            groq_api_key=api_key,
            streaming=True,
        )

    else:
        return ChatOpenAI(
            model=model_name,
            temperature=temp,
            openai_api_key=settings.OPENAI_API_KEY,
            streaming=True,
        )


# ---------------------------------------------------------------------------
# System Prompt Builder
# ---------------------------------------------------------------------------
def _build_system_prompt(state: AgentState) -> str:
    user_id = state.get("user_id")
    org_id = state.get("organization_id")
    lat = state.get("latitude")
    lon = state.get("longitude")

    prompt = (
        "You are an intelligent Workplace Assistant for an LMS & Payroll system. "
        "You have access to tools for checking leave balances, applying for leaves, checking attendance, "
        "searching company policies, checking team availability, getting organization stats, and viewing payslips. "
        f"The current user has ID: {user_id} and belongs to Organization ID: {org_id}. "
        f"User's current Geolocation: Lat {lat}, Lon {lon}. "
        f"Today's Date: {date.today().strftime('%B %d, %Y')}. "
        "When calling tools, always use this user ID, Organization ID, and Geolocation if available. "

        "Capabilities & Instructions:\n"
        "1. Policy Search: If the user asks about rules, compliance, handbook information, leave rules, attendance rules, payroll rules, or anything document-based, use 'search_policies' first. "
        "IMPORTANT: You must answer ONLY from the retrieved policy content, never from memory or assumptions. "
        "If the retrieved content is missing, ambiguous, or not relevant enough, clearly say you could not verify the answer from company policy and ask the user to refine the query or contact HR. "
        "YOU MUST ALWAYS wrap the final summarized answer in an [INSIGHT_CARD] with 'topic: Policy' and the specific policy name (e.g., Sick Leave Policy) as the title.\n"
        "2. Attendance: To check status, use 'get_attendance_today'. To check-in or check-out, use 'mark_attendance'. "
        "If latitude/longitude are missing (0 or None), DO NOT call mark_attendance — tell the user they must share their live location (Telegram location pin or browser geolocation) first. "
        "If 'get_attendance_today' returns an anomaly (like missing yesterday logout), PROACTIVELY inform the user and suggest they correct it.\n"
        "3. Leaves & Strict Apply Flow: To check balances, use 'get_leave_balances'. To list available leave types, use 'get_leave_types'. "
        "If the user wants to apply for leave, you MUST collect all required details before calling 'apply_for_leave': leave type, exact start date, exact end date, whether it is full day or half day when the leave is for a single day, and a reason from the user. "
        "If any required detail is missing, ask a concise follow-up question and DO NOT call 'apply_for_leave' yet. "
        "You MUST NOT invent, assume, or auto-fill a leave reason. "
        "You SHOULD infer duration from the dates only after dates are known, but for a same-day leave you must clarify whether it is full day, first half, or second half if the user did not specify. "
        "When the user provides dates for a leave request, call 'check_team_availability' before submission and summarize the result to the user. "
        "AVAILABILITY REPORTING: When reporting team availability, ALWAYS use an [INSIGHT_CARD] with 'topic: Team Availability'. Include whether colleagues are already on leave and whether coverage looks clear or busy. "
        "SUBMISSION RULE: Only submit the leave after required details are present and you have reported team availability. Once everything is complete, tell the user you are submitting it now, then call 'apply_for_leave'. "
        "LEAVE MANAGEMENT: If the user wants to cancel a leave, use 'list_pending_leaves' first to show them their pending requests with PENDING_LEAVE_CARDs, then use 'cancel_leave' with the specific ID they choose.\n"
        "4. Payslip / Salary: If the user asks for their payslip, salary, net pay, deductions, or last month payroll, you MUST call 'get_latest_payslip' and present the [PAYROLL_CARD] it returns. "
        "Do NOT invent payslip numbers. Do NOT substitute attendance trends, monthly team summaries, or leave balances for a payslip request.\n"
        "5. Team Analytics: If the user (Admin/Manager) asks about organization status or trends, use 'get_team_stats'. This tool now also identifies employees with low attendance.\n"
        "REPORTS: If a manager asks for a report or summary for a specific month (e.g., 'Give me the February report'), use 'generate_monthly_summary'. Use the result to present an [INSIGHT_CARD].\n"
        "6. Leave Recommendations: If the user asks for advice on when to take a leave, or if they have a high leave balance, use 'suggest_leave_window'.\n"
        "7. Attendance Trends & Anomalies: Use 'get_attendance_trends' to detect patterns in user attendance (laters, missing checkouts, or drop in rate).\n"

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
    )

    payslip_ctx = state.get("payslip_context")
    if payslip_ctx:
        prompt += (
            f"\n\n--- PAYSLIP CONTEXT ---\n"
            f"The user is currently viewing the following payslip. Answer any questions about their salary, "
            f"deductions, or LOP based ONLY on this data:\n{payslip_ctx}"
        )

    return prompt


# ---------------------------------------------------------------------------
# Graph Builder (async, MCP-aware)
# ---------------------------------------------------------------------------
async def build_graph(organization_id: int):
    """
    Builds a compiled LangGraph workflow.
    Attempts to load tools from the MCP server first; falls back to legacy tools.
    Returns (compiled_app, mcp_client_or_None).
    """
    mcp_client = None
    tools = []

    if MCP_ENABLED:
        tools, mcp_client = await _get_mcp_tools()

    if not tools:
        tools = _get_legacy_tools()
        logger.info("[Graph] Using legacy LangChain tools.")

    tool_node = ToolNode(tools)
    from asgiref.sync import sync_to_async
    llm_base = await sync_to_async(get_llm)(organization_id)
    llm = llm_base.bind_tools(tools)

    def call_model(state: AgentState):
        system_prompt = _build_system_prompt(state)
        messages = state["messages"]
        response = llm.invoke([SystemMessage(content=system_prompt)] + list(messages))
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
    tools = _get_legacy_tools()
    tool_node = ToolNode(tools)

    def call_model(state: AgentState):
        from .tools import (
            get_leave_balances, apply_for_leave, get_attendance_today,
            search_policies, get_leave_types, mark_attendance,
            check_team_availability, get_team_stats, list_pending_leaves,
            cancel_leave, suggest_leave_window, get_attendance_trends,
            generate_monthly_summary, get_latest_payslip,
        )
        org_id = state.get("organization_id", 0)
        llm = get_llm(org_id).bind_tools(tools)
        system_prompt = _build_system_prompt(state)
        messages = state["messages"]
        response = llm.invoke([SystemMessage(content=system_prompt)] + list(messages))
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
    return workflow.compile()


# Lazy-initialized legacy fallback (only used if views.py imports `app` directly)
app = _build_legacy_app()