import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
    OrderBy,
    Direction,
    DatetimeRange,
    IsEmptyCondition,
    PayloadField,
)

# Config

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", 11434))
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")
COLLECTION = os.getenv("COLLECTION_NAME", "brain")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", 0.92))  # cosine score; >1 disables
EMBED_DIM = 768  # nomic-embed-text output dimension

OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

# App

app = FastAPI(title="Open Brain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# Startup

@app.on_event("startup")
async def startup():
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection: {COLLECTION}")
    else:
        print(f"Collection '{COLLECTION}' already exists")
    # Idempotent; needed for order_by on created_at in GET /entries
    qdrant.create_payload_index(
        collection_name=COLLECTION,
        field_name="created_at",
        field_schema=PayloadSchemaType.DATETIME,
    )
    for field in ("project", "type", "source", "tags"):
        qdrant.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )


# Models

class Metadata(BaseModel):
    type: str = "other"
    topics: list[str] = []
    people: list[str] = []
    action_items: list[str] = []

    @field_validator("type")
    @classmethod
    def coerce_type(cls, v: str) -> str:
        valid = {"decision", "idea", "meeting", "action_item", "reference", "question", "reflection", "other"}
        return v if v in valid else "other"


class IngestRequest(BaseModel):
    content: str
    source: Optional[str] = "manual"
    tags: Optional[list[str]] = []
    project: Optional[str] = None
    force: bool = False  # skip the near-duplicate check


class IngestResponse(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
    project: Optional[str] = None
    created_at: str
    metadata: Metadata
    duplicate_of: Optional[str] = None  # set when an existing near-duplicate was returned instead
    duplicate_score: Optional[float] = None


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = Field(5, ge=1, le=100)
    source_filter: Optional[str] = None
    project: Optional[str] = None
    include_unscoped: bool = True
    type: Optional[str] = None
    tag: Optional[str] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
    project: Optional[str] = None
    created_at: str
    score: float
    metadata: Metadata


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


# Helpers

async def get_embedding(text: str) -> list[float]:
    """Call Ollama to embed text using the current /api/embed endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama embedding failed: {resp.text}"
            )
        data = resp.json()
        # /api/embed returns embeddings as a list of vectors
        return data["embeddings"][0]


EXTRACTION_PROMPT = """Extract metadata from the following text and respond with ONLY valid JSON — no explanation, no markdown.

JSON schema:
{{
  "type": "one of: decision, idea, meeting, action_item, reference, question, reflection, other",
  "topics": ["list of short topic strings"],
  "people": ["list of person names mentioned"],
  "action_items": ["list of follow-up actions"]
}}

Text:
\"\"\"
{content}
\"\"\"
"""


async def extract_metadata(content: str) -> Metadata:
    """Call Ollama /api/generate with JSON format to extract structured metadata.
    Falls back to empty Metadata on any failure — never raises."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": LLM_MODEL,
                    "prompt": EXTRACTION_PROMPT.format(content=content),
                    "format": "json",
                    "stream": False,
                },
            )
            if resp.status_code != 200:
                print(f"[metadata] Ollama generate failed: {resp.status_code}")
                return Metadata()
            data = resp.json()
            raw = data.get("response", "{}")
            parsed = json.loads(raw)
            return Metadata(
                type=parsed.get("type", "other"),
                topics=parsed.get("topics", []),
                people=parsed.get("people", []),
                action_items=parsed.get("action_items", []),
            )
    except Exception as e:
        print(f"[metadata] extraction failed (graceful fallback): {e}")
        return Metadata()


def parse_timestamp(value: Optional[str], name: str) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be an ISO 8601 timestamp")
    return value


