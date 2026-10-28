# Open Brain

A database-backed, MCP-connected personal knowledge system. Drop thoughts in via
the web UI or CLI, search them semantically, and give Claude Code access to your
accumulated context via MCP.

## Stack

| Service     | Port  | Role                                                      |
|-------------|-------|-----------------------------------------------------------|
| Ollama      | 11434 | Embeddings (`nomic-embed-text`) + metadata (`qwen3:14b`)  |
| Qdrant      | 6333  | Vector database                                           |
| Brain API   | 8000  | Ingest + search (FastAPI, Python)                         |
| MCP Server  | 3001  | Claude Code integration (Python, streamable HTTP)         |
| Web UI      | 5173  | Browser capture + search                                  |
| Open WebUI  | 8080  | Optional: chat with your local Ollama models (not part of Open Brain itself) |

All services run via Docker Compose. Every published port is bound to `127.0.0.1`,
so the stack is reachable from your machine only. There is **no authentication**,
so don't expose these ports to a network you don't trust.

By default the Brain API uses an **Ollama installed on your host** (reached via
`host.docker.internal`). The compose file also defines an `ollama` container, but it
doesn't publish a port and isn't used unless you switch to it (see below).

**Open WebUI** (<http://localhost:8080>) is an optional extra bundled in the compose file: a chat
interface for the Ollama models on your machine. It doesn't read or write the brain, but it is a
convenient way to try the models and see what runs locally. Remove the `open-webui` service from
`docker-compose.yml` if you don't want it (its image takes about 6 GB of disk).

---

## Prerequisites

- **Docker** with Compose v2 (`docker compose`, not `docker-compose`). Tested with Docker 29 and Compose 5.
- **Ollama 0.9.0 or later**, on the host (default) or in a container. Metadata extraction sends
  `think: false` so `qwen3` doesn't spend its output on reasoning, and older Ollama versions don't support that.
- **Disk and memory:** about 9 GB for `qwen3:14b` plus a small one for `nomic-embed-text`, and enough RAM to
  hold the 14B model in memory (more than 9 GB free, so 16 GB machines will be tight). The first
  `docker compose up` also needs roughly 13 GB of disk for images (the unused `ollama` container, about 7 GB, and
  Open WebUI, about 6 GB, as measured on disk). On a small
  machine, use a smaller `OLLAMA_LLM_MODEL` (see step 3) and remove the services you don't need.
- **Claude Code**, to use the MCP tools. The API and web UI work without it.

## Quick start

```bash
docker compose up -d                 # build and start everything
ollama pull nomic-embed-text         # embeddings (required)
ollama pull qwen3:14b                # metadata extraction (~9 GB)
curl http://localhost:8000/health    # expect "status": "ok"
claude mcp add --scope user --transport http open-brain http://localhost:3001/mcp
```

Then restart Claude Code and open <http://localhost:5173>. Step 6 below adds the hook that loads your
brain at the start of every session. The sections that follow explain each step and the alternatives
(an Ollama container instead of host Ollama, other models).

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
- `qwen3:14b` (about 9 GB) — extracts each entry's type, topics, people, and action items. If it's
  missing or too slow (the call times out after `METADATA_TIMEOUT` seconds, default 60, which
  matters for a cold model load), entries are still stored but get type `other` and no extracted
  metadata. Such entries are marked `metadata_status: failed`, and `add_to_brain` says so.
  To use a different model you already have, set `OLLAMA_LLM_MODEL` on `brain-api`. On a small
  machine, `llama3.2` (2 GB) still works but labels much worse: in a 21-entry comparison it got
  19% of types right with the original prompt, against 71% for `qwen3:14b` with the current one.
  `mistral-small3.2` (15 GB) scored a little higher on types but is about twice as slow.

With host Ollama:

```bash
ollama pull nomic-embed-text
ollama pull qwen3:14b
```

With the Ollama container:

```bash
docker exec ollama ollama pull nomic-embed-text
docker exec ollama ollama pull qwen3:14b
```

This only needs to be done once per model.

Verify the Brain API is healthy:
```bash
curl http://localhost:8000/health
```

`/health` always returns HTTP 200 while the API is running, and reports whether its
dependencies are usable: `status` is `ok` or `degraded`, with `qdrant` and `ollama` details
(Ollama reachable, and the embedding and metadata models installed).

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
Alternatively: `claude mcp add --scope user --transport http open-brain http://localhost:3001/mcp`.

Restart Claude Code. You should see `open-brain` in the available tools.

### 5. Access the Web UI

```
http://localhost:5173
```

The Brain API only accepts browser requests from the web UI's origins. If you serve
the UI from a different URL, set `CORS_ORIGINS` (comma-separated) on `brain-api`.

### 6. Load your brain at the start of every session (recommended)

Without a hook the brain is only used when someone remembers to ask. Add this to
`~/.claude/settings.json` (merge it with any existing `hooks`) and every Claude Code session starts with the
pinned and recent entries for that repo:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "curl -sfG --max-time 5 http://localhost:8000/context --data-urlencode \"project=$(basename \"$CLAUDE_PROJECT_DIR\")\" --data-urlencode format=text || true; grep -qsiE 'open.?brain|add_to_brain' \"$CLAUDE_PROJECT_DIR/CLAUDE.md\" \"$CLAUDE_PROJECT_DIR/AGENTS.md\" || { echo; echo 'Note: this repo has no CLAUDE.md or AGENTS.md reference to Open Brain. Offer to add a short section: when saving with add_to_brain pass project=<repo folder name>, and use search_brain and list_brain with the same project. Ask the user before editing the file.'; }"
          }
        ]
      }
    ]
  }
}
```

If the repo's `CLAUDE.md` or `AGENTS.md` doesn't mention Open Brain yet, the hook also tells Claude to
offer adding a short usage section, and to ask before editing. How the context is built, and what hooks
can and can't do, is under [Loading context automatically](#loading-context-automatically-sessionstart-hook).

---

## Using with Claude Code

Once connected, Claude Code can:

- **`get_context`** — pinned entries plus the most recent ones for a project, in one compact response; meant for the start of a session
- **`search_brain`** — semantic search over everything you've stored; optional `project`, `type`, `tag`, `source` filters
- **`add_to_brain`** — store thoughts/decisions during a session; optional `tags`, `project`, and `pinned`
- **`list_brain`** — see recent entries, newest first; optional `project`, `type`, `tag`, `pinned` filters
- **`update_brain_entry`** — fix an entry's content, tags, project, pinned state, or its extracted type/topics/people/action items, or re-run metadata extraction
- **`related_to`** — entries similar to a given one, computed when called
- **`supersede_brain_entry`** — mark an entry as replaced by a newer one so it stops appearing in searches
- **`brain_stats`** — totals, entries by source, top topics, and top people

Claude cannot delete entries; use the web UI for that. The web UI can also pin and unpin entries,
show related entries, mark an entry outdated, and restore superseded ones (see the sections below).

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

### Superseding outdated entries

Dedup only catches near-identical text. When a decision changes ("Postgres" in March, "SQLite" in
October), both entries stay live unless you retire the old one. After storing the new entry, call
`supersede_brain_entry(old_id, new_id)` (or `PATCH /entries/{old_id}` with `{"superseded_by": new_id}`).
The old entry is kept but hidden from search, list, `get_context` and dedup. Pass
`include_superseded=True` to `search_brain` and `list_brain` (`"include_superseded": true` on
`/search`, `?include_superseded=true` on `/entries`) to see it, marked `superseded by <id>`. Undo it with
`supersede_brain_entry(old_id, "")`. Deleting the replacement restores the entries it replaced.

To help find what to retire, every new entry's response lists up to three similar existing entries
(same project, not superseded) as `possibly_supersedes`, with id, date and similarity, and `add_to_brain`
shows them as "Possibly replaces". Nothing is superseded automatically: a wrong guess would silently hide a
good entry, so the caller decides. Only entries scoring at least `NEIGHBOR_MIN_SCORE` (default `0.6`, set on
`brain-api`) are listed; that default is a guess, not tuned on real entries. `superseded_by` is kept by
`/export` and `/import`.

### Related entries

`related_to(entry_id)` (or `GET /entries/{id}/related`) returns the entries closest to a given one,
most similar first, with date and similarity. It is computed on read from the entry's own
vector, so nothing is stored and there are no links to go stale or to export. Defaults: up to 5
results (`limit`, 1-20) at a similarity of at least `RELATED_MIN_SCORE` (default `0.5`, an untuned
guess; `min_score` overrides it per request). Scope follows `get_context`: an entry with a project sees
that project plus unscoped entries, and an unscoped entry sees only unscoped ones. Superseded entries
are hidden unless `include_superseded` is set. The web UI has a "related" button on every entry.

### Projects

Entries can be tagged with a `project` (for example the repo name) so context from different
repos doesn't mix. Searching or listing with a `project` returns that project's entries **plus
entries with no project**, so general preferences and decisions still apply everywhere. Entries
saved before this feature have no project and are treated the same way. Tell Claude to pass the
repo name as `project` when adding (or put it in your `CLAUDE.md`).

### Pinned entries and session context

Some facts should be in front of Claude every session, not found only when a search happens to
match: "use pnpm, not npm", "this repo targets Windows", "avoid em dashes in docs". Mark them
**pinned** (`pinned=True` on `add_to_brain`, or `update_brain_entry(entry_id, pinned=True)` on an
existing entry; `"pinned": true` on `POST /ingest` and `PATCH /entries/{id}`). Keep pins few and short.

`get_context` (or `GET /context?project=<name>`) returns the pinned entries first, then the five
newest others, for that project plus entries with no project. A pin with no project is global and
shows up everywhere; a pin with a project shows up only there. Without a `project`, only entries
with no project are returned. At most 20 pins are shown (`max_pinned`), and the response says
when more were hidden. `recent` sets how many recent entries follow (default 5). Add
`format=text` for compact plain text, or leave it off for JSON (`pinned`, `pinned_total`,
`recent`). Pins are kept by `/export` and `/import`.

#### Loading context automatically (SessionStart hook)

The hook itself is Setup [step 6](#6-load-your-brain-at-the-start-of-every-session-recommended). It
goes in `~/.claude/settings.json` so it applies to every repo (or in `.claude/settings.json` of a single
repo, but not both, or the context is injected twice). The project name is the repo folder name.

Claude Code adds a `SessionStart` hook's output to the session as context. The command prints
nothing, and does not fail the session, if the API is down. The context text ends with a reminder
to save decisions with `add_to_brain` and the project name, which is how saving gets prompted.
Your `CLAUDE.md` should still say to pass `project` when saving.

The hook command also ends with a check: if neither `CLAUDE.md` nor `AGENTS.md` in the repo
mentions Open Brain (`open brain`, `open-brain` or `add_to_brain`), it prints a one-line note
telling Claude to offer adding a short section (pass `project` when saving, search with the same
project) and to ask before editing. Once the file mentions Open Brain the note disappears, so
it costs nothing in configured repos. The snippet above is the full command; copy it as is.

What hooks can't do: per Claude Code's hook docs, only `SessionStart` and `UserPromptSubmit`
output reaches the model, so a `SessionEnd` or `PreCompact` hook cannot nudge Claude to save
anything. A `Stop` hook can make Claude continue, but it fires after every turn, so it is too
noisy to use for capture. That's why the reminder lives in the injected context instead.

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

The extracted metadata can be corrected by hand with `type`, `topics`, `people`, and `action_items`
(a list replaces the old one and `[]` clears it). This is the fix for things the local model gets
wrong, such as a tool name listed under people. Edited entries are marked
`metadata_status: "manual"`; a later `reextract` would overwrite your edits.

```bash
curl -X PATCH http://localhost:8000/entries/<id> \
  -H "Content-Type: application/json" \
  -d '{"type": "decision", "people": []}'
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

## Running the tests and lint

The API tests run against an in-memory Qdrant with Ollama faked, so they need no running stack:

```bash
cd brain-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

They cover ordering and paging, filters, dedup, hybrid search, metadata failures, edit/delete,
export/import, pinning and session context, and health.

The MCP server has its own tests (`mcp-server/`, same commands, needs Python 3.10+). They call the
tools with the HTTP layer faked and check the requests sent to the Brain API and the text returned
to Claude. The web UI has no tests yet.

Lint with [ruff](https://docs.astral.sh/ruff/) (installed by `requirements-dev.txt`; config in
`ruff.toml`) from the repo root:

```bash
ruff check .
```

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes to `main` and on pull requests:
ruff, the API tests and MCP server tests (Python 3.12), a web UI production build, and `docker compose config`
to validate the compose file.

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
The metadata model (`qwen3:14b` by default) isn't installed or failed to respond.
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
