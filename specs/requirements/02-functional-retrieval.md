# 02 — Functional Requirements: Retrieval

## 1. Semantic Search

**Endpoint:** `POST /search`

| ID | Requirement | Status |
|----|-------------|--------|
| SRCH-001 | The API MUST accept `{query: string, limit?: int, source_filter?: string, project?: string, include_unscoped?: bool, type?: string, tag?: string, created_after?: string, created_before?: string, mode?: "hybrid"|"semantic"}`. `mode` defaults to `hybrid`. `limit` defaults to 5 and is validated 1–100. | ✅ |
| SRCH-002 | Empty/whitespace `query` MUST return HTTP 400 `"Query cannot be empty"`. | ✅ |
| SRCH-003 | The query MUST be embedded with the same model as ingest and searched by cosine similarity. | ✅ |
| SRCH-013 | In `hybrid` mode (default) the API MUST also run an exact-term search and merge it with the vector ranking by reciprocal rank fusion (k=60). Startup creates a full-text (word tokenizer, lowercase, min token length 2) index on `content`. Keyword candidates are points containing any non-stopword query term, ranked by BM25 computed in the API, because Qdrant 1.11 has no built-in BM25. Filters apply to both rankings. `semantic` mode returns the vector ranking only. | ✅ |
| SRCH-004 | Results MUST be ordered by descending score and each include `id, content, source, tags, project, created_at, score, match, metadata{type,topics,people,action_items}`. Order is by descending score in `semantic` mode and by fused rank in `hybrid` mode. | ✅ |
| SRCH-014 | `score` MUST always be the cosine similarity between the query and the entry (also for entries found only by keyword), so it means the same in both modes. `match` is `semantic`, `keyword`, or `both`, saying which rankings contained the entry. | ✅ |
| SRCH-005 | If `source_filter` is set, results MUST be restricted to entries whose `source` exactly matches. | ✅ |
| SRCH-006 | Response MUST echo the original `query`. | ✅ |
| SRCH-007 | Missing payload fields MUST get defaults (`source="unknown"`, `tags=[]`, `type="other"`, etc.) so legacy entries do not break search. | ✅ |
| SRCH-008 | `limit` SHOULD be validated (positive, with an upper bound). Validated 1–100. | ✅ |
| SRCH-009 | Search SHOULD support filtering by tags, type, topics, people, and date range. `tag`, `type`, and `created_after`/`created_before` are supported; `topics` and `people` are not. | ⚠️ |
| SRCH-012 | `project` filtering MUST match entries with that project and, unless `include_unscoped` is false (default true), entries with no `project`. All supplied filters are ANDed. Malformed timestamps return HTTP 422. | ✅ |
| SRCH-010 | Search SHOULD support a minimum score threshold. | ❌ |
| SRCH-011 | Search uses `query_points` (the deprecated `qdrant.search` is no longer used). | ✅ |

## 2. List Recent Entries

**Endpoint:** `GET /entries?limit=20&before=<ISO timestamp>`; also accepts `after`, `project`, `include_unscoped`, `type`, `tag`, `source` (same semantics as search, SRCH-012) and `pinned=true` (PIN-004)

| ID | Requirement | Status |
|----|-------------|--------|
| LIST-001 | The API MUST return `{entries: [...], count: n, next_before}`; each entry has `id, content, source, tags, project, pinned, created_at, type, topics, people, action_items` (flat, unlike search's nested `metadata`). | ✅ |
| LIST-002 | Entries returned MUST be sorted by `created_at` descending. | ✅ Server-side `order_by` on the indexed `created_at` field. |
| LIST-003 | The API MUST support `limit` (default 20, validated 1–100). | ✅ |
| LIST-004 | The API MUST allow paging: `before` returns only entries with `created_at` earlier than the timestamp; `next_before` in the response is the value to pass for the next page, or `null` on the last page. | ✅ |
| LIST-005 | Vectors MUST NOT be returned (`with_vectors=False`). | ✅ |
| LIST-006 | "Most recent N" MUST be correct across the whole collection. Startup creates a datetime payload index on `created_at` (idempotent) so existing collections work. Entries lacking `created_at` are excluded from this listing. | ✅ |

## 3. Stats

**Endpoint:** `GET /stats`

| ID | Requirement | Status |
|----|-------------|--------|
| STAT-001 | The API MUST return `total`, `by_source{source:count}`, `top_topics[{topic,count}]` (top 10), `top_people[{person,count}]` (top 10). | ✅ |
| STAT-002 | Stats MUST be computed by scrolling the full collection in batches of 100. | ✅ |
| STAT-003 | Stats are O(n) per call with no caching; acceptable for personal scale (thousands of entries). | ✅ (accepted) |
| STAT-004 | Topic/person counting is case-sensitive and does no normalization ("Qdrant" ≠ "qdrant"). Normalization SHOULD be added. | ⚠️ |
| STAT-005 | Stats are exposed to Claude via MCP `brain_stats`, but not displayed in the web UI. | ✅ / ❌ UI |

## 4. Health

**Endpoint:** `GET /health`

| ID | Requirement | Status |
|----|-------------|--------|
| HLTH-001 | MUST return HTTP 200 whenever the API process is running, with `{status, collection, embed_model, qdrant, ollama}`. | ✅ |
| HLTH-002 | Health MUST probe dependencies: `qdrant{ok, collection_exists}` (lists collections) and `ollama{ok, embed_model_present, llm_model_present}` (`GET /api/tags` with a 3 s timeout; a bare model name matches `:latest`). Failures are reported with `error`, never raised. | ✅ |
| HLTH-004 | `status` MUST be `ok` only when Qdrant is reachable with the collection present and Ollama is reachable with both models installed; otherwise `degraded`. A degraded status still returns HTTP 200 so the web UI's online indicator keeps meaning "the API is up". | ✅ |
| HLTH-003 | The web UI uses this endpoint for its online/offline indicator. | ✅ |

## 5. Session Context

**Endpoint:** `GET /context?project=&recent=5&max_pinned=20&format=json|text`

What a session should know up front, in one small response. Built to be injected by a Claude Code `SessionStart` hook (README) and exposed to the model as the `get_context` MCP tool.

| ID | Requirement | Status |
|----|-------------|--------|
| CTX-001 | The API MUST return pinned entries first (newest first, at most `max_pinned`, default 20, validated 0-100), then the newest unpinned entries (`recent`, default 5, validated 0-50). Pinned entries never repeat in `recent`. | ✅ |
| CTX-002 | With `project`, the result covers that project's entries plus unscoped ones. Without it, only unscoped entries are returned (not every project's), so a session with no project does not receive other projects' context. | ✅ |
| CTX-003 | The JSON form MUST be `{project, pinned[], pinned_total, recent[]}` with entries in the flat `/entries` shape. `pinned_total` counts all matching pins even when the list is capped. | ✅ |
| CTX-004 | `format=text` MUST return compact `text/plain`: a title, a `Pinned:` and a `Recent:` section with one line per entry (date, project or `general`, whitespace collapsed, truncated to 800 characters), a note when pins were hidden by the cap, and a closing line telling the model to save with `add_to_brain` (with the project) and search for anything older. | ✅ |
| CTX-005 | The text form is the only capture nudge available to hooks: as far as Claude Code documents, `SessionStart` (and `UserPromptSubmit`) stdout is added to the model's context, but `SessionEnd` output is not, so the saving reminder rides along with the context. See the README for what each hook event can and cannot do. | ✅ |
