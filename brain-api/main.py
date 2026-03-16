import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

# Config

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", 11434))
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")
COLLECTION = os.getenv("COLLECTION_NAME", "brain")
EMBED_DIM = 768  # nomic-embed-text output dimension

OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

# App

app = FastAPI(title="Open Brain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


class IngestResponse(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
    created_at: str
    metadata: Metadata


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5
    source_filter: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
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


# Routes

@app.get("/health")
async def health():
    return {"status": "ok", "collection": COLLECTION, "embed_model": EMBED_MODEL}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Run embedding and metadata extraction concurrently
    embedding, metadata = await asyncio.gather(
        get_embedding(req.content),
        extract_metadata(req.content),
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
                    "tags": req.tags,
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
        tags=req.tags,
        created_at=created_at,
        metadata=metadata,
    )


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    embedding = await get_embedding(req.query)

    query_filter = None
    if req.source_filter:
        query_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=req.source_filter))]
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
async def list_entries(limit: int = 20, offset: int = 0):
    results, _ = qdrant.scroll(
        collection_name=COLLECTION,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    entries = [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "source": r.payload.get("source", "unknown"),
            "tags": r.payload.get("tags", []),
            "created_at": r.payload.get("created_at", ""),
            "type": r.payload.get("type", "other"),
            "topics": r.payload.get("topics", []),
            "people": r.payload.get("people", []),
            "action_items": r.payload.get("action_items", []),
        }
        for r in results
    ]
    entries.sort(key=lambda x: x["created_at"], reverse=True)
    return {"entries": entries, "count": len(entries)}


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
