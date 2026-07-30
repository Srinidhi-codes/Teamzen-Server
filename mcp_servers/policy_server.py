"""Teamzen Policy MCP server — port 8005 by default."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_servers.shared import bootstrap_django, create_mcp, run_mcp

bootstrap_django()

from mcp_servers.tool_registry import register_policy_tools

port = int(os.environ.get("MCP_POLICY_PORT", os.environ.get("MCP_SERVER_PORT", 8005)))
mcp = create_mcp(
    name="teamzen-policy",
    instructions="Teamzen policy tools: hybrid RAG search over uploaded handbooks.",
    port=port,
)
register_policy_tools(mcp)

if __name__ == "__main__":
    run_mcp(mcp, server_name="teamzen-policy")
