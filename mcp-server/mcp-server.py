import os

import httpx
from mcp.server.fastmcp import FastMCP

BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://brain-api:8000")

port = int(os.getenv("PORT", "3000"))
mcp = FastMCP("open-brain", host="0.0.0.0", port=port)


@mcp.tool()
async def search_brain(
    query: str,
    limit: int = 5,
    project: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    include_superseded: bool = False,
) -> str:
    """Search your personal Open Brain knowledge base using semantic search.
    Use this to recall past thoughts, decisions, notes, or anything stored.
    Phrase the query naturally, e.g. 'RPG game architecture decisions' or 'why I chose FastAPI'.
    Exact terms such as names, identifiers and error strings are matched too, alongside meaning.

    Optional filters: project (the current repo/project name; also returns entries not tied
    to any project, such as general preferences), type (decision, idea, meeting, action_item,
    reference, question, reflection, other), tag (exact tag), source (e.g. 'mcp', 'web-ui').

    Entries that a newer entry replaced (see supersede_brain_entry) are hidden. Set
    include_superseded=True to see them too, e.g. to audit how a decision changed.
    """
    body = {"query": query, "limit": limit}
    if include_superseded:
        body["include_superseded"] = True
    if project:
        body["project"] = project
    if type:
        body["type"] = type
    if tag:
        body["tag"] = tag
    if source:
        body["source_filter"] = source
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{BRAIN_API_URL}/search", json=body)
        if resp.status_code != 200:
            return f"Error searching brain: {resp.text}"

        data = resp.json()
        results = data.get("results", [])

        if not results:
            return f"No results found for: '{query}'"

        lines = []
        for i, r in enumerate(results, 1):
            tags = f" [{', '.join(r['tags'])}]" if r.get("tags") else ""
            date = r.get("created_at", "")[:10] if r.get("created_at") else "unknown"
            proj = f" | project: {r['project']}" if r.get("project") else ""
            kw = " | exact-term match" if r.get("match") in ("keyword", "both") else ""
            pin = " | pinned" if r.get("pinned") else ""
            if r.get("superseded_by"):
                pin += f" | superseded by {r['superseded_by']}"
            lines.append(f"{i}. [{r['id']}] (score: {r['score']:.3f}{kw} | {date} | via {r['source']}{proj}{pin}{tags})")
            lines.append(f"   {r['content']}")

            meta = r.get("metadata", {})
            if meta.get("type") and meta["type"] != "other":
                lines.append(f"   type: {meta['type']}")
            if meta.get("topics"):
                lines.append(f"   topics: {', '.join(meta['topics'])}")
            if meta.get("people"):
                lines.append(f"   people: {', '.join(meta['people'])}")
            if meta.get("action_items"):
                lines.append(f"   actions: {'; '.join(meta['action_items'])}")
            lines.append("")

        return f"Results for '{query}':\n\n" + "\n".join(lines)


