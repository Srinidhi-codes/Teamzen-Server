"""Teamzen Attendance MCP server — port 8002 by default."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django, create_mcp, run_mcp

bootstrap_django()

from mcp_servers.tool_registry import register_attendance_tools

port = int(os.environ.get("MCP_ATTENDANCE_PORT", os.environ.get("MCP_SERVER_PORT", 8002)))
mcp = create_mcp(
    name="teamzen-attendance",
    instructions="Teamzen attendance tools: check-in/out, trends, corrections, team pulse.",
    port=port,
)
register_attendance_tools(mcp)

if __name__ == "__main__":
    run_mcp(mcp, server_name="teamzen-attendance")
