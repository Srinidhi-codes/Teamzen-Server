# ai_engine

LangGraph agent, hybrid RAG, REST chat stream, policy ingest, org LLM config.

**Learn:** [11 Prompts](../../docs/backend/11-prompt-engineering.md) · [12 RAG](../../docs/backend/12-rag.md) · [13 LangGraph](../../docs/backend/13-langgraph-agent.md) · [15 Guardrails](../../docs/backend/15-guardrails.md)

| File | Role |
|------|------|
| `views.py` | `POST /api/ai/chat/` |
| `graph.py` | Agent graph + system prompt |
| `retrieval.py` | Vector + FTS + RRF |
| `tools.py` | LangChain/MCP implementations |
| `guardrails.py` | Jailbreak regex |
| `actor_context.py` | Trusted identity for tools |