@mcp.tool()
async def add_to_brain(
    content: str,
    tags: list[str] | None = None,
    project: str | None = None,
    pinned: bool = False,
    force: bool = False,
) -> str:
    """Store a thought, decision, note, or piece of information into the Open Brain knowledge base.
    Use this to save things worth remembering -- architectural decisions, ideas, things learned, etc.

    Pass project (the current repo/project name) for anything specific to one project, so it
    doesn't surface in other projects' searches. Omit it for general preferences or knowledge
    that applies everywhere.

    Set pinned=True for a short, lasting fact that every future session in this project
    should see without searching, such as "use pnpm, not npm" or "this repo targets Windows".
    Pinned entries are shown first by get_context. Keep pins few and brief; most entries
    should not be pinned.

    Near-duplicates of an existing entry (same project) are not stored again; the tool says so
    and returns the existing entry. Set force=True only if the new entry is genuinely different.

    If the new entry is close to existing ones, they are listed as "Possibly replaces". When the
    new entry changes or reverses one of them (a decision that flipped, a preference that
    changed), call supersede_brain_entry so the old one stops showing up in searches.
    """
    tags = tags or []
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BRAIN_API_URL}/ingest",
            json={
                "content": content, "tags": tags, "source": "mcp", "project": project,
                "force": force, **({"pinned": True} if pinned else {}),
            },
        )
        if resp.status_code != 200:
            return f"Error storing in brain: {resp.text}"

        data = resp.json()
        if data.get("duplicate_of"):
            hint = "" if data.get("pinned") or not pinned else (
                " To pin the existing entry instead, call update_brain_entry with pinned=True."
            )
            return (
                f"Not stored: a near-duplicate already exists (id: {data['duplicate_of']}, "
                f"similarity {data['duplicate_score']:.3f}).\n\n\"{data['content']}\"\n\n"
                f"Use force=True if this is genuinely a different entry.{hint}"
            )
        tag_str = f"\nTags: {', '.join(tags)}" if tags else ""
        if data.get("project"):
            tag_str += f"\nProject: {data['project']}"
        if data.get("pinned"):
            tag_str += "\nPinned: yes"

        meta = data.get("metadata", {})
        meta_parts = []
        if meta.get("type") and meta["type"] != "other":
            meta_parts.append(f"Type: {meta['type']}")
        if meta.get("topics"):
            meta_parts.append(f"Topics: {', '.join(meta['topics'])}")
        if meta.get("people"):
            meta_parts.append(f"People: {', '.join(meta['people'])}")
        if meta.get("action_items"):
            meta_parts.append(f"Action items: {'; '.join(meta['action_items'])}")
        if data.get("metadata_status") == "failed":
            meta_parts.append(
                "Note: metadata extraction failed (is the Ollama LLM loaded?), "
                "so type/topics/people/action items are empty."
            )
        meta_str = ("\n" + "\n".join(meta_parts)) if meta_parts else ""

        similar = ""
        if data.get("possibly_supersedes"):
            rows = [
                f"- [{n['id']}] ({n['created_at'][:10]}, similarity {n['score']:.3f}) "
                f"{' '.join(n['content'].split())[:200]}"
                for n in data["possibly_supersedes"]
            ]
            similar = (
                "\n\nPossibly replaces (similar existing entries; if the new entry makes one "
                f"outdated, call supersede_brain_entry(old_id, \"{data['id']}\")):\n"
                + "\n".join(rows)
            )

        return f"Stored in brain (id: {data['id']})\n\n\"{content}\"{tag_str}{meta_str}{similar}"


@mcp.tool()
async def update_brain_entry(
    entry_id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    pinned: bool | None = None,
    reextract: bool = False,
    type: str | None = None,
    topics: list[str] | None = None,
    people: list[str] | None = None,
    action_items: list[str] | None = None,
) -> str:
    """Edit an existing Open Brain entry. Get entry_id from search_brain or list_brain.
    Only the fields you pass are changed. Changing content re-embeds the entry and regenerates
    its type/topics/people/action items. tags replaces all tags. project="" removes the
    project. pinned=True pins the entry (get_context always shows it) and pinned=False unpins
    it. reextract=True re-runs metadata extraction without changing content (use it on
    entries whose metadata extraction failed).

    The extracted metadata can be corrected by hand: type (decision, idea, meeting,
    action_item, reference, question, reflection, other), topics, people, action_items.
    Each list replaces the old one and [] clears it. Use this when the automatic labels are
    wrong, e.g. a tool name listed under people. Hand-edited entries are marked metadata_status
    "manual".
    """
    body: dict = {"reextract": reextract}
    if content is not None:
        body["content"] = content
    if tags is not None:
        body["tags"] = tags
    if project is not None:
        body["project"] = project
    if pinned is not None:
        body["pinned"] = pinned
    for key, value in (
        ("type", type), ("topics", topics), ("people", people), ("action_items", action_items),
    ):
        if value is not None:
            body[key] = value
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.patch(f"{BRAIN_API_URL}/entries/{entry_id}", json=body)
        if resp.status_code == 404:
            return f"No entry with id {entry_id}"
        if resp.status_code != 200:
            return f"Error updating entry: {resp.text}"
        e = resp.json()
        parts = [f"Updated entry {e['id']}", f"\"{e['content']}\""]
        if e.get("project"):
            parts.append(f"Project: {e['project']}")
        if e.get("pinned"):
            parts.append("Pinned: yes")
        if e.get("tags"):
            parts.append(f"Tags: {', '.join(e['tags'])}")
        if e.get("type") and e["type"] != "other":
            parts.append(f"Type: {e['type']}")
        if e.get("topics"):
            parts.append(f"Topics: {', '.join(e['topics'])}")
        if e.get("people"):
            parts.append(f"People: {', '.join(e['people'])}")
        if e.get("action_items"):
            parts.append(f"Action items: {'; '.join(e['action_items'])}")
        if e.get("metadata_status") == "failed":
            parts.append("Note: metadata extraction failed; try reextract=True later.")
        return "\n".join(parts)


