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

**Progress:** Stage 1 (edit) is done: `PATCH /entries/{id}` with content/tags/project/reextract (hand-editing of type/topics/people/action items was added afterwards), the `update_brain_entry` MCP tool, and 404/422 handling on delete (GAP-009 API half). Stage 2 (`GET /export`, streamed JSONL without vectors) is done. Stage 3 (`POST /import`) is done too: re-embeds, keeps ids and dates, skips existing ids unless `overwrite=true`, reuses good metadata, and skips the dedup check. Verified by wiping the brain and restoring: the re-export was byte-identical.

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

**Status:** every priority item above is done, and the API has a pytest suite (`brain-api/tests`, see the README). CI (GitHub Actions) and ruff linting are in place. The MCP server wrappers are tested too. Remaining: web UI tests and a web UI linter, and the leftovers noted in each item.

_Original advice:_ start with #1, since it's small and fixes something already broken. Add pytest coverage for the API with Ollama and Qdrant mocked as you go (GAP-018), starting with whatever you touch. There are no tests today, so each change is currently unverified except by hand.

---

# Round 2: Features from comparable projects

Round 1 above is done. This round comes from comparing Open Brain against other personal and agent memory projects (the Supabase-based Open Brain servers, Mem0, Letta, Zep/Graphiti, mcp-memory-service, and others). That comparison was based on READMEs and listings only, not their code, so treat the descriptions of those projects as inspiration, not as specs. Also verify details of the current implementation (for example what `search_brain` returns) before building on them.

The same constraint applies: everything must run in the existing Compose stack, fully local, no new cloud dependency.

### 7. ~~Automatic capture and recall (hooks plus `get_context`)~~ Done (capture is reminder-driven)

Implemented: `GET /context` (JSON or `format=text`), the `get_context` MCP tool, and a documented `SessionStart` hook in the README. The hook research found that only `SessionStart` and `UserPromptSubmit` output reaches the model, `SessionEnd` has no effect on the session, and a `Stop` hook fires every turn, so there is no hook that can nudge Claude to save at session end. Capture therefore relies on a reminder at the end of the injected context text plus `CLAUDE.md`, and the original "session end leaves new entries behind" goal was dropped. Not done: a `PreCompact` hook (its output path was not confirmed), and a web UI view of context.

**Why:** The README says Claude "can default to its own memory" when it isn't told to use the brain, and `CLAUDE.md` only helps if Claude follows it. Right now the brain gets used when someone remembers to ask. This is the gap between "available" and "actually used", and it's the highest-value item in this round.

