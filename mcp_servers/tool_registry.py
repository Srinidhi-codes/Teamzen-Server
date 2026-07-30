"""
Shared tool registration for Teamzen MCP servers.
Each register_* function attaches thin wrappers onto a FastMCP instance.
"""
from __future__ import annotations

from typing import Optional

from mcp_servers.shared import invoke_tool


def register_attendance_tools(mcp) -> None:
    @mcp.tool()
    def get_attendance_today(user_id: int) -> dict:
        """
        Checks the user's attendance record for today.
        Returns check-in/out times, current status, and flags missing logouts from yesterday.
        """
        from ai_engine.tools import get_attendance_today as _tool
        return invoke_tool(_tool, {"user_id": user_id}, required_scope="attendance:read")

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
        return invoke_tool(
            _tool,
            {
                "user_id": user_id,
                "action": action,
                "latitude": latitude,
                "longitude": longitude,
            },
            required_scope="attendance:write",
        )

    @mcp.tool()
    def get_attendance_trends(user_id: int, days: int = 30) -> str:
        """
        Analyzes historical attendance data to detect anomalies and trends.
        Detects repeated late arrivals, missing checkouts, and rate drops.
        Returns findings as an INSIGHT_CARD string.
        days: number of past days to analyse (default 30).
        """
        from ai_engine.tools import get_attendance_trends as _tool
        return invoke_tool(
            _tool, {"user_id": user_id, "days": days}, required_scope="attendance:read"
        )

    @mcp.tool()
    def get_team_pulse(organization_id: int, user_id: int = None) -> str:
        """Team Pulse brief: prior-week attendance, pending leaves, late offenders."""
        from ai_engine.tools import get_team_pulse as _tool
        payload = {"organization_id": organization_id}
        if user_id is not None:
            payload["user_id"] = user_id
        return invoke_tool(_tool, payload, required_scope="hr:read")

    @mcp.tool()
    def list_pending_corrections(user_id: int) -> str:
        """List pending attendance corrections with CORRECTION_CARD tags."""
        from ai_engine.tools import list_pending_corrections as _tool
        return invoke_tool(_tool, {"user_id": user_id}, required_scope="attendance:read")

    @mcp.tool()
    def confirm_attendance_correction(
        user_id: int, correction_id: int, logout_time: str = None
    ) -> str:
        """Employee confirms a pending correction (optional logout_time HH:MM)."""
        from ai_engine.tools import confirm_attendance_correction as _tool
        payload = {"user_id": user_id, "correction_id": correction_id}
        if logout_time:
            payload["logout_time"] = logout_time
        return invoke_tool(_tool, payload, required_scope="attendance:write")

    @mcp.tool()
    def review_attendance_correction(
        approver_id: int, correction_id: int, decision: str, comments: str = ""
    ) -> str:
        """Manager/HR approve or reject a pending attendance correction."""
        from ai_engine.tools import review_attendance_correction as _tool
        return invoke_tool(
            _tool,
            {
                "approver_id": approver_id,
                "correction_id": correction_id,
                "decision": decision,
                "comments": comments or "",
            },
            required_scope="attendance:write",
        )


def register_leave_tools(mcp) -> None:
    @mcp.tool()
    def get_leave_balances(user_id: int) -> list:
        """
        Fetches the current leave balances for the given user for the current year.
        Returns a list of leave types with entitled, used, and available days.
        """
        from ai_engine.tools import get_leave_balances as _tool
        return invoke_tool(_tool, {"user_id": user_id}, required_scope="leaves:read")

    @mcp.tool()
    def get_leave_types(organization_id: int) -> list:
        """
        Lists all active leave types available in the organization.
        Useful before applying for leave to get valid leave_type_id values.
        """
        from ai_engine.tools import get_leave_types as _tool
        return invoke_tool(
            _tool, {"organization_id": organization_id}, required_scope="leaves:read"
        )

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
        return invoke_tool(
            _tool,
            {
                "user_id": user_id,
                "leave_type_id": leave_type_id,
                "from_date_str": from_date_str,
                "to_date_str": to_date_str,
                "reason": reason,
                "half_day_period": half_day_period,
            },
            required_scope="leaves:write",
        )

    @mcp.tool()
    def list_pending_leaves(user_id: int) -> list:
        """
        Lists all pending leave requests for the user.
        Required before cancelling a leave to get the correct request ID.
        """
        from ai_engine.tools import list_pending_leaves as _tool
        return invoke_tool(_tool, {"user_id": user_id}, required_scope="leaves:read")

    @mcp.tool()
    def cancel_leave(user_id: int, request_id: int) -> dict:
        """
        Cancels a pending or approved leave request by its ID.
        Can only cancel requests belonging to the given user.
        """
        from ai_engine.tools import cancel_leave as _tool
        return invoke_tool(
            _tool,
            {"user_id": user_id, "request_id": request_id},
            required_scope="leaves:write",
        )

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
        return invoke_tool(
            _tool,
            {
                "user_id": user_id,
                "start_date_str": start_date_str,
                "end_date_str": end_date_str,
            },
            required_scope="leaves:read",
        )

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
        return invoke_tool(_tool, params, required_scope="leaves:read")


