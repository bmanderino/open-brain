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
  missing, entries are still stored but get type `other` and no extracted metadata.
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

- **`search_brain`** — semantic search over everything you've stored
- **`add_to_brain`** — store thoughts/decisions during a session
- **`list_brain`** — see recent entries
- **`brain_stats`** — totals, entries by source, top topics, and top people

Claude cannot delete entries; use the web UI for that.

Example prompts in Claude Code:
- "Search my brain for anything about the RPG game architecture"
- "Add to my brain that I decided to use Qdrant over Pinecone because of the Docker-native setup"
- "Before we start, check my brain for any context on this project"

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
