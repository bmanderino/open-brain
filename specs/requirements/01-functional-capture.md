# 01 — Functional Requirements: Capture

Requirement keywords: **MUST**, **SHOULD**, **MAY**. Status: ✅ implemented, ⚠️ partial, ❌ not implemented.

## 1. Ingest

**Endpoint:** `POST /ingest` (`brain-api/main.py`)

| ID | Requirement | Status |
|----|-------------|--------|
| CAP-001 | The API MUST accept JSON `{content: string, source?: string, tags?: string[], project?: string, force?: bool}`. `source` defaults to `"manual"`, `tags` to `[]` (a `null` is normalized to `[]`). `project` is optional; blank values are treated as absent and the key is not stored. | ✅ |
| CAP-002 | The API MUST reject empty or whitespace-only `content` with HTTP 400 `"Content cannot be empty"`. | ✅ |
| CAP-003 | The API MUST generate a UUIDv4 `id` and a UTC ISO-8601 `created_at` timestamp server-side. | ✅ |
| CAP-004 | The API MUST generate an embedding of `content` via Ollama and store it as the point vector. | ✅ |
| CAP-005 | Embedding and metadata extraction MUST run concurrently (`asyncio.gather`). | ✅ |
| CAP-006 | If embedding fails (non-200 from Ollama), the API MUST return HTTP 502 with the Ollama error and MUST NOT store a partial entry. | ✅ |
| CAP-007 | The response MUST return `id, content, source, tags, project, created_at, metadata` (`project` is `null` when unscoped). | ✅ |
| CAP-008 | `source` SHOULD identify the origin surface. Current values: `web-ui`, `mcp`, `cli` (user-supplied), `manual` (default). | ✅ |
| CAP-009 | The API SHOULD enforce a maximum content length or chunk long content to fit the embedding model's context window. | ❌ |
| CAP-010 | The API SHOULD skip near-identical content. Before inserting, it MUST look up the top match within the same project scope (same `project`, or among unscoped entries when none is given); if its cosine score is ≥ `DEDUP_THRESHOLD` (default 0.92) it MUST NOT insert and instead returns the existing entry with `duplicate_of` (its id) and `duplicate_score`. `force: true` in the request bypasses the check. | ✅ |

## 2. Automatic Metadata Extraction

| ID | Requirement | Status |
|----|-------------|--------|
| META-001 | On ingest, the API MUST call Ollama `/api/generate` with `format: "json"`, `stream: false`, model `OLLAMA_LLM_MODEL` (default `llama3.2`), 20 s timeout. | ✅ |
| META-002 | The extraction prompt MUST request: `type`, `topics[]`, `people[]`, `action_items[]`. | ✅ |
| META-003 | Valid `type` values: `decision, idea, meeting, action_item, reference, question, reflection, other`. Any other value MUST be coerced to `other`. | ✅ |
| META-004 | Extraction MUST NOT fail ingest. On any error (HTTP failure, timeout, invalid JSON) the API MUST log and fall back to `Metadata()` (`type=other`, empty lists) and record `metadata_status: "failed"`. The LLM call times out after `METADATA_TIMEOUT` seconds (default 60). | ✅ |
| META-005 | Extracted metadata MUST be persisted in the point payload as top-level keys `type, topics, people, action_items`, plus `metadata_status` (`"ok"` or `"failed"`). The ingest response, `/entries`, and duplicate responses include `metadata_status` (`null` for entries stored before the field existed). | ✅ |
| META-008 | List fields MUST be cleaned: a bare string becomes a one-item list, and placeholder values (`none`, `n/a`, `null`, `unknown`, empty) are dropped. | ✅ |
| META-006 | User content is interpolated into the prompt via `str.format`; content containing literal `{`/`}` is safe because only the template is formatted, but prompt-injection by content is possible and MUST be treated as untrusted. | ⚠️ |
| META-007 | Users SHOULD be able to override or edit extracted metadata. | ❌ |

## 3. Delete

**Endpoint:** `DELETE /entries/{entry_id}`

| ID | Requirement | Status |
|----|-------------|--------|
| DEL-001 | The API MUST delete the point with the given id from the collection and return `{"deleted": "<id>"}`. | ✅ |
| DEL-002 | Deleting a non-existent id MUST return 404. | ✅ |
| DEL-003 | Deletion is permanent; there is no soft-delete or undo. | ✅ (by design) |
| DEL-004 | A malformed (non-UUID) id MUST return 422. | ✅ |
| DEL-005 | The MCP server does not expose delete. This is intentional to prevent accidental AI deletion. | ✅ |

## 4. Update

| ID | Requirement | Status |
|----|-------------|--------|
| UPD-001 | The API MUST support `PATCH /entries/{id}` with `{content?, tags?, project?, reextract?}`; only fields that are sent change, and the response is the full updated entry in the flat `/entries` shape. | ✅ |
| UPD-002 | Changing `content` MUST re-embed the entry and re-run metadata extraction (concurrently), replacing the vector and the type/topics/people/action_items/metadata_status. `id`, `created_at`, and `source` are preserved. Empty content returns 400. | ✅ |
| UPD-003 | `tags` replaces the whole list. `project` set to `null` or `""` removes the project key (the entry becomes unscoped). | ✅ |
| UPD-004 | `reextract: true` MUST re-run metadata extraction without changing content or the vector, so entries with `metadata_status: failed` can be repaired. | ✅ |
| UPD-005 | Missing id returns 404 and a malformed id returns 422. Updates do not run the duplicate check. | ✅ |
| UPD-006 | Editing `type`, `topics`, `people`, or `action_items` by hand is not supported; use `reextract`. | ❌ |
