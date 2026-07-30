"""Teamzen Payroll MCP server — port 8004 by default."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django, create_mcp, run_mcp

bootstrap_django()

from mcp_servers.tool_registry import register_payroll_tools, register_hr_tools

port = int(os.environ.get("MCP_PAYROLL_PORT", os.environ.get("MCP_SERVER_PORT", 8004)))
mcp = create_mcp(
    name="teamzen-payroll",
    instructions="Teamzen payroll tools: payslips, forecasts, anomalies, and org HR stats.",
    port=port,
)
register_payroll_tools(mcp)
register_hr_tools(mcp)

if __name__ == "__main__":
    run_mcp(mcp, server_name="teamzen-payroll")
