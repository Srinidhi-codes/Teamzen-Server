"""
Teamzen Combined MCP Server
============================
Exposes all HR tools (attendance, leaves, HR analytics, policy search)
as a single MCP server using streamable HTTP transport.

Run:
    python mcp_servers/teamzen_server.py

The server listens on http://0.0.0.0:8001/mcp by default.
The PORT can be overridden via the MCP_SERVER_PORT environment variable.
"""

import sys
import os

# Bootstrap Django before anything else imports models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django
bootstrap_django()

import asyncio
import json
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Instantiate the FastMCP server
# host/port/streamable_http_path are constructor args in mcp >= 1.3
# ---------------------------------------------------------------------------
port = int(os.environ.get("MCP_SERVER_PORT", 8001))

mcp = FastMCP(
    name="teamzen-hr",
    instructions=(
        "You are the Teamzen HR tool server. "
        "Use these tools to look up attendance, leaves, team stats, and policies "
        "on behalf of authenticated employees and managers."
    ),
    host="0.0.0.0",
    port=port,
    streamable_http_path="/mcp",
)

# ===========================================================================
# ATTENDANCE TOOLS
# ===========================================================================

@mcp.tool()
def get_attendance_today(user_id: int) -> dict:
    """
    Checks the user's attendance record for today.
    Returns check-in/out times, current status, and flags missing logouts from yesterday.
    """
    from ai_engine.tools import get_attendance_today as _tool
    return _tool.invoke({"user_id": user_id})


@mcp.tool()
def mark_attendance(
    user_id: int,
    action: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> str:
    """
    Marks attendance (check-in or check-out) for the user.
    action must be 'check-in' or 'check-out'.
    latitude and longitude are required for geofence verification.
    """
    from ai_engine.tools import mark_attendance as _tool
    return _tool.invoke({
        "user_id": user_id,
        "action": action,
        "latitude": latitude,
        "longitude": longitude,
    })


@mcp.tool()
def get_attendance_trends(user_id: int, days: int = 30) -> str:
    """
    Analyzes historical attendance data to detect anomalies and trends.
    Detects repeated late arrivals, missing checkouts, and rate drops.
    Returns findings as an INSIGHT_CARD string.
    days: number of past days to analyse (default 30).
    """
    from ai_engine.tools import get_attendance_trends as _tool
    return _tool.invoke({"user_id": user_id, "days": days})


# ===========================================================================
# LEAVE TOOLS
# ===========================================================================

@mcp.tool()
def get_leave_balances(user_id: int) -> list:
    """
    Fetches the current leave balances for the given user for the current year.
    Returns a list of leave types with entitled, used, and available days.
    """
    from ai_engine.tools import get_leave_balances as _tool
    return _tool.invoke({"user_id": user_id})


@mcp.tool()
def get_leave_types(organization_id: int) -> list:
    """
    Lists all active leave types available in the organization.
    Useful before applying for leave to get valid leave_type_id values.
    """
    from ai_engine.tools import get_leave_types as _tool
    return _tool.invoke({"organization_id": organization_id})


@mcp.tool()
def apply_for_leave(
    user_id: int,
    leave_type_id: int,
    from_date_str: str,
    to_date_str: str,
    reason: str,
    half_day_period: str = "full_day",
) -> dict:
    """
    Submits a new leave request for the user.
    from_date_str and to_date_str must be in 'YYYY-MM-DD' format.
    half_day_period must be full_day, first_half, or second_half.
    Returns a success dict with request_id or an ERROR_CARD string on failure.
    """
    from ai_engine.tools import apply_for_leave as _tool
    return _tool.invoke({
        "user_id": user_id,
        "leave_type_id": leave_type_id,
        "from_date_str": from_date_str,
        "to_date_str": to_date_str,
        "reason": reason,
        "half_day_period": half_day_period,
    })


@mcp.tool()
def list_pending_leaves(user_id: int) -> list:
    """
    Lists all pending leave requests for the user.
    Required before cancelling a leave to get the correct request ID.
    """
    from ai_engine.tools import list_pending_leaves as _tool
    return _tool.invoke({"user_id": user_id})


@mcp.tool()
def cancel_leave(user_id: int, request_id: int) -> dict:
    """
    Cancels a pending or approved leave request by its ID.
    Can only cancel requests belonging to the given user.
    """
    from ai_engine.tools import cancel_leave as _tool
    return _tool.invoke({"user_id": user_id, "request_id": request_id})


@mcp.tool()
def check_team_availability(
    user_id: int,
    start_date_str: str,
    end_date_str: str,
) -> dict:
    """
    Checks how many colleagues in the user's department are on leave during a date range.
    start_date_str and end_date_str must be in 'YYYY-MM-DD' format.
    Helps the AI advise on whether it's a good time to apply for leave.
    """
    from ai_engine.tools import check_team_availability as _tool
    return _tool.invoke({
        "user_id": user_id,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
    })


@mcp.tool()
def suggest_leave_window(user_id: int, month: Optional[int] = None) -> str:
    """
    Analyses and suggests the best time for the user to take leave in a given month.
    Factors in leave balance, team availability, company holidays, and user history.
    month: 1–12. Defaults to the current month if not provided.
    Returns an INSIGHT_CARD string with the recommendation.
    """
    from ai_engine.tools import suggest_leave_window as _tool
    params = {"user_id": user_id}
    if month is not None:
        params["month"] = month
    return _tool.invoke(params)


# ===========================================================================
# HR / ANALYTICS TOOLS
# ===========================================================================

@mcp.tool()
def get_team_stats(organization_id: int) -> dict:
    """
    Fetches high-level attendance and leave stats for the whole organization.
    Returns headcount, present today, on-leave count, and low-attendance alerts.
    Useful for managers and admins.
    """
    from ai_engine.tools import get_team_stats as _tool
    return _tool.invoke({"organization_id": organization_id})


@mcp.tool()
def generate_monthly_summary(organization_id: int, month: int, year: int) -> dict:
    """
    Generates an executive summary of an organization's HR performance for a month.
    Aggregates attendance rates, leave trends, and departmental activity.
    Returns an AI-written professional paragraph plus raw stats.
    Only meaningful for managers and admins.
    month: 1–12, year: e.g. 2026.
    """
    from ai_engine.tools import generate_monthly_summary as _tool
    return _tool.invoke({
        "organization_id": organization_id,
        "month": month,
        "year": year,
    })


# ===========================================================================
# POLICY TOOLS
# ===========================================================================

@mcp.tool()
def search_policies(query: str, organization_id: int) -> str:
    """
    Searches company policy documents using semantic similarity (RAG / pgvector).
    Use when the user asks about rules, policies, or handbook information.
    Returns the most relevant policy excerpts as a combined string.
    """
    from ai_engine.tools import search_policies as _tool
    return _tool.invoke({"query": query, "organization_id": organization_id})


# ===========================================================================
# Entry Point
# ===========================================================================

if __name__ == "__main__":
    print(f"[Teamzen MCP] Starting combined HR tool server on port {port}...")
    mcp.run(transport="streamable-http")
