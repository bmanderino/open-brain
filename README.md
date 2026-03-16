# Open Brain

A database-backed, MCP-connected personal knowledge system. Drop thoughts in via
the web UI or CLI, search them semantically, and give Claude Code access to your
accumulated context via MCP.

## Stack

| Service     | Port  | Role                              |
|-------------|-------|-----------------------------------|
| Ollama      | 11434 | Embeddings (nomic-embed-text)     |
| Qdrant      | 6333  | Vector database                   |
| Brain API   | 8000  | Ingest + search (FastAPI)         |
| MCP Server  | 3001  | Claude Code integration           |
| Web UI      | 5173  | Browser capture + search          |

All services run via Docker Compose.

---

## Setup

### 1. Start the stack

```bash
docker compose up -d
```

First run will build the images — takes a few minutes. After that, restarts are instant.

Check everything is up:

```bash
docker compose ps
```

### 2. Pull the embedding model

After the stack is running, pull the embedding model into the Ollama container:

```bash
docker exec ollama ollama pull nomic-embed-text
```

This only needs to be done once — the model is stored in the `ollama-data` volume.

Verify the Brain API is healthy:
```bash
curl http://localhost:8000/health
```

### 3. Connect Claude Code

#### CLI (recommended)

Edit (or create) `~/.claude.json`:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "sse",
      "url": "http://localhost:3001/mcp"
    }
  }
}
```

Restart Claude Code. You should see `open-brain` in the available tools.

#### Remote (e.g. connecting from a Mac to a Windows host)

Find your Windows machine's local IP:

```powershell
ipconfig
```

Look for the IPv4 address on your main network adapter (e.g. `192.168.1.42`).

Edit (or create) `~/.claude.json` on your Mac:

```json
{
  "mcpServers": {
    "open-brain": {
      "type": "sse",
      "url": "http://YOUR_WINDOWS_IP:3001/mcp"
    }
  }
}
```

Restart Claude Code. You should see `open-brain` in the available tools.

### 4. Access the Web UI

Local:
```
http://localhost:5173
```

From a remote machine: `http://YOUR_WINDOWS_IP:5173`

---

## Using with Claude Code

Once connected, Claude Code can:

- **`search_brain`** — semantic search over everything you've stored
- **`add_to_brain`** — store thoughts/decisions during a session
- **`list_brain`** — see recent entries

Example prompts in Claude Code:
- "Search my brain for anything about the RPG game architecture"
- "Add to my brain that I decided to use Qdrant over Pinecone because of the Docker-native setup"
- "Before we start, check my brain for any context on this project"

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
Ollama runs as part of the stack on the `brain-net` Docker network. If embeddings
fail, check the `ollama` container is running (`docker compose ps`) and that
`nomic-embed-text` has been pulled (`docker exec ollama ollama pull nomic-embed-text`).

**Mac can't reach Windows services:**
Make sure Windows Firewall allows inbound connections on ports 3001, 5173, 8000.
You can add rules in Windows Defender Firewall → Inbound Rules.

**MCP not showing in Claude Code:**
- Double-check the port is `3001`
- Confirm `~/.claude.json` (not `~/.claude/claude.json`) contains the `mcpServers` entry
- Restart Claude Code fully after any config changes
