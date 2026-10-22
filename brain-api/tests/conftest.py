"""Test setup: the real FastAPI app runs against an in-memory Qdrant, with the two Ollama
calls (embedding and metadata extraction) replaced by deterministic fakes."""
import asyncio
import hashlib
import math
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402

DIM = 64


def fake_embed(text: str) -> list[float]:
    """Bag-of-words hashing: texts sharing words get similar vectors."""
    vec = [0.0] * DIM
    for tok in re.findall(r"\w+", text.lower()):
        vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class Ollama:
    """Handle on the fakes so tests can break them or count calls."""

    def __init__(self):
        self.embed_calls = 0
        self.extract_calls = 0
        self.extract_fails = False
        self.embed_fails = False

    async def embed(self, text):
        self.embed_calls += 1
        if self.embed_fails:
            raise main.HTTPException(status_code=502, detail="Ollama embedding failed: boom")
        return fake_embed(text)

    async def extract(self, content):
        self.extract_calls += 1
        if self.extract_fails:
            return main.Metadata(), "failed"
        metadata = main.Metadata(type="decision", topics=["fake-topic"], people=[], action_items=[])
        return metadata, "ok"


@pytest.fixture
def ollama(monkeypatch):
    fake = Ollama()
    monkeypatch.setattr(main, "get_embedding", fake.embed)
    monkeypatch.setattr(main, "extract_metadata", fake.extract)
    return fake


@pytest.fixture
def client(monkeypatch, ollama):
    monkeypatch.setattr(main, "qdrant", QdrantClient(":memory:"))
    monkeypatch.setattr(main, "EMBED_DIM", DIM)
    asyncio.run(main.startup())
    return TestClient(main.app)


@pytest.fixture
def add(client):
    """add(content, **fields) -> ingest response JSON (asserting success)."""

    def _add(content, **fields):
        resp = client.post("/ingest", json={"content": content, **fields})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _add
