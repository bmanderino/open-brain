# 06 — Deployment, Configuration, and Non-Functional Requirements

## 1. Deployment

| ID | Requirement | Status |
|----|-------------|--------|
| DEP-001 | The full stack MUST start with `docker compose up -d`. | ✅ |
| DEP-002 | After first start the user MUST pull the embedding model once (`ollama pull nomic-embed-text`, or `docker exec ollama ollama pull ...` with the container). The metadata model (`qwen3:14b`, about 9 GB) must be pulled likewise or extraction falls back (see META-004). The README documents both, in a Quick start and in Setup step 3. | ✅ |
| DEP-003 | Services share the `brain-net` bridge network; services restart `unless-stopped`. | ✅ |
| DEP-004 | Brain API starts after `qdrant` and `ollama` (`depends_on`, start order only, no health-based wait). If Qdrant isn't ready the API's startup collection check may crash and rely on restart. | ⚠️ |
| DEP-005 | The Qdrant image is pinned (`qdrant/qdrant:v1.20.0`, the server version the stack was verified against); the Python client stays at 1.11.3. Bump the tag deliberately. | ✅ |
| DEP-006 | The README MUST state the prerequisites: Docker with Compose v2, Ollama 0.9.0 or later (the `think` option used by metadata extraction), disk and RAM for `qwen3:14b`, and the size of the first image downloads. | ✅ |
| DEP-007 | The repository carries an MIT `LICENSE` file. | ✅ |

### Services and Ports

| Service | Container | Host:Container (bound to 127.0.0.1) | Notes |
|---------|-----------|----------------|-------|
| ollama | `ollama` | (not published; see GAP-005) | Volume `ollama-data`; bind mount `./ollama/llm_models` |
| qdrant | `open-brain-qdrant` | 6333, 6334 | Volume `qdrant_data` |
| brain-api | `open-brain-api` | 8000:8000 | |
| mcp-server | `open-brain-mcp` | 3001:3000 | |
| web-ui | `open-brain-ui` | 5173:80 | |
| open-webui | `open-webui` | 8080:8080 | Optional extra; not part of Open Brain proper |

## 2. Configuration

| Variable | Service | Default | Purpose |
|----------|---------|---------|---------|
| `QDRANT_HOST` / `QDRANT_PORT` | brain-api | `localhost` / `6333` | Vector DB location |
| `OLLAMA_HOST` / `OLLAMA_PORT` | brain-api | `localhost` / `11434` | Ollama location |
| `OLLAMA_EMBED_MODEL` | brain-api | `nomic-embed-text` | Embedding model |
| `OLLAMA_LLM_MODEL` | brain-api | `qwen3:14b` | Metadata extraction model |
| `COLLECTION_NAME` | brain-api | `brain` | Qdrant collection |
| `METADATA_TIMEOUT` | brain-api | `60` | Seconds to wait for the LLM metadata call before recording `metadata_status: failed` |
| `DEDUP_THRESHOLD` | brain-api | `0.92` | Cosine score at/above which an ingest is treated as a near-duplicate and not stored (values above 1 disable) |
| `CORS_ORIGINS` | brain-api | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API |
| `BRAIN_API_URL` | mcp-server | `http://brain-api:8000` | Upstream API |
| `PORT` | mcp-server | `3000` | Listen port |
| `BRAIN_API_URL` | web-ui | `http://localhost:8000` | Browser-visible API URL |

| ID | Requirement | Status |
|----|-------------|--------|
| CFG-001 | All endpoints and models MUST be configurable via environment variables with the defaults above. | ✅ |
| CFG-002 | Compose currently sets `OLLAMA_HOST=host.docker.internal` (uses a host-installed Ollama, e.g. Apple Silicon Metal) while also running an `ollama` container. Only one is used; the choice is manual. See GAP-005. | ⚠️ |
| CFG-003 | GPU: the NVIDIA `deploy` block is currently removed in the working tree (uncommitted); README says it is "pre-configured" for NVIDIA. | ⚠️ |

