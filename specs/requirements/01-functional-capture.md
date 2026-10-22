# 01 — Functional Requirements: Capture

Requirement keywords: **MUST**, **SHOULD**, **MAY**. Status: ✅ implemented, ⚠️ partial, ❌ not implemented.

## 1. Ingest

**Endpoint:** `POST /ingest` (`brain-api/main.py`)

| ID | Requirement | Status |
|----|-------------|--------|
| CAP-001 | The API MUST accept JSON `{content: string, source?: string, tags?: string[], project?: string}`. `source` defaults to `"manual"`, `tags` to `[]` (a `null` is normalized to `[]`). `project` is optional; blank values are treated as absent and the key is not stored. | ✅ |
| CAP-002 | The API MUST reject empty or whitespace-only `content` with HTTP 400 `"Content cannot be empty"`. | ✅ |
| CAP-003 | The API MUST generate a UUIDv4 `id` and a UTC ISO-8601 `created_at` timestamp server-side. | ✅ |
| CAP-004 | The API MUST generate an embedding of `content` via Ollama and store it as the point vector. | ✅ |
| CAP-005 | Embedding and metadata extraction MUST run concurrently (`asyncio.gather`). | ✅ |
| CAP-006 | If embedding fails (non-200 from Ollama), the API MUST return HTTP 502 with the Ollama error and MUST NOT store a partial entry. | ✅ |
| CAP-007 | The response MUST return `id, content, source, tags, project, created_at, metadata` (`project` is `null` when unscoped). | ✅ |
| CAP-008 | `source` SHOULD identify the origin surface. Current values: `web-ui`, `mcp`, `cli` (user-supplied), `manual` (default). | ✅ |
| CAP-009 | The API SHOULD enforce a maximum content length or chunk long content to fit the embedding model's context window. | ❌ |
| CAP-010 | The API MAY de-duplicate identical or near-identical content. | ❌ |

## 2. Automatic Metadata Extraction

| ID | Requirement | Status |
|----|-------------|--------|
| META-001 | On ingest, the API MUST call Ollama `/api/generate` with `format: "json"`, `stream: false`, model `OLLAMA_LLM_MODEL` (default `llama3.2`), 20 s timeout. | ✅ |
| META-002 | The extraction prompt MUST request: `type`, `topics[]`, `people[]`, `action_items[]`. | ✅ |
| META-003 | Valid `type` values: `decision, idea, meeting, action_item, reference, question, reflection, other`. Any other value MUST be coerced to `other`. | ✅ |
| META-004 | Extraction MUST NOT fail ingest. On any error (HTTP failure, timeout, invalid JSON) the API MUST log and fall back to `Metadata()` (`type=other`, empty lists). | ✅ |
| META-005 | Extracted metadata MUST be persisted in the point payload as top-level keys `type, topics, people, action_items`. | ✅ |
| META-006 | User content is interpolated into the prompt via `str.format`; content containing literal `{`/`}` is safe because only the template is formatted, but prompt-injection by content is possible and MUST be treated as untrusted. | ⚠️ |
| META-007 | Users SHOULD be able to override or edit extracted metadata. | ❌ |

## 3. Delete

**Endpoint:** `DELETE /entries/{entry_id}`

| ID | Requirement | Status |
|----|-------------|--------|
| DEL-001 | The API MUST delete the point with the given id from the collection and return `{"deleted": "<id>"}`. | ✅ |
| DEL-002 | Deleting a non-existent id currently returns 200 (Qdrant delete is idempotent). The API SHOULD return 404. | ⚠️ |
| DEL-003 | Deletion is permanent; there is no soft-delete or undo. | ✅ (by design) |
| DEL-004 | An invalid (non-UUID) id SHOULD return a 4xx; currently surfaces as an unhandled Qdrant error (500). | ⚠️ |
| DEL-005 | The MCP server does not expose delete. This is intentional to prevent accidental AI deletion. | ✅ |

## 4. Update

| ID | Requirement | Status |
|----|-------------|--------|
| UPD-001 | Editing an existing entry (content, tags, metadata) is not supported. Users delete and re-ingest. | ❌ (non-goal) |
