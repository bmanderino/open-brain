# Open Brain — Product Requirements Document

> **Status:** Retroactive. This PRD documents the system as currently built (v1.0.0) and records known gaps and future direction. Requirement details live in [`requirements/`](requirements/).

## 1. Overview

Open Brain is a self-hosted, database-backed personal knowledge system. A user captures thoughts, decisions, and notes through a web UI, a CLI (`curl`), or directly from Claude Code via MCP. Entries are embedded and stored in a vector database, automatically enriched with structured metadata by a local LLM, and retrievable by *meaning* rather than keyword. The primary differentiator is that an AI coding assistant (Claude Code) can read from and write to the same knowledge base, giving it persistent, user-owned context across sessions.

Everything runs locally in Docker Compose; no data leaves the user's machine.

## 2. Problem Statement

- AI assistants forget between sessions, and built-in assistant memory is opaque, vendor-held, and not easily searchable or editable by the user.
- Personal notes (decisions, rationale, ideas) are scattered across tools and are hard to recall without remembering exact wording.
- Cloud knowledge tools require sending private notes to third parties.

## 3. Goals

| ID | Goal |
|----|------|
| G1 | Make capturing a thought take seconds, from any of three surfaces (web, CLI, MCP). |
| G2 | Retrieve relevant past entries by semantic similarity. |
| G3 | Give Claude Code read/write access to the knowledge base through MCP. |
| G4 | Auto-structure entries (type, topics, people, action items) with no user effort. |
| G5 | Keep all data and inference local and user-owned. |
| G6 | Be installable with `docker compose up` and a single model pull. |

## 4. Non-Goals (current version)

- Multi-user support, authentication, or authorization.
- Cloud hosting or remote/public deployment.
- Editing existing entries (only create, read, delete).
- Rich content: attachments, images, URL fetching/summarization.
- Hybrid (keyword + semantic) search, reranking, or LLM-generated answers over results (RAG synthesis).
- Mobile app or browser extension.

## 5. Target User

A single technical individual (developer / power user) who runs Docker locally, uses Claude Code, and wants a private "second brain" that their AI tools can share. Optionally has an NVIDIA GPU or Apple Silicon for faster inference.

## 6. Key User Stories

1. As a user, I write a thought in the web UI, add tags, and save it with one click or Ctrl/Cmd+Enter.
2. As a user, I search "why did I choose Qdrant" and see ranked entries even if the wording differs.
3. As a user, I see each entry auto-labelled with a type, topics, people, and action items.
4. As a user, I delete an entry I no longer want.
5. As a Claude Code user, I ask Claude to "check my brain for context on this project" and it searches my entries.
6. As a Claude Code user, I tell Claude to store a decision, and it appears in the web UI as source `mcp`.
7. As a scripter, I POST to the API with `curl` to store or search from any terminal.
8. As an operator, I view stats (totals, sources, top topics, top people) to understand what's in the brain.

## 7. System Summary

```
 Web UI (React/nginx :5173) ──┐
 curl / scripts ──────────────┼──► Brain API (FastAPI :8000) ──► Qdrant (:6333)
 Claude Code ─► MCP (:3001) ──┘              │
                                             └──► Ollama (:11434)
                                                  embeddings: nomic-embed-text
                                                  metadata LLM: llama3.2
```

| Component | Tech | Responsibility |
|-----------|------|----------------|
| `brain-api` | Python 3.12, FastAPI, qdrant-client, httpx | Ingest, search, list, delete, stats, health |
| `mcp-server` | Python 3.12, `mcp` FastMCP, streamable-http | Exposes 4 tools to Claude Code, proxies to Brain API |
| `web-ui` | React 18, Vite, nginx | Capture, recent list, semantic search |
| `qdrant` | Qdrant | Vector + payload storage (768-d, cosine) |
| `ollama` | Ollama | Local embeddings and metadata extraction |
| `open-webui` | Open WebUI | Optional, unrelated chat UI for Ollama models (bundled in compose) |

## 8. Requirements Index

| Document | Scope |
|----------|-------|
| [01-functional-capture.md](requirements/01-functional-capture.md) | Ingest, metadata extraction, delete |
| [02-functional-retrieval.md](requirements/02-functional-retrieval.md) | Search, list, stats, health |
| [03-mcp-integration.md](requirements/03-mcp-integration.md) | MCP server tools and client setup |
| [04-web-ui.md](requirements/04-web-ui.md) | Web UI behavior |
| [05-data-model.md](requirements/05-data-model.md) | Entry/payload schema, vector config |
| [06-deployment-nfr.md](requirements/06-deployment-nfr.md) | Deployment, configuration, non-functional |
| [07-known-gaps.md](requirements/07-known-gaps.md) | Discrepancies, bugs, and proposed work |

## 9. Success Metrics

Single-user, local tool, so metrics are qualitative/self-measured:

- Stack reaches healthy state with ≤ 3 commands after clone.
- Ingest round trip (embed + metadata + store) completes in a few seconds on target hardware.
- A semantically related query surfaces the intended entry in the top 5 for typical personal notes.
- Claude Code successfully invokes all MCP tools without manual intervention after config.

## 10. Risks and Open Questions

- **Security:** No authentication. CORS is restricted to the web UI origin and ports bind to `127.0.0.1`, but the stack is still unsafe to expose beyond localhost without adding auth. See gaps doc.
- **LLM metadata quality:** Small local model may mislabel; failure is silent (falls back to `other`/empty).
- **Pagination correctness:** `/entries` offset semantics don't match Qdrant's scroll model (see gaps).
- **Embedding model lock-in:** Changing embed model changes dimension and requires re-embedding all data.
- Open: Should authentication be added before any non-local use? Should entries be editable? Should search blend keyword and vector scoring?