## 3. Non-Functional Requirements

### Performance
| ID | Requirement |
|----|-------------|
| NFR-001 | Ingest SHOULD complete in seconds on GPU/Metal hardware; because embedding and metadata run in parallel, latency ≈ max of the two. Timeouts: embed 30 s, metadata 60 s (`METADATA_TIMEOUT`), MCP add 60 s, MCP search/list/stats 30 s. |
| NFR-002 | Search latency SHOULD be dominated by one embedding call plus a Qdrant ANN query. |
| NFR-003 | Target scale: a single user, up to ~10⁴–10⁵ entries. Stats and list endpoints are not designed beyond this. |

### Reliability
| ID | Requirement |
|----|-------------|
| NFR-010 | LLM metadata failure MUST NOT block capture (graceful degradation). ✅ |
| NFR-011 | Embedding failure MUST surface as an error (no silent data loss). ✅ |
| NFR-012 | Data MUST survive container restarts via named volumes. ✅ |

### Security
| ID | Requirement | Status |
|----|-------------|--------|
| NFR-020 | The system is designed for localhost / trusted-network use only. | By design |
| NFR-021 | CORS MUST be limited to the configured `CORS_ORIGINS` (default `http://localhost:5173`, `http://127.0.0.1:5173`), allowing only GET/POST/PATCH/DELETE and the `Content-Type` header. | ✅ |
| NFR-021a | There is still no authentication on the Brain API, MCP server, or Qdrant. Auth MUST be added before any non-local exposure. | ⚠️ |
| NFR-022 | All published ports MUST bind to `127.0.0.1` only. To expose on a LAN, change the mapping and set `CORS_ORIGINS` accordingly. | ✅ |
| NFR-023 | Content passed to the LLM is untrusted (prompt injection can only influence metadata fields, which are validated/coerced). | ✅ |

### Observability
| ID | Requirement | Status |
|----|-------------|--------|
| NFR-030 | Logging is `print` statements only (collection creation, metadata failures). Structured logging SHOULD be added. | ⚠️ |
| NFR-031 | No metrics or tracing. | ❌ |

### Quality
| ID | Requirement | Status |
|----|-------------|--------|
| NFR-040 | API tests (pytest, `brain-api/tests`) run against an in-memory Qdrant with Ollama's embedding and metadata calls faked; they cover the API's behavior end to end and run in under a second. The MCP server has its own pytest suite (`mcp-server/tests`, 32 tests) that calls each tool with the HTTP transport faked and asserts the requests sent and the text returned. There is no web-UI test coverage. | ⚠️ |
| NFR-042 | Python code MUST pass `ruff check` with the rules in `ruff.toml` (E, F, W, I, B, UP; E501, UP007, UP017, B905 ignored). Ruff is pinned in `brain-api/requirements-dev.txt`. | ✅ |
| NFR-042a | Python code MUST be formatted by `ruff format` (line length 100 from `ruff.toml`); CI fails on `ruff format --check .`. | ✅ |
| NFR-043 | CI (GitHub Actions, `.github/workflows/ci.yml`) MUST run on pushes to `main` and on pull requests: ruff (check and format check), the API tests and MCP server tests on Python 3.12, a web UI production build (`npm run build`), and `docker compose config -q`. It does not build the Docker images or run the stack. | ✅ |
| NFR-041 | Dependencies are version-pinned (API) or lower-bounded (`mcp[cli]>=1.8.0,<2`; v2 renamed FastMCP and breaks the server). | ✅ / ⚠️ |

### Compatibility
- Host: Docker with Compose v2; NVIDIA GPU (needs deploy block restored), Apple Silicon (host Ollama via Metal), or CPU.
- Browser: modern evergreen browsers (uses `-webkit-line-clamp`, CSS grid).
- Clients: Claude Code (MCP streamable-http).
