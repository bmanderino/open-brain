# Open Brain

A database-backed, MCP-connected personal knowledge system. Drop thoughts in via
the web UI or CLI, search them semantically, and give Claude Code access to your
accumulated context via MCP.

## Stack

| Service     | Port  | Role                                                      |
|-------------|-------|-----------------------------------------------------------|
| Ollama      | 11434 | Embeddings (`nomic-embed-text`) + metadata (`llama3.2`)   |
| Qdrant      | 6333  | Vector database                                           |
| Brain API   | 8000  | Ingest + search (FastAPI, Python)                         |
| MCP Server  | 3001  | Claude Code integration (Python, streamable HTTP)         |
| Web UI      | 5173  | Browser capture + search                                  |

All services run via Docker Compose. Every published port is bound to `127.0.0.1`,
so the stack is reachable from your machine only. There is **no authentication**,
so don't expose these ports to a network you don't trust.

By default the Brain API uses an **Ollama installed on your host** (reached via
`host.docker.internal`). The compose file also defines an `ollama` container, but it
doesn't publish a port and isn't used unless you switch to it (see below).

---

## Setup

### 1. Choose where Ollama runs

**Host Ollama (default — recommended on Apple Silicon):** Install Ollama from
<https://ollama.com> and make sure it's running. It uses Metal automatically. No
compose changes needed. If your host Ollama listens only on loopback and you're on
Linux, you may need `OLLAMA_HOST=0.0.0.0` for containers to reach it.

**Ollama container (NVIDIA GPU or CPU):** In `docker-compose.yml`:

1. On `brain-api`, set `OLLAMA_HOST=ollama`.
2. On the `ollama` service, publish the port (only if the host port is free — stop
   any host Ollama first): `ports: ["127.0.0.1:11434:11434"]`.
3. For NVIDIA, also add this to the `ollama` service (requires the NVIDIA Container
   Toolkit):

   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: all
             capabilities: [gpu]
   ```

CPU-only works too (skip step 3); embeddings and metadata extraction will be slower.

### 2. Start the stack

```bash
docker compose up -d
```

First run will build the images — takes a few minutes. After that, restarts are instant.

Check everything is up:

```bash
docker compose ps
```

### 3. Pull the models

Two models are used:

- `nomic-embed-text` — embeddings (**required**).
- `llama3.2` — extracts each entry's type, topics, people, and action items. If it's
  missing or too slow (the call times out after `METADATA_TIMEOUT` seconds, default 60, which
  matters for a cold model load), entries are still stored but get type `other` and no extracted
  metadata. Such entries are marked `metadata_status: failed`, and `add_to_brain` says so.
  To use a different model you already have, set `OLLAMA_LLM_MODEL` on `brain-api`.

With host Ollama:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

With the Ollama container:

```bash
docker exec ollama ollama pull nomic-embed-text
docker exec ollama ollama pull llama3.2
```

This only needs to be done once per model.

Verify the Brain API is healthy:
```bash
curl http://localhost:8000/health
```

Note: `/health` only confirms the API process is up; it doesn't check Ollama or Qdrant.

### 4. Connect Claude Code

Edit (or create) `~/.claude.json`:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "http",
      "url": "http://localhost:3001/mcp"
    }
  }
}
```

The server uses the streamable HTTP transport, so the type is `http` (not `sse`).
Alternatively: `claude mcp add --transport http open-brain http://localhost:3001/mcp`.

Restart Claude Code. You should see `open-brain` in the available tools.

### 5. Access the Web UI

```
http://localhost:5173
```

The Brain API only accepts browser requests from the web UI's origins. If you serve
the UI from a different URL, set `CORS_ORIGINS` (comma-separated) on `brain-api`.

---

## Using with Claude Code

Once connected, Claude Code can:

- **`search_brain`** — semantic search over everything you've stored; optional `project`, `type`, `tag`, `source` filters
- **`add_to_brain`** — store thoughts/decisions during a session; optional `tags` and `project`
- **`list_brain`** — see recent entries, newest first; optional `project`, `type`, `tag` filters
- **`update_brain_entry`** — fix an entry's content, tags, or project, or re-run metadata extraction
- **`brain_stats`** — totals, entries by source, top topics, and top people

Claude cannot delete entries; use the web UI for that.

Example prompts in Claude Code:
- "Search my brain for anything about the RPG game architecture"
- "Add to my brain that I decided to use Qdrant over Pinecone because of the Docker-native setup"
- "Before we start, check my brain for any context on this project"

### Search

Searches are hybrid: semantic similarity plus exact-term matching (names, identifiers, error
strings, library names), merged by reciprocal rank fusion. Each result's `score` is the
cosine similarity to the query, and `match` (`semantic`, `keyword`, or `both`) shows how it was
found. Send `"mode": "semantic"` to `/search` for vector-only results.

