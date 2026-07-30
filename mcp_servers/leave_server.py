"""Teamzen Leaves MCP server — port 8003 by default."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django, create_mcp, run_mcp

bootstrap_django()

from mcp_servers.tool_registry import register_leave_tools

port = int(os.environ.get("MCP_LEAVES_PORT", os.environ.get("MCP_SERVER_PORT", 8003)))
mcp = create_mcp(
    name="teamzen-leaves",
    instructions="Teamzen leave tools: balances, apply/cancel, team availability, suggestions.",
    port=port,
)
register_leave_tools(mcp)

if __name__ == "__main__":
    run_mcp(mcp, server_name="teamzen-leaves")