**Suggested approach:**
- Add a `GET /context?project=` endpoint that returns pinned entries (see #8) first, then the most recent entries for that project, plus unscoped entries, in one compact response. Keep the output short, since it will be injected into context. Hooks can't call MCP tools, so the endpoint is the primary piece.
- Add a `get_context(project)` MCP tool as a thin wrapper over that endpoint.
- Document a Claude Code `SessionStart` hook that calls the endpoint (or a tiny script) and injects the result at the start of a session.
- **Verify before designing the capture side.** As far as we know, `SessionStart` stdout can be injected as context, but `PreCompact` and `SessionEnd` may only run side effects and can't put anything in front of the model. Check what each hook event can actually do in the current Claude Code version. If they can't nudge Claude, use a `Stop` hook, a `CLAUDE.md` instruction, or a hook that summarizes and calls `/ingest` over HTTP itself. Don't promise "a session end leaves new entries behind" until a working path is confirmed.
- Put the hook snippets in the README and a `docs/` or `specs/` file so they're copy-pasteable.

**Done when:** A fresh session in a repo with the hook shows that project's pinned and recent entries without anyone asking. (The original second clause, that a session end leaves new entries behind, is not achievable with hooks; see above.)

### 8. ~~Pinned core memories~~ Done

Implemented: optional `pinned` flag (key omitted when false, so no migration), bool payload index, settable on `/ingest`, `PATCH`, and the MCP tools, filterable with `GET /entries?pinned=true`, shown first by `/context` with a cap of 20, and kept by export/import. Unscoped pins are global. Still open: pin control in the web UI (PIN-007).

**Why:** Letta separates always-in-context "core" memory from searchable archive. Some facts ("this repo targets Windows", "use pnpm", "avoid em dashes in docs") should be present every session and never depend on a search hit.

**Suggested approach:** Add an optional boolean `pinned` to the payload (default false), settable on ingest and via `PATCH` / `update_brain_entry`, with a keyword or bool payload index so it can be filtered. `get_context` (#7) returns pinned entries first. Consider a soft cap on how many pinned entries get returned so context stays small, and flag pins in `list_brain` and search output.

Decisions to make explicit:
- **Unscoped pins are global.** A pin with no `project` shows up in every project's context. A pin with a `project` shows up only there.
- **Export/import must carry `pinned`.** The round trip is byte-identical today, so keep it that way and add a test.

### 9. Supersession (retire or replace outdated entries)

**Why:** Dedup only catches near-identical text. If a decision changes (Postgres in March, SQLite in October), both entries stay live and search returns both with no hint which is current. Zep/Graphiti track when facts stop being true, and Mem0 decides between add and update when it extracts facts. A lightweight local version solves most of the problem.

**Suggested approach:**
- Add `superseded_by` (entry id, optional) to the payload and a way to set it, either via `PATCH` or a dedicated `supersede_brain_entry(old_id, new_id)` MCP tool.
- Exclude superseded entries from search, list, and `get_context` by default, with an `include_superseded` flag for audits.
- Build the manual path first: the `supersede_brain_entry` tool, the default exclusion, and `include_superseded`. This is where most of the value is.
- At ingest, surface the top few neighbors that fall below the dedup threshold as `possibly_supersedes` so the caller can decide. Don't auto-supersede, because a wrong guess silently hides a good entry.
- **Don't rely on a narrow similarity band.** The dedup sampling in #3 put paraphrases at 0.96+ and a same-theme, different statement at 0.76. A flipped decision ("Postgres" to "SQLite") probably scores near the low end, so a tight band between that and the dedup threshold will be noisy. Return the top neighbors with scores and `created_at` and let Claude judge, and make sure search results show `created_at` so the newer entry is visible.
- Share the ingest-time neighbor lookup with dedup and #10 so it's one query, not three.
- Show superseded state in the web UI and keep it in export/import.

**Done when:** Superseding an entry hides it from default search, and the add response surfaces likely candidates to replace.

**Status (2026-10-22):** Built as `PATCH superseded_by` plus the `supersede_brain_entry` tool (SUP-001..007), with `include_superseded` on search and list, exclusion from `get_context` and dedup, `possibly_supersedes` on ingest (up to 3 neighbors at or above `NEIGHBOR_MIN_SCORE`, 0.6, untuned), and export/import. Deleting a replacement restores what it replaced. Web UI support was added afterwards (UI-060..064). The index on `superseded_by` and the `IsEmpty` filter are only verified against local-mode Qdrant, so try it once against the real server.

### 10. Related-entry links

**Why:** The Supabase Open Brain auto-links new entries to similar ones, which gives a graph feel for browsing. Ingest already computes the nearest neighbor for dedup, so this is close to free.

**Suggested approach:** Compute links on read instead of storing them. Add a `related_to(id)` MCP tool and a matching `GET /entries/{id}/related` endpoint that queries Qdrant using the entry's own vector and returns the top 3 to 5 neighbors above a lower threshold. Show them in the UI. At this scale the query is cheap, and it avoids stale links, a re-link endpoint, a payload field, and import/export changes. This does not need a graph database.

If ingest-time neighbors are already returned for #9, reuse that lookup rather than adding another one.

**Status (2026-10-22):** Built as `GET /entries/{id}/related` and the `related_to` tool (REL-001..006), scoped like `/context`, default floor `RELATED_MIN_SCORE` 0.5 (untuned). It shares the `Neighbor` shape with the ingest lookup but runs its own query, since it starts from a stored vector rather than a new embedding. Verified against the real server via the MCP tool (0.5 filters little in a single-topic brain). Web UI support was added afterwards (UI-062).

### 11. Open loops and review (deferred)

**Status:** Hold until #7 is in use and there's evidence that action items get read. This is the riskiest item in the round: it changes the shape of `action_items`, which touches the payload, import/export, the UI, and the metadata-edit path. The items also come from `llama3.2` extraction, so they're likely noisy, and a todo list built on noisy extraction tends to rot.

**Why:** Action items are already extracted (FEAT-008) but have no state, so they pile up with no way to tell what's open. The Supabase version has weekly review synthesis of themes and open loops.

**Suggested approach:** Give action items a status (open/done) and a way to flip it, either by storing them as structured objects or by a parallel `done_actions` field. Be careful here: the payload currently stores `action_items` as a list of strings, so changing the shape needs a migration and an import/export update. Add an `open_actions(project)` MCP tool and an action list view in the UI. Optionally add `review(since)` that groups recent entries by topic and lists open actions, using `llama3.2` only if a plain grouped listing isn't enough.

### 12. Transcript indexing (optional, lower priority)

**Why:** One comparable project has a tool that summarizes past editor chat sessions into entries, which backfills the brain without anyone remembering to save. Claude Code keeps session transcripts locally.

**Suggested approach:** A standalone script (not part of the API) that reads session JSONL files, summarizes each with the local LLM, and calls `/ingest` with `source=transcript` and the right `project`. Make it idempotent, for example by keying on session id so reruns don't duplicate. Expect noisy summaries, so consider tagging these entries and excluding them from default search until quality is checked. Check where Claude Code stores transcripts and their format first, since that can change between versions.

## Deliberately skipped

- Cloud sync, OAuth, and hosted/remote MCP access (mcp-memory-service style). These conflict with the local-first goal.
- A full knowledge graph or graph database. Related-entry links (#10) get most of the value at this scale.
- Markdown/Obsidian two-way sync. JSONL export already covers portability. Revisit only if reading the brain in an editor becomes a real want.
- Auth (FEAT-007) stays low priority while everything is bound to `127.0.0.1`.
- Chunking (FEAT-005) is still open. Cheap to ignore until entries get long, and worth revisiting if transcript indexing (#12) is built, since summaries and long notes can exceed the embedding context.

## Suggested order

1. #7 and #8 together, since `get_context` depends on pinning. Confirm hook capabilities first.
2. #9, manual supersede path first.
3. #10, as a compute-on-read endpoint and tool.
4. #11 and #12 only if usage justifies them.

## Open question: retrieval quality

Nothing measures whether retrieval is actually good. Hybrid search and the dedup threshold were both tuned on small samples. Before #9 relies on similarity thresholds, consider a small fixed set of queries with expected hits (a few dozen is enough, run against a seeded test collection) so changes to search, thresholds, or models can be compared instead of guessed at. Optional, but it would make the numbers in #3, #5, and #9 less of a guess.
