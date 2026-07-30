@echo off
REM Start Teamzen MCP servers (Windows)
REM Facade :8001 | attendance :8002 | leaves :8003 | payroll :8004 | policy :8005
setlocal
cd /d "%~dp0.."

if "%MCP_AUTH_REQUIRED%"=="" set MCP_AUTH_REQUIRED=false
if "%MCP_INTERNAL_SECRET%"=="" set MCP_INTERNAL_SECRET=dev-internal-secret

start "teamzen-hr" cmd /k python mcp_servers/teamzen_server.py
start "teamzen-attendance" cmd /k python mcp_servers/attendance_server.py
start "teamzen-leaves" cmd /k python mcp_servers/leave_server.py
start "teamzen-payroll" cmd /k python mcp_servers/payroll_server.py
start "teamzen-policy" cmd /k python mcp_servers/policy_server.py

echo Started 5 MCP server windows.
echo Facade: http://localhost:8001/mcp
echo Set MCP_INTERNAL_SECRET=%MCP_INTERNAL_SECRET% on Django for LangGraph.
endlocal