@mcp.tool()
async def supersede_brain_entry(old_id: str, new_id: str) -> str:
    """Mark an entry as outdated because a newer entry replaces it, e.g. a decision that was
    reversed. The old entry is hidden from search_brain, list_brain and get_context but stays
    stored; pass include_superseded=True to those tools to see it. Get ids from search_brain,
    list_brain, or the "Possibly replaces" list that add_to_brain returns. Store the new entry
    first, then call this with the old entry's id and the new entry's id.

    To undo it, pass new_id="" and the old entry shows up again.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(
            f"{BRAIN_API_URL}/entries/{old_id}", json={"superseded_by": new_id}
        )
        if resp.status_code == 404:
            return f"No entry with id {old_id}"
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            return f"Not superseded: {detail}"
        if resp.status_code != 200:
            return f"Error superseding entry: {resp.text}"
        e = resp.json()
        if not e.get("superseded_by"):
            return f"Restored entry {e['id']}; it shows up in searches again."
        return (
            f"Entry {e['id']} is now superseded by {e['superseded_by']} and hidden from "
            "search, list and context.\n\n"
            f"\"{e['content']}\""
        )


@mcp.tool()
async def get_context(project: str | None = None, recent: int = 5) -> str:
    """Get the context worth knowing at the start of work: pinned entries first, then the most
    recent entries, for one project plus anything not tied to a project. Call this at the start
    of a session or task, passing the current repo/project name as project. It is compact on
    purpose; use search_brain to dig for anything specific. Without project, returns only
    entries not tied to a project.
    """
    params: dict = {"recent": recent, "format": "text"}
    if project:
        params["project"] = project
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BRAIN_API_URL}/context", params=params)
        if resp.status_code != 200:
            return f"Error fetching context: {resp.text}"
        return resp.text


@mcp.tool()
async def list_brain(
    limit: int = 10,
    project: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    pinned: bool = False,
    include_superseded: bool = False,
) -> str:
    """List the most recent entries in the Open Brain knowledge base, newest first.
    Optional filters: project (also includes entries not tied to any project),
    type (decision, idea, meeting, action_item, reference, question, reflection, other),
    tag (exact tag), pinned=True (only pinned entries). Superseded entries are hidden unless
    include_superseded=True.
    """
    params: dict = {"limit": limit}
    if include_superseded:
        params["include_superseded"] = "true"
    if pinned:
        params["pinned"] = "true"
    if project:
        params["project"] = project
    if type:
        params["type"] = type
    if tag:
        params["tag"] = tag
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BRAIN_API_URL}/entries", params=params)
        if resp.status_code != 200:
            return f"Error listing brain: {resp.text}"

        data = resp.json()
        entries = data.get("entries", [])

        if not entries:
            return "Your brain is empty. Add something with add_to_brain!"

        lines = []
        for i, e in enumerate(entries, 1):
            tags = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
            date = e.get("created_at", "")[:10] if e.get("created_at") else "unknown"
            proj = f" | project: {e['project']}" if e.get("project") else ""
            pin = " | pinned" if e.get("pinned") else ""
            if e.get("superseded_by"):
                pin += f" | superseded by {e['superseded_by']}"
            lines.append(f"{i}. [{e['id']}] ({date} | {e['source']}{proj}{pin}{tags})")
            lines.append(f"   {e['content']}")

            meta_type = e.get("type", "other")
            topics = e.get("topics", [])
            people = e.get("people", [])
            if meta_type and meta_type != "other":
                lines.append(f"   type: {meta_type}")
            if topics:
                lines.append(f"   topics: {', '.join(topics)}")
            if people:
                lines.append(f"   people: {', '.join(people)}")
            lines.append("")

        return "Recent brain entries:\n\n" + "\n".join(lines)


@mcp.tool()
async def brain_stats() -> str:
    """Get aggregate statistics about the Open Brain knowledge base:
    total entry count, breakdown by source, top topics, and top people mentioned.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BRAIN_API_URL}/stats")
        if resp.status_code != 200:
            return f"Error fetching brain stats: {resp.text}"

        d = resp.json()
        lines = [f"Brain Stats — {d['total']} total entries\n"]

        if d.get("by_source"):
            lines.append("By source:")
            for src, count in sorted(d["by_source"].items(), key=lambda x: -x[1]):
                lines.append(f"  {src}: {count}")
            lines.append("")

        if d.get("top_topics"):
            lines.append("Top topics:")
            for item in d["top_topics"]:
                lines.append(f"  {item['topic']}: {item['count']}")
            lines.append("")

        if d.get("top_people"):
            lines.append("Top people mentioned:")
            for item in d["top_people"]:
                lines.append(f"  {item['person']}: {item['count']}")

        return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
