# 02 — Functional Requirements: Retrieval

## 1. Semantic Search

**Endpoint:** `POST /search`

| ID | Requirement | Status |
|----|-------------|--------|
| SRCH-001 | The API MUST accept `{query: string, limit?: int, source_filter?: string}`. `limit` defaults to 5. | ✅ |
| SRCH-002 | Empty/whitespace `query` MUST return HTTP 400 `"Query cannot be empty"`. | ✅ |
| SRCH-003 | The query MUST be embedded with the same model as ingest and searched by cosine similarity. | ✅ |
| SRCH-004 | Results MUST be ordered by descending score and each include `id, content, source, tags, created_at, score, metadata{type,topics,people,action_items}`. | ✅ |
| SRCH-005 | If `source_filter` is set, results MUST be restricted to entries whose `source` exactly matches. | ✅ |
| SRCH-006 | Response MUST echo the original `query`. | ✅ |
| SRCH-007 | Missing payload fields MUST get defaults (`source="unknown"`, `tags=[]`, `type="other"`, etc.) so legacy entries do not break search. | ✅ |
| SRCH-008 | `limit` SHOULD be validated (positive, with an upper bound). Currently unbounded and unvalidated. | ⚠️ |
| SRCH-009 | Search SHOULD support filtering by tags, type, topics, people, and date range. | ❌ |
| SRCH-010 | Search SHOULD support a minimum score threshold. | ❌ |
| SRCH-011 | Search uses `qdrant.search`, deprecated in newer qdrant-client versions in favor of `query_points`. | ⚠️ |

## 2. List Recent Entries

**Endpoint:** `GET /entries?limit=20&offset=0`

| ID | Requirement | Status |
|----|-------------|--------|
| LIST-001 | The API MUST return `{entries: [...], count: n}`; each entry has `id, content, source, tags, created_at, type, topics, people, action_items` (flat, unlike search's nested `metadata`). | ✅ |
| LIST-002 | Entries returned MUST be sorted by `created_at` descending. | ⚠️ Sorted only within the fetched page; see gap GAP-001. |
| LIST-003 | The API MUST support `limit` (default 20). | ✅ |
| LIST-004 | `offset` MUST allow paging. Currently passed directly as Qdrant's scroll `offset`, which expects a point id/cursor, not an integer; paging is unreliable. | ❌ (bug) |
| LIST-005 | Vectors MUST NOT be returned (`with_vectors=False`). | ✅ |
| LIST-006 | "Most recent N" MUST be correct across the whole collection. Currently Qdrant scroll order is by internal point id, not time, so "recent" is only correct when total entries ≤ `limit`. | ❌ (bug) |

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
| HLTH-001 | MUST return `{status:"ok", collection, embed_model}` with HTTP 200 when the API process is running. | ✅ |
| HLTH-002 | Health currently does NOT verify Qdrant or Ollama connectivity. It SHOULD report dependency status. | ⚠️ |
| HLTH-003 | The web UI uses this endpoint for its online/offline indicator. | ✅ |
