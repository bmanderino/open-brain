import os
import httpx
from mcp.server.fastmcp import FastMCP

BRAIN_API_URL = os.getenv("BRAIN_API_URL", "http://brain-api:8000")

port = int(os.getenv("PORT", "3000"))
mcp = FastMCP("open-brain", host="0.0.0.0", port=port)


@mcp.tool()
async def search_brain(query: str, limit: int = 5) -> str:
    """Search your personal Open Brain knowledge base using semantic search.
    Use this to recall past thoughts, decisions, notes, or anything stored.
    Phrase the query naturally, e.g. 'RPG game architecture decisions' or 'why I chose FastAPI'.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BRAIN_API_URL}/search",
            json={"query": query, "limit": limit},
        )
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
            lines.append(f"{i}. (score: {r['score']:.3f} | {date} | via {r['source']}{tags})")
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
async def add_to_brain(content: str, tags: list[str] = []) -> str:
    """Store a thought, decision, note, or piece of information into the Open Brain knowledge base.
    Use this to save things worth remembering -- architectural decisions, ideas, things learned, etc.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BRAIN_API_URL}/ingest",
            json={"content": content, "tags": tags, "source": "mcp"},
        )
        if resp.status_code != 200:
            return f"Error storing in brain: {resp.text}"

        data = resp.json()
        tag_str = f"\nTags: {', '.join(tags)}" if tags else ""

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
        meta_str = ("\n" + "\n".join(meta_parts)) if meta_parts else ""

        return f"Stored in brain (id: {data['id']})\n\n\"{content}\"{tag_str}{meta_str}"


@mcp.tool()
async def list_brain(limit: int = 10) -> str:
    """List the most recent entries in the Open Brain knowledge base."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BRAIN_API_URL}/entries?limit={limit}")
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
            lines.append(f"{i}. ({date} | {e['source']}{tags})")
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
