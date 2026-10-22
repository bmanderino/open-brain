import asyncio
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from qdrant_client import QdrantClient
from qdrant_client.models import (
    DatetimeRange,
    Direction,
    Distance,
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchText,
    MatchValue,
    OrderBy,
    PayloadField,
    PayloadSchemaType,
    PointStruct,
    PointVectors,
    TextIndexParams,
    TextIndexType,
    TokenizerType,
    VectorParams,
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
# Seconds to wait for the LLM; a cold model load can take well over 20s
METADATA_TIMEOUT = float(os.getenv("METADATA_TIMEOUT", 60))
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", 0.92))  # cosine score; >1 disables
EMBED_DIM = 768  # nomic-embed-text output dimension

OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

# App

app = FastAPI(title="Open Brain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
    qdrant.create_payload_index(
        collection_name=COLLECTION,
        field_name="content",
        field_schema=TextIndexParams(
            type=TextIndexType.TEXT,
            tokenizer=TokenizerType.WORD,
            min_token_len=2,
            lowercase=True,
        ),
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

    @field_validator("topics", "people", "action_items", mode="before")
    @classmethod
    def clean_list(cls, v):
        """Small models return a bare string, or placeholders like "none" instead of []."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        placeholders = {"", "none", "n/a", "na", "null", "nil", "unknown"}
        return [x.strip() for x in v if isinstance(x, str) and x.strip().lower() not in placeholders]

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


class UpdateRequest(BaseModel):
    """Only fields that are sent are changed. project: null or "" clears it."""
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = None
    reextract: bool = False  # re-run metadata extraction without changing content


class IngestResponse(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
    project: Optional[str] = None
    created_at: str
    metadata: Metadata
    metadata_status: Optional[str] = None  # "ok" or "failed"; None on entries stored before this field existed
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
    mode: Literal["hybrid", "semantic"] = "hybrid"  # hybrid adds exact-term matching


class SearchResult(BaseModel):
    id: str
    content: str
    source: str
    tags: list[str]
    project: Optional[str] = None
    created_at: str
    score: float  # cosine similarity to the query
    match: str = "semantic"  # semantic | keyword | both
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


async def extract_metadata(content: str) -> tuple[Metadata, str]:
    """Call Ollama /api/generate with JSON format to extract structured metadata.
    Returns (metadata, status) where status is "ok" or "failed". On failure the
    metadata is empty; never raises."""
    try:
        async with httpx.AsyncClient(timeout=METADATA_TIMEOUT) as client:
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
                return Metadata(), "failed"
            data = resp.json()
            raw = data.get("response", "{}")
            parsed = json.loads(raw)
            metadata = Metadata(
                type=parsed.get("type", "other"),
                topics=parsed.get("topics", []),
                people=parsed.get("people", []),
                action_items=parsed.get("action_items", []),
            )
            return metadata, "ok"
    except Exception as e:
        print(f"[metadata] extraction failed ({type(e).__name__}): {e}")
        return Metadata(), "failed"


def entry_dict(entry_id, payload: dict) -> dict:
    """Flat entry shape returned by /entries and PATCH /entries/{id}."""
    return {
        "id": str(entry_id),
        "content": payload["content"],
        "source": payload.get("source", "unknown"),
        "tags": payload.get("tags", []),
        "project": payload.get("project"),
        "created_at": payload.get("created_at", ""),
        "type": payload.get("type", "other"),
        "topics": payload.get("topics", []),
        "people": payload.get("people", []),
        "action_items": payload.get("action_items", []),
        "metadata_status": payload.get("metadata_status"),
    }


def get_point(entry_id: str, with_vectors: bool = False):
    """Fetch one point or raise 422 (malformed id) / 404 (missing)."""
    try:
        uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="entry id must be a UUID") from None
    found = qdrant.retrieve(
        collection_name=COLLECTION,
        ids=[entry_id],
        with_payload=True,
        with_vectors=with_vectors,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Entry not found")
    return found[0]


def parse_timestamp(value: Optional[str], name: str) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be an ISO 8601 timestamp") from None
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


STOPWORDS = {
    "the", "an", "is", "are", "was", "were", "to", "of", "in", "on", "for", "and", "or",
    "it", "this", "that", "with", "as", "at", "by", "be", "do", "does", "did", "what",
    "which", "who", "why", "how", "when", "where", "me", "my", "we", "our", "about",
}
RRF_K = 60


def tokenize(text: str) -> list[str]:
    """Mirror the Qdrant word tokenizer used by the content text index."""
    return [t for t in re.findall(r"\w+", text.lower()) if len(t) >= 2]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def keyword_search(query: str, query_filter: Optional[Filter], limit: int) -> list:
    """Exact-term matches ranked with BM25 (Qdrant 1.11 has no built-in BM25).
    Candidates are points whose content contains any query term."""
    terms = [t for t in dict.fromkeys(tokenize(query)) if t not in STOPWORDS]
    if not terms:
        return []

    def has_term(term: str) -> FieldCondition:
        return FieldCondition(key="content", match=MatchText(text=term))

    must = [Filter(should=[has_term(t) for t in terms])]
    if query_filter:
        must.append(query_filter)
    candidates, _ = qdrant.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=must),
        limit=200,
        with_payload=True,
        with_vectors=True,
    )
    if not candidates:
        return []

    total = qdrant.count(collection_name=COLLECTION, exact=True).count
    df = {
        t: qdrant.count(
            collection_name=COLLECTION, count_filter=Filter(must=[has_term(t)]), exact=True
        ).count
        for t in terms
    }
    docs = [tokenize(c.payload["content"]) for c in candidates]
    avg_len = sum(len(d) for d in docs) / len(docs)
    k1, b = 1.2, 0.75

    def bm25(doc: list[str]) -> float:
        score = 0.0
        for t in terms:
            tf = doc.count(t)
            if not tf:
                continue
            idf = math.log(1 + (total - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / avg_len))
        return score

    ranked = sorted(zip(candidates, docs), key=lambda cd: bm25(cd[1]), reverse=True)
    return [c for c, _ in ranked[:limit]]


def fuse(vector_hits: list, keyword_hits: list, embedding: list[float], limit: int) -> list:
    """Reciprocal rank fusion. Returns (point, cosine score, match) in fused order, where
    match says which rankings the point appeared in. score stays cosine similarity so
    it means the same thing as in semantic mode."""
    fused: dict[str, float] = {}
    points: dict[str, object] = {}
    cosines: dict[str, float] = {}
    sources: dict[str, set] = {}
    for rank, hit in enumerate(vector_hits):
        key = str(hit.id)
        fused[key] = fused.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        points[key], cosines[key] = hit, hit.score
        sources.setdefault(key, set()).add("semantic")
    for rank, hit in enumerate(keyword_hits):
        key = str(hit.id)
        fused[key] = fused.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        points.setdefault(key, hit)
        if key not in cosines:
            cosines[key] = cosine(embedding, hit.vector)
        sources.setdefault(key, set()).add("keyword")
    order = sorted(fused, key=lambda k: fused[k], reverse=True)[:limit]
    return [
        (points[k], cosines[k], "both" if len(sources[k]) == 2 else next(iter(sources[k])))
        for k in order
    ]


# Routes

def model_installed(wanted: str, installed: list[str]) -> bool:
    """Ollama lists models with a tag (llama3.2:latest); a bare name means :latest."""
    return any(name == wanted or name == f"{wanted}:latest" for name in installed)


@app.get("/health")
async def health():
    """Always HTTP 200 while the API process is up; status says whether dependencies are
    usable ("ok" or "degraded"), and qdrant/ollama give the detail."""
    qdrant_status: dict = {"ok": True}
    try:
        names = await asyncio.to_thread(
            lambda: [c.name for c in qdrant.get_collections().collections]
        )
        qdrant_status["collection_exists"] = COLLECTION in names
    except Exception as e:
        qdrant_status = {"ok": False, "error": str(e)[:200]}

    ollama_status: dict = {"ok": True}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
        resp.raise_for_status()
        installed = [m.get("name", "") for m in resp.json().get("models", [])]
        ollama_status["embed_model_present"] = model_installed(EMBED_MODEL, installed)
        ollama_status["llm_model_present"] = model_installed(LLM_MODEL, installed)
    except Exception as e:
        ollama_status = {"ok": False, "error": str(e)[:200]}

    healthy = (
        qdrant_status["ok"]
        and qdrant_status.get("collection_exists", False)
        and ollama_status["ok"]
        and ollama_status["embed_model_present"]
        and ollama_status["llm_model_present"]
    )
    return {
        "status": "ok" if healthy else "degraded",
        "collection": COLLECTION,
        "embed_model": EMBED_MODEL,
        "qdrant": qdrant_status,
        "ollama": ollama_status,
    }


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Run embedding and metadata extraction concurrently
    tags = req.tags or []
    project = req.project.strip() if req.project and req.project.strip() else None

    embedding, (metadata, metadata_status) = await asyncio.gather(
        get_embedding(req.content),
        extract_metadata(req.content),
    )

    if not req.force:
        # Duplicates are judged within the same project scope (or among unscoped entries)
        if project:
            scope = FieldCondition(key="project", match=MatchValue(value=project))
        else:
            scope = IsEmptyCondition(is_empty=PayloadField(key="project"))
        top = qdrant.query_points(
            collection_name=COLLECTION,
            query=embedding,
            limit=1,
            query_filter=Filter(must=[scope]),
            with_payload=True,
        ).points
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
                metadata_status=hit.payload.get("metadata_status"),
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
                    "metadata_status": metadata_status,
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
        metadata_status=metadata_status,
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

    pool = min(req.limit * 3, 100)  # candidates per ranking before fusion
    vector_hits = qdrant.query_points(
        collection_name=COLLECTION,
        query=embedding,
        limit=pool if req.mode == "hybrid" else req.limit,
        query_filter=query_filter,
        with_payload=True,
    ).points

    if req.mode == "semantic":
        ranked = [(hit, hit.score, "semantic") for hit in vector_hits]
    else:
        keyword_hits = keyword_search(req.query, query_filter, pool)
        ranked = fuse(vector_hits, keyword_hits, embedding, req.limit)

    results = [
        SearchResult(
            id=str(hit.id),
            content=hit.payload["content"],
            source=hit.payload.get("source", "unknown"),
            tags=hit.payload.get("tags", []),
            project=hit.payload.get("project"),
            created_at=hit.payload.get("created_at", ""),
            score=score,
            match=match,
            metadata=Metadata(
                type=hit.payload.get("type", "other"),
                topics=hit.payload.get("topics", []),
                people=hit.payload.get("people", []),
                action_items=hit.payload.get("action_items", []),
            ),
        )
        for hit, score, match in ranked
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
    entries = [entry_dict(r.id, r.payload) for r in results]
    next_before = entries[-1]["created_at"] if len(entries) == limit else None
    return {"entries": entries, "count": len(entries), "next_before": next_before}


@app.patch("/entries/{entry_id}")
async def update_entry(entry_id: str, req: UpdateRequest):
    """Edit content, tags, or project. Changing content re-embeds and re-extracts
    metadata; reextract=true re-runs extraction alone (e.g. for metadata_status failed)."""
    point = get_point(entry_id)
    payload: dict = {}
    clear: list[str] = []

    if "tags" in req.model_fields_set and req.tags is not None:
        payload["tags"] = req.tags
    if "project" in req.model_fields_set:
        project = req.project.strip() if req.project else ""
        if project:
            payload["project"] = project
        elif "project" in point.payload:
            clear.append("project")

    content = point.payload["content"]
    content_changed = req.content is not None and req.content != content
    if req.content is not None and not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    new_vector = None
    if content_changed or req.reextract:
        new_content = req.content if content_changed else content
        if content_changed:
            (new_vector, (metadata, status)) = await asyncio.gather(
                get_embedding(new_content), extract_metadata(new_content)
            )
            payload["content"] = new_content
        else:
            metadata, status = await extract_metadata(new_content)
        payload.update(
            {
                "type": metadata.type,
                "topics": metadata.topics,
                "people": metadata.people,
                "action_items": metadata.action_items,
                "metadata_status": status,
            }
        )

    if new_vector is not None:
        qdrant.update_vectors(
            collection_name=COLLECTION,
            points=[PointVectors(id=entry_id, vector=new_vector)],
        )
    if payload:
        qdrant.set_payload(collection_name=COLLECTION, payload=payload, points=[entry_id])
    if clear:
        qdrant.delete_payload(collection_name=COLLECTION, keys=clear, points=[entry_id])

    return entry_dict(entry_id, get_point(entry_id).payload)


@app.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str):
    get_point(entry_id)  # 422 for a malformed id, 404 if missing
    qdrant.delete(
        collection_name=COLLECTION,
        points_selector=[entry_id],
    )
    return {"deleted": entry_id}


def export_line(point) -> str:
    p = point.payload
    return json.dumps(
        {
            "id": str(point.id),
            "content": p["content"],
            "source": p.get("source", "unknown"),
            "tags": p.get("tags", []),
            "project": p.get("project"),
            "created_at": p.get("created_at", ""),
            "metadata": {
                "type": p.get("type", "other"),
                "topics": p.get("topics", []),
                "people": p.get("people", []),
                "action_items": p.get("action_items", []),
            },
            "metadata_status": p.get("metadata_status"),
        },
        ensure_ascii=False,
    )


@app.get("/export")
def export_entries():
    """Stream every entry as JSONL (one JSON object per line), in no guaranteed order. Vectors are
    not included: /import re-embeds, so an export works across embedding models."""

    def lines():
        offset = None
        while True:
            batch, offset = qdrant.scroll(
                collection_name=COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in batch:
                yield export_line(point) + "\n"
            if offset is None:
                break

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="open-brain-{stamp}.jsonl"'},
    )


IMPORT_BATCH = 20
IMPORT_CONCURRENCY = 4


class ImportLine(BaseModel):
    """One line of an /export file. Unknown keys are ignored."""
    id: Optional[str] = None
    content: str
    source: Optional[str] = "import"
    tags: Optional[list[str]] = None
    project: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Optional[dict] = None
    metadata_status: Optional[str] = None


@app.post("/import")
async def import_entries(request: Request, overwrite: bool = False):
    """Restore entries from a JSONL body in the /export format (send with --data-binary).
    Ids and created_at are kept, so re-importing a file is safe: existing ids are skipped
    unless overwrite=true. Every entry is re-embedded. Metadata is reused when the line has
    it and it did not fail; otherwise it is extracted. The near-duplicate check is skipped."""
    text = (await request.body()).decode("utf-8", errors="replace")
    result = {"imported": 0, "skipped_existing": 0, "reextracted": 0, "failed": []}

    parsed: list[tuple[int, ImportLine, str]] = []
    seen: set[str] = set()
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            line = ImportLine.model_validate(json.loads(raw))
            if not line.content.strip():
                raise ValueError("content is empty")
            entry_id = line.id or str(uuid.uuid4())
            uuid.UUID(entry_id)
            if line.created_at:
                datetime.fromisoformat(line.created_at)
            if entry_id in seen:
                raise ValueError(f"duplicate id {entry_id} in file")
            seen.add(entry_id)
            parsed.append((n, line, entry_id))
        except Exception as e:
            result["failed"].append({"line": n, "error": str(e)[:200]})

    gate = asyncio.Semaphore(IMPORT_CONCURRENCY)

    async def prepare(n: int, line: ImportLine, entry_id: str):
        async with gate:
            try:
                reused = bool(line.metadata) and line.metadata_status != "failed"
                if reused:
                    embedding = await get_embedding(line.content)
                    metadata, status = Metadata(**line.metadata), line.metadata_status
                else:
                    embedding, (metadata, status) = await asyncio.gather(
                        get_embedding(line.content), extract_metadata(line.content)
                    )
                project = line.project.strip() if line.project and line.project.strip() else None
                point = PointStruct(
                    id=entry_id,
                    vector=embedding,
                    payload={
                        "content": line.content,
                        "source": line.source or "import",
                        "tags": line.tags or [],
                        **({"project": project} if project else {}),
                        "created_at": line.created_at or datetime.now(timezone.utc).isoformat(),
                        "type": metadata.type,
                        "topics": metadata.topics,
                        "people": metadata.people,
                        "action_items": metadata.action_items,
                        **({"metadata_status": status} if status else {}),
                    },
                )
                return point, not reused
            except Exception as e:
                detail = e.detail if isinstance(e, HTTPException) else str(e)
                result["failed"].append({"line": n, "error": str(detail)[:200]})
                return None

    for i in range(0, len(parsed), IMPORT_BATCH):
        chunk = parsed[i : i + IMPORT_BATCH]
        existing = {
            str(r.id)
            for r in qdrant.retrieve(
                collection_name=COLLECTION,
                ids=[eid for _, _, eid in chunk],
                with_payload=False,
                with_vectors=False,
            )
        }
        todo = []
        for item in chunk:
            if item[2] in existing and not overwrite:
                result["skipped_existing"] += 1
            else:
                todo.append(item)
        prepared = [r for r in await asyncio.gather(*(prepare(*t) for t in todo)) if r]
        if prepared:
            qdrant.upsert(collection_name=COLLECTION, points=[pt for pt, _ in prepared])
            result["imported"] += len(prepared)
            result["reextracted"] += sum(1 for _, extracted in prepared if extracted)

    result["failed"].sort(key=lambda f: f["line"])
    return result


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
