# 03 — MCP Integration

**Implementation:** `mcp-server/mcp-server.py` using `mcp.server.fastmcp.FastMCP("open-brain")`, transport `streamable-http`, listening on `0.0.0.0:$PORT` (default 3000; published as host port 3001). The server is a thin proxy to the Brain API at `BRAIN_API_URL` (default `http://brain-api:8000`) and holds no state.

## 1. Server

| ID | Requirement | Status |
|----|-------------|--------|
| MCP-001 | The server MUST expose the MCP endpoint at `http://localhost:3001/mcp`. | ✅ |
| MCP-002 | The server MUST use the streamable-http transport. | ✅ |
| MCP-003 | Tool failures from the Brain API (non-200) MUST be returned as human-readable error strings (`"Error …: <body>"`) rather than raising. | ✅ |
| MCP-004 | Network-level errors (connection refused, timeout) are not caught and propagate as MCP tool errors. They SHOULD be caught and reported as strings. | ⚠️ |
| MCP-005 | The server MUST NOT expose a delete operation. It exposes `update_brain_entry` for edits. | ✅ |
| MCP-006 | The server has no authentication; any process able to reach port 3001 can read/write the brain. | ⚠️ |

## 2. Tools

### `search_brain(query, limit=5, project=None, type=None, tag=None, source=None) -> str`
- MCP-010: Calls `POST /search` (30 s timeout).
- MCP-011: Returns `"No results found for: '<query>'"` on empty results.
- MCP-012: Otherwise returns a numbered text list: score (3 dp), date (YYYY-MM-DD), source, project (when set), tags, content, then `type` (omitted if `other`), `topics`, `people`, `actions` lines when present.
- MCP-014: Search is hybrid; results found through exact-term matching are labeled `exact-term match` in the output, and the docstring says names, identifiers and error strings are matched.
- MCP-013: Exposes `project`, `type`, `tag`, and `source` filters (`source` maps to the API's `source_filter`). The docstring tells the model that `project` also returns unscoped entries.

### `add_to_brain(content, tags=None, project=None, pinned=False, force=False) -> str`
- MCP-020: Calls `POST /ingest` with `source="mcp"` (60 s timeout to allow for LLM extraction).
- MCP-021: Returns a confirmation containing the new id, the stored content, tags, project (when set), and extracted type/topics/people/action items when present.
- MCP-025: When the API reports `metadata_status: "failed"`, the tool MUST append a note that extraction failed and the metadata fields are empty.
- MCP-024: When the API reports `duplicate_of`, the tool MUST say nothing was stored, show the existing entry's id, similarity and content, and mention `force=True`. The docstring explains this to the model.
- MCP-023: The docstring tells the model to pass `project` (the current repo name) for project-specific content and omit it for general knowledge.
- MCP-026: `pinned` is sent only when true. The docstring tells the model to pin only short, lasting facts every future session should see, and to keep pins few. A confirmation says `Pinned: yes`. When a duplicate was skipped and the caller asked to pin, the message suggests `update_brain_entry(pinned=True)` on the existing entry.
- MCP-022: The tool description SHOULD steer the model to use this tool for the brain (not its own memory); README notes users must be explicit.

### `update_brain_entry(entry_id, content=None, tags=None, project=None, pinned=None, reextract=False, type=None, topics=None, people=None, action_items=None) -> str`
- MCP-060: Calls `PATCH /entries/{id}` (90 s timeout, since changed content re-runs the LLM).
- MCP-061: Returns the updated entry's content, project, tags, and metadata; `"No entry with id <id>"` on 404; a note when metadata extraction failed.
- MCP-062: `search_brain` and `list_brain` output includes each entry's id in brackets so it can be passed here.
- MCP-063: The docstring states that only passed fields change, that `tags` replaces all tags, and that `project=""` removes the project, and that `type`, `topics`, `people`, and `action_items` correct the extracted metadata by hand (lists replace, `[]` clears; edited entries become `metadata_status: "manual"`).
- MCP-065: `pinned` is sent only when given, so `False` unpins and `None` leaves the pin alone. The output includes `Pinned: yes` for pinned entries.
- MCP-064: Metadata arguments that are `None` are not sent; an empty list is sent so it can clear a field. Validation errors from the API (e.g. an invalid `type`) are returned as `Error updating entry: ...`.

### `list_brain(limit=10, project=None, type=None, tag=None, pinned=False) -> str`
- MCP-030: Calls `GET /entries` with `limit` and any filters.
- MCP-031: Returns `"Your brain is empty. Add something with add_to_brain!"` when empty.
- MCP-032: Output shows date, source, project (when set), tags, content, type, topics, people (action items are omitted, unlike search).
- MCP-033: Returns the true newest entries (LIST-006 fixed).
- MCP-034: `pinned=True` lists only pinned entries. Pinned entries are marked `| pinned` in `list_brain` and `search_brain` output.

### `get_context(project=None, recent=5) -> str`
- MCP-070: Calls `GET /context?format=text` (30 s timeout) and returns the API's text unchanged (CTX-004).
- MCP-071: `project` is sent only when given. Without it the API returns only unscoped entries.
- MCP-072: The docstring tells the model to call this at the start of a session or task with the current repo name as `project`, that it is compact on purpose, and to use `search_brain` to dig deeper.
- MCP-073: A non-200 reply is returned as `"Error fetching context: <body>"`.

### `brain_stats() -> str`
- MCP-040: Calls `GET /stats`.
- MCP-041: Returns total plus sections "By source" (sorted desc), "Top topics", "Top people mentioned".

## 3. Client Configuration

| ID | Requirement | Status |
|----|-------------|--------|
| MCP-050 | README documents adding the server to `~/.claude.json` under `mcpServers.open-brain` with `url: http://localhost:3001/mcp`. | ✅ |
| MCP-051 | README documents `"type": "http"`, matching the `streamable-http` server. | ✅ |
| MCP-052 | Docs correctly describe the server as Python. | ✅ |
