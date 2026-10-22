# Next Steps

Prioritized work for Open Brain, based on a code review of `brain-api/main.py`, `mcp-server/mcp-server.py`, and the existing specs. Read this alongside [`requirements/07-known-gaps.md`](requirements/07-known-gaps.md). That file has the full GAP and FEAT lists. This one says what to do first and why.

## Context

Open Brain is a fully local personal knowledge base: FastAPI + Qdrant + Ollama (`nomic-embed-text` for embeddings, `llama3.2` for metadata), a FastMCP server over streamable HTTP, and a React UI. The main consumer is Claude Code via MCP, so MCP behavior matters more than the web UI when deciding priorities.

The local-only, `docker compose up` setup is the main differentiator versus other personal memory projects. Most of them either need a hosted DB (Supabase) or have dropped their local option (Mem0's OpenMemory was sunset in 2026). Don't trade that away. Anything added should run in the existing Compose stack with no new cloud dependency.

Pinned versions to keep in mind: `qdrant-client==1.11.3`, `fastapi==0.115.0`, `mcp[cli]>=1.8.0,<2`. Check that any Qdrant API you use exists in 1.11.x before upgrading anything.

## Priority list

### 1. ~~Fix `GET /entries` ordering and paging (GAP-001, GAP-002)~~ Done

Implemented with a `created_at` datetime index, `order_by` desc, and a `before`/`next_before` cursor. Verified with 55 entries paged 10 at a time.

**Why:** The `list_brain` MCP tool calls this endpoint to show "recent" entries. Right now `list_entries` scrolls `limit` points in Qdrant's internal id order, then sorts that slice by `created_at`. Once the brain has more than `limit` entries, the result is not the most recent entries, it's an arbitrary subset sorted newest-first. The integer `offset` is also passed to `qdrant.scroll`, which expects a point id or cursor, so paging doesn't work.

**Suggested approach:** Create a payload index on `created_at` (datetime type) in the startup hook, idempotently, so existing collections get it too. Then use `scroll` with `order_by` on `created_at` descending. For paging, either return and accept an opaque cursor, or switch to a `before` timestamp param. Keep the response shape the same so the web UI and MCP tool keep working. Verify `order_by` behavior on 1.11.3 before relying on it. If it's a problem, scroll all and sort in memory as a stopgap, since the collection is small.

**Done when:** With 50+ entries, `list_brain(limit=10)` returns the 10 newest, and paging through returns the rest in order with no repeats.

### 2. ~~Project namespace and search filters (FEAT-009, FEAT-002)~~ Done

Implemented: optional `project` field, keyword indexes, shared filter builder for `/search` and `/entries`, MCP exposure, and README docs. Searching with a project also returns unscoped entries (`include_unscoped=false` to opt out). Still open: person/topic filters and web UI filter controls.

**Why:** This is the biggest improvement for real Claude Code use. Every MCP write currently gets `source="mcp"` with nothing identifying the project, so context from different repos mixes together in search results. Claude also can't narrow a search by type, tag, or person even though that metadata is already stored. `source_filter` exists in the API but isn't exposed through MCP.

**Suggested approach:**
- Add an optional `project` field to the payload, with a keyword index. Entries without it should still work (treat as unscoped, not as an error).
- Add optional `project`, `type`, `tag`, `source`, and date-range filters to `/search` and `/entries`, built as a Qdrant `Filter` with `must` conditions.
- Expose `project` (and `type`/`tag` where it's cheap) on the `search_brain`, `add_to_brain`, and `list_brain` MCP tools. Update the tool docstrings, since Claude reads those to decide how to call them. A good default: Claude passes the current repo name as `project` when adding.
- Decide whether search with a `project` set should also include unscoped entries. Probably yes, since general preferences and decisions apply everywhere.

**Done when:** Entries added with `project="foo"` don't show up in searches scoped to `project="bar"`, old entries still work, and the filters are documented in the README.

### 3. ~~Dedup on ingest~~ Done

Implemented with `DEDUP_THRESHOLD` (default 0.92), scoped per project, a `force` override, and `duplicate_of` in the ingest response. Paraphrases scored 0.96+ and a same-theme different statement 0.76, so the default holds up on a small sample; revisit with real data.

**Why:** There's nothing stopping Claude from storing the same decision repeatedly across sessions. That adds noise and drags down search quality over time.

**Suggested approach:** In `/ingest`, after computing the embedding, query the top hit. If its cosine score is above a threshold, return the existing entry with a flag like `duplicate_of` instead of inserting. The threshold needs tuning against real entries, so make it an env var (something like `DEDUP_THRESHOLD`, start around 0.92 and adjust). Make sure the MCP `add_to_brain` response says clearly when it skipped a near-duplicate, so Claude doesn't think it stored something new. Consider a `force` param to override.

**Done when:** Adding the same sentence twice stores one entry and tells the caller why.

### 4. ~~Surface metadata extraction failures~~ Done

Implemented: `metadata_status` (`ok`/`failed`) stored and returned, `METADATA_TIMEOUT` (default 60s), an MCP note on failure, and cleanup of placeholder values like `none`. The re-extract path is still open and belongs to #6.

**Why:** `extract_metadata` has a 20s timeout and catches every exception, falling back to `type: other` with empty lists. A cold `llama3.2` load on a fresh Ollama can easily take longer than that, so entries get stored with no metadata and nobody finds out. The only trace is a `[metadata]` line in container logs. This also quietly degrades the topic and people stats.

**Suggested approach:** Add a `metadata_status` field (`ok` / `failed`) to the ingest response and stored payload. Raise the timeout (or make it an env var). Show a note in the `add_to_brain` MCP output when extraction failed. Optionally add a re-extract path (see FEAT-001 below) so failed entries can be repaired later.

### 5. ~~Hybrid search (FEAT-004)~~ Done

Implemented without upgrading anything: a full-text index on `content`, BM25 computed in the API over the keyword candidates, and reciprocal rank fusion with the vector results. `qdrant.search` was replaced by `query_points`, so GAP-013 is only partly open (`on_event` remains). The vector-only mode is `mode=semantic`.

**Why:** Pure semantic search is weak on exact terms: names, identifiers, error strings, library names. Those make up much of what a dev knowledge base holds.

**Suggested approach:** Qdrant 1.11 doesn't give you BM25 for free. One option is a full-text payload index on `content` plus a text match query, then merging the two ranked lists with reciprocal rank fusion in the API. Check what 1.11.x supports before committing, and only upgrade `qdrant-client` and the server image if there's a clear benefit. This also means migrating off the deprecated `qdrant.search` call (GAP-013), which is a good time to do it.

### 6. ~~Edit, export, import (FEAT-001, FEAT-006)~~ Done

**Progress:** Stage 1 (edit) is done: `PATCH /entries/{id}` with content/tags/project/reextract, the `update_brain_entry` MCP tool, and 404/422 handling on delete (GAP-009 API half). Stage 2 (`GET /export`, streamed JSONL without vectors) is done. Stage 3 (`POST /import`) is done too: re-embeds, keeps ids and dates, skips existing ids unless `overwrite=true`, reuses good metadata, and skips the dedup check. Verified by wiping the brain and restoring: the re-export was byte-identical.

**Why:** Data ownership is a stated goal (G5), but right now the only backup is a Docker volume snapshot, and a wrongly labeled entry can only be fixed by delete and re-add.

**Suggested approach:** `PATCH /entries/{id}` that updates content/tags/project and optionally re-runs embedding and metadata. A `GET /export` that streams JSONL (id, content, source, tags, project, created_at, metadata, no vectors), and an `/import` that re-embeds. Re-embedding on import keeps the export model-agnostic. Also expose an update tool over MCP so Claude can correct entries.

## Small fixes to fold in along the way

- `delete_entry` should validate the id and return 404 for missing entries instead of 200 (GAP-009).
- ~~Validate `limit` on `/search` and `/entries`~~ done (GAP-012), as were GAP-014 and GAP-015.
- ~~`/health` should probe Qdrant and Ollama~~ done (GAP-011).
- `/stats` scrolls the entire collection on every call. Fine at this size, but cache it or compute incrementally if the brain grows into the thousands.

## Not in scope right now

Auth (FEAT-007) matters only if this is ever exposed beyond localhost. All ports are bound to `127.0.0.1`, so it can wait. Chunking long content (FEAT-005) is worth doing if entries start getting long, but the typical entry here is a short note or decision.

## Suggested process

**Status:** every priority item above is done, and the API has a pytest suite (`brain-api/tests`, see the README). Remaining: CI, linting, tests for the MCP server and web UI, and the leftovers noted in each item.

_Original advice:_ start with #1, since it's small and fixes something already broken. Add pytest coverage for the API with Ollama and Qdrant mocked as you go (GAP-018), starting with whatever you touch. There are no tests today, so each change is currently unverified except by hand.
