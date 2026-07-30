# Teamzen MCP Sign-in (Sequence 5.1)

Connect Cursor / Claude to Teamzen by signing in with your Teamzen account
(email/password or OTP). Issues a **user-bound** `tzm_…` token so MCP tools
run as that user.

## Quick start

### A) Manual browser

1. Start Django (`runserver` / daphne) and MCP (`python mcp_servers/teamzen_server.py`)
2. Open http://localhost:8000/mcp/connect/
3. Sign in → Approve scopes → copy the token into Cursor `mcp.json`

### B) Device flow

```bash
cd backend
python mcp_oauth/device_login.py
# open the printed URL, sign in, approve — script prints access_token
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mcp/oauth/device/code` | Start device grant |
| POST | `/mcp/oauth/token` | Poll device / exchange auth code |
| GET | `/mcp/oauth/authorize` | Browser auth-code start |
| GET | `/mcp/connect/` | Manual connect portal |
| GET | `/mcp/connect/device/` | Enter user code |

## Cursor config

```json
{
  "mcpServers": {
    "teamzen-hr": {
      "url": "http://localhost:8001/mcp",
      "headers": {
        "Authorization": "Bearer tzm_YOUR_TOKEN"
      }
    }
  }
}
```
