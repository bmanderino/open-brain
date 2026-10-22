# 03 — MCP Integration

**Implementation:** `mcp-server/mcp-server.py` using `mcp.server.fastmcp.FastMCP("open-brain")`, transport `streamable-http`, listening on `0.0.0.0:$PORT` (default 3000; published as host port 3001). The server is a thin proxy to the Brain API at `BRAIN_API_URL` (default `http://brain-api:8000`) and holds no state.

## 1. Server

| ID | Requirement | Status |
|----|-------------|--------|
| MCP-001 | The server MUST expose the MCP endpoint at `http://localhost:3001/mcp`. | ✅ |
| MCP-002 | The server MUST use the streamable-http transport. | ✅ |
| MCP-003 | Tool failures from the Brain API (non-200) MUST be returned as human-readable error strings (`"Error …: <body>"`) rather than raising. | ✅ |
| MCP-004 | Network-level errors (connection refused, timeout) are not caught and propagate as MCP tool errors. They SHOULD be caught and reported as strings. | ⚠️ |
| MCP-005 | The server MUST NOT expose delete or update operations. | ✅ |
| MCP-006 | The server has no authentication; any process able to reach port 3001 can read/write the brain. | ⚠️ |

## 2. Tools

### `search_brain(query, limit=5, project=None, type=None, tag=None, source=None) -> str`
- MCP-010: Calls `POST /search` (30 s timeout).
- MCP-011: Returns `"No results found for: '<query>'"` on empty results.
- MCP-012: Otherwise returns a numbered text list: score (3 dp), date (YYYY-MM-DD), source, project (when set), tags, content, then `type` (omitted if `other`), `topics`, `people`, `actions` lines when present.
- MCP-013: Exposes `project`, `type`, `tag`, and `source` filters (`source` maps to the API's `source_filter`). The docstring tells the model that `project` also returns unscoped entries.

### `add_to_brain(content, tags=None, project=None) -> str`
- MCP-020: Calls `POST /ingest` with `source="mcp"` (60 s timeout to allow for LLM extraction).
- MCP-021: Returns a confirmation containing the new id, the stored content, tags, project (when set), and extracted type/topics/people/action items when present.
- MCP-023: The docstring tells the model to pass `project` (the current repo name) for project-specific content and omit it for general knowledge.
- MCP-022: The tool description SHOULD steer the model to use this tool for the brain (not its own memory); README notes users must be explicit.

### `list_brain(limit=10, project=None, type=None, tag=None) -> str`
- MCP-030: Calls `GET /entries` with `limit` and any filters.
- MCP-031: Returns `"Your brain is empty. Add something with add_to_brain!"` when empty.
- MCP-032: Output shows date, source, project (when set), tags, content, type, topics, people (action items are omitted, unlike search).
- MCP-033: Returns the true newest entries (LIST-006 fixed).

### `brain_stats() -> str`
- MCP-040: Calls `GET /stats`.
- MCP-041: Returns total plus sections "By source" (sorted desc), "Top topics", "Top people mentioned".

## 3. Client Configuration

| ID | Requirement | Status |
|----|-------------|--------|
| MCP-050 | README documents adding the server to `~/.claude.json` under `mcpServers.open-brain` with `url: http://localhost:3001/mcp`. | ✅ |
| MCP-051 | README documents `"type": "http"`, matching the `streamable-http` server. | ✅ |
| MCP-052 | Docs correctly describe the server as Python. | ✅ |
