"""
Teamzen Combined MCP Server (LangGraph facade)
==============================================
Exposes all HR tools on a single streamable-HTTP endpoint.

Run:
    python mcp_servers/teamzen_server.py

Default: http://0.0.0.0:8001/mcp
Override with MCP_SERVER_PORT. Auth via X-MCP-Internal-Secret or Bearer token
(or MCP_AUTH_REQUIRED=false for open local dev).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django, create_mcp, run_mcp

bootstrap_django()

from mcp_servers.tool_registry import register_all_tools

port = int(os.environ.get("MCP_SERVER_PORT", 8001))
mcp = create_mcp(
    name="teamzen-hr",
    instructions=(
        "You are the Teamzen HR tool server. "
        "Use these tools to look up attendance, leaves, team stats, payroll, and policies "
        "on behalf of authenticated employees and managers."
    ),
    port=port,
)
register_all_tools(mcp)

if __name__ == "__main__":
    run_mcp(mcp, server_name="teamzen-hr")
