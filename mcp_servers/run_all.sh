#!/usr/bin/env bash
# Start all Teamzen MCP servers (Unix)
# Facade :8001 | attendance :8002 | leaves :8003 | payroll :8004 | policy :8005
set -e
cd "$(dirname "$0")/.."

export MCP_AUTH_REQUIRED="${MCP_AUTH_REQUIRED:-false}"
export MCP_INTERNAL_SECRET="${MCP_INTERNAL_SECRET:-dev-internal-secret}"

python mcp_servers/teamzen_server.py &
python mcp_servers/attendance_server.py &
python mcp_servers/leave_server.py &
python mcp_servers/payroll_server.py &
python mcp_servers/policy_server.py &

echo "Started MCP servers (PIDs $! ...)"
echo "Facade: http://localhost:8001/mcp"
echo "Set MCP_INTERNAL_SECRET=$MCP_INTERNAL_SECRET on Django for LangGraph"
wait
