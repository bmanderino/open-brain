# 05 — Data Model

## 1. Storage

| ID | Requirement | Status |
|----|-------------|--------|
| DATA-001 | All entries MUST be stored as points in a single Qdrant collection named by `COLLECTION_NAME` (default `brain`). | ✅ |
| DATA-002 | The collection MUST be created on API startup if absent, with vector size 768 and cosine distance. If it exists it is left untouched. | ✅ |
| DATA-003 | The vector size is hard-coded (`EMBED_DIM = 768`) for `nomic-embed-text`. Changing `OLLAMA_EMBED_MODEL` to a model with a different dimension requires a new collection and re-embedding. The API SHOULD validate this at startup. | ⚠️ |
| DATA-004 | Qdrant data MUST persist in the `qdrant_data` Docker volume across restarts; `docker compose down -v` destroys it. | ✅ |
| DATA-005 | There are no payload indexes. Filtering by `source` is a full scan; acceptable at personal scale. | ✅ (accepted) |
| DATA-006 | There is no backup/export/import mechanism. | ❌ |

## 2. Point

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDv4 string | Qdrant point id |
| `vector` | float[768] | Embedding of `content` |
| `payload` | object | See below |

## 3. Payload

| Key | Type | Source | Default when absent (read path) |
|-----|------|--------|---------------------------------|
| `content` | string | user | required |
| `source` | string | client (`web-ui`, `mcp`, `cli`, `manual`, …) | `"unknown"` |
| `tags` | string[] | user | `[]` |
| `project` | string | client (optional; key omitted when unscoped) | `null` |
| `created_at` | ISO-8601 UTC string | server | `""` |
| `type` | enum string | LLM | `"other"` |
| `topics` | string[] | LLM | `[]` |
| `people` | string[] | LLM | `[]` |
| `action_items` | string[] | LLM | `[]` |

`type` enum: `decision | idea | meeting | action_item | reference | question | reflection | other`.

## 4. API Shape Notes

- DATA-010: Ingest and search responses nest LLM output under `metadata`; `/entries` returns it flat at the top level. Consumers (UI, MCP) handle each shape separately. Unifying is a possible future cleanup.
- DATA-011: Embeddings are never returned to clients.
- DATA-012: Content is stored and embedded as one unit; no chunking.
- DATA-015: A full-text index on `content` (word tokenizer, lowercase, min token length 2) is created idempotently at startup to support keyword search.
- DATA-014: Keyword payload indexes on `project`, `type`, `source`, and `tags` are created idempotently at startup to support filters.
- DATA-013: `created_at` has a datetime payload index, created idempotently at API startup, used for `order_by` in `/entries`.

## 5. Privacy

- DATA-020: All content, embeddings, and LLM inference stay on the local host/Docker network. No telemetry or third-party calls are made by project code.