def build_filter(
    project: Optional[str] = None,
    include_unscoped: bool = True,
    type: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Optional[Filter]:
    """AND together whichever filters were given. A project filter also matches
    entries with no project (unscoped) unless include_unscoped is false."""
    must = []
    if project:
        match = FieldCondition(key="project", match=MatchValue(value=project))
        if include_unscoped:
            unscoped = IsEmptyCondition(is_empty=PayloadField(key="project"))
            must.append(Filter(should=[match, unscoped]))
        else:
            must.append(match)
    if type:
        must.append(FieldCondition(key="type", match=MatchValue(value=type)))
    if tag:
        must.append(FieldCondition(key="tags", match=MatchValue(value=tag)))
    if source:
        must.append(FieldCondition(key="source", match=MatchValue(value=source)))
    after = parse_timestamp(created_after, "created_after")
    before = parse_timestamp(created_before, "created_before")
    if after or before:
        must.append(
            FieldCondition(key="created_at", range=DatetimeRange(gt=after, lt=before))
        )
    return Filter(must=must) if must else None


# Routes

@app.get("/health")
async def health():
    return {"status": "ok", "collection": COLLECTION, "embed_model": EMBED_MODEL}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Run embedding and metadata extraction concurrently
    tags = req.tags or []
    project = req.project.strip() if req.project and req.project.strip() else None

    embedding, metadata = await asyncio.gather(
        get_embedding(req.content),
        extract_metadata(req.content),
    )

    if not req.force:
        # Duplicates are judged within the same project scope (or among unscoped entries)
        if project:
            scope = FieldCondition(key="project", match=MatchValue(value=project))
        else:
            scope = IsEmptyCondition(is_empty=PayloadField(key="project"))
        top = qdrant.search(
            collection_name=COLLECTION,
            query_vector=embedding,
            limit=1,
            query_filter=Filter(must=[scope]),
            with_payload=True,
        )
        if top and top[0].score >= DEDUP_THRESHOLD:
            hit = top[0]
            return IngestResponse(
                id=str(hit.id),
                content=hit.payload["content"],
                source=hit.payload.get("source", "unknown"),
                tags=hit.payload.get("tags", []),
                project=hit.payload.get("project"),
                created_at=hit.payload.get("created_at", ""),
                metadata=Metadata(
                    type=hit.payload.get("type", "other"),
                    topics=hit.payload.get("topics", []),
                    people=hit.payload.get("people", []),
                    action_items=hit.payload.get("action_items", []),
                ),
                duplicate_of=str(hit.id),
                duplicate_score=hit.score,
            )

    entry_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    qdrant.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=entry_id,
                vector=embedding,
                payload={
                    "content": req.content,
                    "source": req.source,
                    "tags": tags,
                    **({"project": project} if project else {}),
                    "created_at": created_at,
                    "type": metadata.type,
                    "topics": metadata.topics,
                    "people": metadata.people,
                    "action_items": metadata.action_items,
                },
            )
        ],
    )

    return IngestResponse(
        id=entry_id,
        content=req.content,
        source=req.source,
        tags=tags,
        project=project,
        created_at=created_at,
        metadata=metadata,
    )


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    embedding = await get_embedding(req.query)

    query_filter = build_filter(
        project=req.project,
        include_unscoped=req.include_unscoped,
        type=req.type,
        tag=req.tag,
        source=req.source_filter,
        created_after=req.created_after,
        created_before=req.created_before,
    )

    hits = qdrant.search(
        collection_name=COLLECTION,
        query_vector=embedding,
        limit=req.limit,
        query_filter=query_filter,
        with_payload=True,
    )

    results = [
        SearchResult(
            id=str(hit.id),
            content=hit.payload["content"],
            source=hit.payload.get("source", "unknown"),
            tags=hit.payload.get("tags", []),
            project=hit.payload.get("project"),
            created_at=hit.payload.get("created_at", ""),
            score=hit.score,
            metadata=Metadata(
                type=hit.payload.get("type", "other"),
                topics=hit.payload.get("topics", []),
                people=hit.payload.get("people", []),
                action_items=hit.payload.get("action_items", []),
            ),
        )
        for hit in hits
    ]

    return SearchResponse(query=req.query, results=results)


@app.get("/entries")
async def list_entries(
    limit: int = Query(20, ge=1, le=100),
    before: Optional[str] = None,
    after: Optional[str] = None,
    project: Optional[str] = None,
    include_unscoped: bool = True,
    type: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
):
    """Newest-first. Page by passing the previous response's next_before as before."""
    query_filter = build_filter(
        project=project,
        include_unscoped=include_unscoped,
        type=type,
        tag=tag,
        source=source,
        created_after=after,
        created_before=before,
    )
    results, _ = qdrant.scroll(
        collection_name=COLLECTION,
        scroll_filter=query_filter,
        limit=limit,
        order_by=OrderBy(key="created_at", direction=Direction.DESC),
        with_payload=True,
        with_vectors=False,
    )
    entries = [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "source": r.payload.get("source", "unknown"),
            "tags": r.payload.get("tags", []),
            "project": r.payload.get("project"),
            "created_at": r.payload.get("created_at", ""),
            "type": r.payload.get("type", "other"),
            "topics": r.payload.get("topics", []),
            "people": r.payload.get("people", []),
            "action_items": r.payload.get("action_items", []),
        }
        for r in results
    ]
    next_before = entries[-1]["created_at"] if len(entries) == limit else None
    return {"entries": entries, "count": len(entries), "next_before": next_before}


@app.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str):
    qdrant.delete(
        collection_name=COLLECTION,
        points_selector=[entry_id],
    )
    return {"deleted": entry_id}


@app.get("/stats")
async def stats():
    """Aggregate statistics by scrolling all entries in Qdrant."""
    all_entries = []
    offset = None

    while True:
        batch, next_offset = qdrant.scroll(
            collection_name=COLLECTION,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_entries.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    total = len(all_entries)

    source_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    person_counts: dict[str, int] = {}

    for entry in all_entries:
        p = entry.payload
        src = p.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

        for topic in p.get("topics", []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        for person in p.get("people", []):
            person_counts[person] = person_counts.get(person, 0) + 1

    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_people = sorted(person_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total": total,
        "by_source": source_counts,
        "top_topics": [{"topic": k, "count": v} for k, v in top_topics],
        "top_people": [{"person": k, "count": v} for k, v in top_people],
    }
