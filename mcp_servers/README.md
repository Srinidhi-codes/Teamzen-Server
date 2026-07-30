# Teamzen MCP Servers (Sequence 5 + 5.1 Sign-in)
#
# Ports:
#   teamzen-hr (facade)  8001  — used by LangGraph by default
#   attendance           8002
#   leaves               8003
#   payroll              8004
#   policy               8005
#
# Sign in with Teamzen (recommended for Cursor):
#   Browser:  http://localhost:8000/mcp/connect/
#   Device:   python mcp_oauth/device_login.py
#   See mcp_oauth/README.md for OAuth endpoints.
#
# Auth / identity:
#   MCP_AUTH_REQUIRED=false          — open (local default; no trusted user)
#   MCP_INTERNAL_SECRET=<secret>     — LangGraph sends this + X-MCP-User-Id / Org-Id
#   Authorization: Bearer tzm_…      — user-bound token from Sign-in flow
#   Authorization: Bearer <JWT>      — SimpleJWT access → that logged-in user
#
# Tool args user_id / organization_id / approver_id are OVERWRITTEN from auth.
#
# Create a CI token (optional):
#   python manage.py create_mcp_token --org 1 --user 5 --name CI \
#     --scopes attendance:read,leaves:read,payroll:read,policy:read,hr:read
#
# Django (LangGraph) env:
#   MCP_SERVER_URL=http://localhost:8001/mcp
#   MCP_INTERNAL_SECRET=dev-internal-secret
#   MCP_MULTI_SERVER=false
#
# MCP process env (match Django secret):
#   MCP_INTERNAL_SECRET=dev-internal-secret
#   MCP_AUTH_REQUIRED=false   # or true in production
