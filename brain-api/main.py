import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


# Routes

@app.get("/health")
async def health():
    return {"status": "ok", "collection": COLLECTION, "embed_model": EMBED_MODEL}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    embedding = await get_embedding(req.content)
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