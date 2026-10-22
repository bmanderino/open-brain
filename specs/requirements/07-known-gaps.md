# 07 — Known Gaps, Discrepancies, and Proposed Work

Findings from the retroactive review. Priorities: **P1** correctness/security, **P2** quality, **P3** nice to have.

## Bugs and Discrepancies

| ID | Pri | Finding | Evidence | Proposed fix |
|----|-----|---------|----------|--------------|
| GAP-001 | P1 | ~~`/entries` "recent" is wrong beyond `limit` entries: Qdrant scroll returns in point-id order, then the page is sorted by `created_at`.~~ **Resolved:** `created_at` has a datetime payload index and `/entries` uses `order_by` descending. | `main.py` `list_entries` | Done. |
| GAP-002 | P1 | ~~`offset` is an integer passed as Qdrant scroll `offset` (expects a point id/cursor); paging doesn't work.~~ **Resolved:** the integer `offset` is replaced by a `before` timestamp param; responses include `next_before`. | `main.py` `list_entries` | Done. |
| GAP-003 | P1 | ~~CORS `*` + all-interface ports~~ **Resolved:** CORS restricted to `CORS_ORIGINS` (default the web UI origins), methods/headers narrowed, and all published ports bound to `127.0.0.1`. Still no authentication (see FEAT-007). | `main.py` CORS; compose ports | Done; optional API key remains. |
| GAP-004 | P2 | ~~README says MCP config `"type": "sse"`; server runs `streamable-http`.~~ **Resolved:** README now uses `"type": "http"`. | README step 4 vs `mcp.run(transport="streamable-http")` | Update README to `"type": "http"`. |
| GAP-005 | P2 | ~~Compose points the API at `host.docker.internal` while also running an Ollama container; the README says OLLAMA is part of the stack on `brain-net`.~~ **Resolved:** README documents host Ollama as default and the container as an opt-in; container port no longer published. | `docker-compose.yml` (uncommitted diff) | Pick one default; document the other as an override (e.g., compose override file / env var). |
| GAP-006 | P2 | ~~NVIDIA `deploy` block removed in working tree but README says GPU is pre-configured.~~ **Resolved:** README documents the NVIDIA `deploy` block as an opt-in snippet. | `git diff docker-compose.yml` | Use a `docker-compose.nvidia.yml` override and update README. |
| GAP-007 | P2 | ~~README/compose call MCP server "Node.js"; it's Python.~~ **Resolved:** README and compose comment corrected. | compose comment | Fix comment. |
| GAP-008 | P2 | ~~README setup omits pulling `llama3.2`; without it metadata extraction silently falls back to `other`.~~ **Resolved:** README now documents pulling `llama3.2` and the fallback behavior. | README step 3 | Add pull step; surface extraction failure (flag in response). |
| GAP-009 | P2 | `DELETE` returns 200 for missing ids and 500 for malformed ids; UI deletes without confirmation or error handling. **API half resolved:** DELETE now returns 404 for missing and 422 for malformed ids; the UI still deletes without confirmation or error handling. | `delete_entry`, `deleteEntry` | Validate id, return 404, add confirm + error toast. |
| GAP-010 | P2 | Web UI and API swallow errors (all ingest errors say "could not reach Brain API"; search errors appear as "no results"). | `App.jsx` | Distinguish network/HTTP/empty states. |
| GAP-011 | P2 | `/health` does not check Qdrant or Ollama. | `main.py` | Add dependency probes. |
| GAP-012 | P2 | `limit` unvalidated on `/search` (`/entries` is now validated, 1–100). | `main.py` | Pydantic `Field(ge=1, le=100)`. |
| GAP-013 | P3 | Deprecated APIs: `@app.on_event("startup")` (FastAPI lifespan), `qdrant.search` (use `query_points`). **Partly resolved:** `qdrant.search` replaced by `query_points`; `on_event` remains. | `main.py` | Migrate `on_event` to lifespan. |
| GAP-014 | P3 | ~~Mutable default args (`tags: list[str] = []`) in MCP tool signatures.~~ **Resolved** | `mcp-server.py` | Done. |
| GAP-015 | P3 | ~~`ingest` returns `req.tags` that may be `None` if client sends `null`; typed `list[str]`.~~ **Resolved** | `main.py` | Done. |
| GAP-016 | P3 | Inconsistent response shapes (`metadata` nested vs flat). | See DATA-010 | Unify under `metadata`. |
| GAP-017 | P3 | Non-standard fixed fonts referenced but may not be loaded; no responsive layout. | `App.jsx` CSS | Verify `index.html` font links; add breakpoints. |
| GAP-018 | P3 | No tests, CI, or lint. | repo | Add pytest for API (mock Ollama/Qdrant) and a smoke test script. |

## Candidate Features (not committed)

| ID | Feature | Rationale |
|----|---------|-----------|
| FEAT-001 | ~~Edit entries / re-run metadata~~ **Done** via `PATCH /entries/{id}` and the `update_brain_entry` MCP tool (UI editing and hand-editing of metadata remain) | Fix bad LLM labels without delete + re-add. Entries with `metadata_status: failed` are the first candidates for a re-extract |
| FEAT-002 | Search filters (type, tag, source, person, date) in API, UI, and MCP | **Partly done:** API and MCP support project/type/tag/source/date filters; person/topic filters and UI controls remain |
| FEAT-003 | Stats panel in web UI | `/stats` is only exposed to MCP today |
| FEAT-004 | ~~Hybrid search (BM25 + vector)~~ **Done** (RRF of vector ranking and API-side BM25 over a full-text index) | Better recall for exact terms and names |
| FEAT-005 | Chunking for long content | Embedding model context limit |
| FEAT-006 | Export / import / backup | Data ownership; currently only Docker volume snapshots |
| FEAT-007 | Optional API key / auth | Needed for any non-local use |
| FEAT-008 | Action-item view across all entries | Metadata already captured, not surfaced as a task list |
| FEAT-009 | ~~MCP `source`/project namespace per project~~ **Done** (optional `project` field, unscoped entries included in project searches) | Avoid cross-project context bleed in Claude Code |