def register_hr_tools(mcp) -> None:
    @mcp.tool()
    def get_team_stats(organization_id: int) -> dict:
        """
        Fetches high-level attendance and leave stats for the whole organization.
        Returns headcount, present today, on-leave count, and low-attendance alerts.
        Useful for managers and admins.
        """
        from ai_engine.tools import get_team_stats as _tool
        return invoke_tool(
            _tool, {"organization_id": organization_id}, required_scope="hr:read"
        )

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
        return invoke_tool(
            _tool,
            {"organization_id": organization_id, "month": month, "year": year},
            required_scope="hr:read",
        )


def register_payroll_tools(mcp) -> None:
    @mcp.tool()
    def get_latest_payslip(user_id: int) -> str:
        """
        Returns the user's most recent payslip (gross, net, deductions, components).
        Use for salary / payslip / net pay questions. Do not invent numbers.
        """
        from ai_engine.tools import get_latest_payslip as _tool
        return invoke_tool(_tool, {"user_id": user_id}, required_scope="payroll:read")

    @mcp.tool()
    def get_payslip(user_id: int, month: int, year: int) -> str:
        """Fetch payslip for a specific month (1-12) and year."""
        from ai_engine.tools import get_payslip as _tool
        return invoke_tool(
            _tool,
            {"user_id": user_id, "month": month, "year": year},
            required_scope="payroll:read",
        )

    @mcp.tool()
    def explain_deduction(
        user_id: int,
        month: int = None,
        year: int = None,
        component_name: str = None,
    ) -> str:
        """Explain payslip deductions (PF, PT, LOP, etc.). Optional month/year/component filter."""
        from ai_engine.tools import explain_deduction as _tool
        payload = {"user_id": user_id}
        if month is not None:
            payload["month"] = month
        if year is not None:
            payload["year"] = year
        if component_name:
            payload["component_name"] = component_name
        return invoke_tool(_tool, payload, required_scope="payroll:read")

    @mcp.tool()
    def salary_forecast(
        user_id: int,
        unpaid_days: float,
        month: int = None,
        year: int = None,
    ) -> str:
        """Estimate pay loss for unpaid/LOP days from active CTC. Read-only."""
        from ai_engine.tools import salary_forecast as _tool
        payload = {"user_id": user_id, "unpaid_days": unpaid_days}
        if month is not None:
            payload["month"] = month
        if year is not None:
            payload["year"] = year
        return invoke_tool(_tool, payload, required_scope="payroll:read")

    @mcp.tool()
    def compare_payslips(
        user_id: int,
        month1: int,
        year1: int,
        month2: int,
        year2: int,
    ) -> str:
        """Compare two payslips across months for net/gross/LOP/deduction deltas."""
        from ai_engine.tools import compare_payslips as _tool
        return invoke_tool(
            _tool,
            {
                "user_id": user_id,
                "month1": month1,
                "year1": year1,
                "month2": month2,
                "year2": year2,
            },
            required_scope="payroll:read",
        )

    @mcp.tool()
    def get_payroll_history(user_id: int, limit: int = 6) -> str:
        """List recent payslips (month/year/net/status) for an employee."""
        from ai_engine.tools import get_payroll_history as _tool
        return invoke_tool(
            _tool, {"user_id": user_id, "limit": limit}, required_scope="payroll:read"
        )

    @mcp.tool()
    def check_payroll_anomalies(organization_id: int, month: int, year: int) -> str:
        """Scan a completed payroll run for anomalies (LOP spikes, net pay swings, double deductions, zero net, missing salary structures, new-joiner pro-rata)."""
        from ai_engine.tools import check_payroll_anomalies as _tool
        return invoke_tool(
            _tool,
            {"organization_id": organization_id, "month": month, "year": year},
            required_scope="payroll:read",
        )


def register_policy_tools(mcp) -> None:
    @mcp.tool()
    def search_policies(query: str, organization_id: int) -> str:
        """
        Searches company policy documents using hybrid RAG (vector + full-text).
        Use when the user asks about rules, policies, or handbook information.
        Returns relevant policy excerpts with page numbers for citations.
        """
        from ai_engine.tools import search_policies as _tool
        return invoke_tool(
            _tool,
            {"query": query, "organization_id": organization_id},
            required_scope="policy:read",
        )


def register_all_tools(mcp) -> None:
    register_attendance_tools(mcp)
    register_leave_tools(mcp)
    register_hr_tools(mcp)
    register_payroll_tools(mcp)
    register_policy_tools(mcp)