### Duplicates

`add_to_brain` and `POST /ingest` skip near-duplicates: if an existing entry in the same project
(or among unscoped entries) has a cosine similarity of at least `DEDUP_THRESHOLD` (default
`0.92`, set on `brain-api`), nothing is stored and the existing entry is returned with
`duplicate_of`. Pass `force` (`"force": true` in the API, `force=True` in the tool) to store anyway.
In testing, rewordings of the same statement scored 0.96+ and a different statement on the same
theme scored about 0.76; raise the threshold if too much is being skipped, lower it to catch more.

### Projects

Entries can be tagged with a `project` (for example the repo name) so context from different
repos doesn't mix. Searching or listing with a `project` returns that project's entries **plus
entries with no project**, so general preferences and decisions still apply everywhere. Entries
saved before this feature have no project and are treated the same way. Tell Claude to pass the
repo name as `project` when adding (or put it in your `CLAUDE.md`).

Note: It helps to be specific when asking Claude to add context to the brain as, otherwise, it can default to its own memory.

---

## CLI Usage (optional)

You can hit the Brain API directly from any terminal:

**Store a thought:**
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"content": "your thought here", "tags": ["tag1"], "source": "cli"}'
```

**Search:**
```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "what did I decide about X", "limit": 5}'
```

**Filters** (all optional, combined with AND):

| Field | Meaning |
|-------|---------|
| `project` | This project's entries plus unscoped ones; set `"include_unscoped": false` for this project only |
| `type` | `decision`, `idea`, `meeting`, `action_item`, `reference`, `question`, `reflection`, `other` |
| `tag` | Exact tag |
| `source_filter` | Exact source, e.g. `mcp` |
| `created_after`, `created_before` | ISO 8601 timestamps |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "linting", "project": "open-brain", "type": "decision"}'
```

**Edit an entry** (only the fields you send change; changing `content` re-embeds it and
regenerates its metadata; `project: ""` removes the project; `"reextract": true` re-runs metadata
extraction alone, e.g. for entries marked `metadata_status: failed`):
```bash
curl -X PATCH http://localhost:8000/entries/<id> \
  -H "Content-Type: application/json" \
  -d '{"tags": ["decision"], "project": "open-brain"}'
```

**Export everything** as JSONL (one entry per line, no vectors, so it works with any embedding
model). This is the backup route that doesn't depend on Docker volumes:
```bash
curl -o brain-backup.jsonl http://localhost:8000/export
```

**Restore or move a brain** from an export file. Entries are re-embedded with your current
model, ids and dates are kept, and ids that already exist are skipped (add `?overwrite=true` to
replace them), so running it twice is safe. Entries without usable metadata are re-extracted;
otherwise the saved metadata is reused. The response lists any bad lines:
```bash
curl -X POST http://localhost:8000/import --data-binary @brain-backup.jsonl
```

**List recent entries** (newest first, `limit` 1–100). Accepts `project`, `include_unscoped`,
`type`, `tag`, `source`, `after`, and `before`. To page, pass the previous response's
`next_before` as `before`; it is `null` on the last page:
```bash
curl "http://localhost:8000/entries?limit=10&project=open-brain"
```

`POST /ingest` also accepts an optional `"project"` field.

---

## Stopping / Starting

```bash
docker compose down      # stop (data persists in volume)
docker compose up -d     # start again
docker compose down -v   # stop AND wipe all data
```

---

## Troubleshooting

**Brain API can't reach Ollama:**
Check that Ollama is running where `OLLAMA_HOST` points (host Ollama by default:
`curl http://localhost:11434/api/tags`) and that `nomic-embed-text` has been pulled.
On Linux with host Ollama, it must listen on an address reachable from containers.

**Entries have no type/topics:**
The metadata model (`llama3.2` by default) isn't installed or failed to respond.
Pull it, or point `OLLAMA_LLM_MODEL` at an installed model, then check
`docker compose logs brain-api` for `[metadata]` messages.

**`ports are not available ... 11434`:**
Host Ollama already uses that port. Leave the `ollama` container's port unpublished
(the default) or stop the host Ollama.

**Web UI shows "offline" or requests fail with CORS errors:**
Open the UI at `http://localhost:5173` (or add your URL to `CORS_ORIGINS`), and make
sure the Brain API is up: `curl http://localhost:8000/health`.

**MCP not showing in Claude Code:**
- Double-check the port is `3001` and the config `type` is `http`
- Confirm `~/.claude.json` (not `~/.claude/claude.json`) contains the `mcpServers` entry
- Check the server is up: `docker compose logs mcp-server`
- Restart Claude Code fully after any config changes
