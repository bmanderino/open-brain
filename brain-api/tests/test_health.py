import httpx
import pytest

import main


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient when /health asks Ollama for /api/tags."""

    def __init__(self, models=None, error=None, status=200):
        self.models, self.error, self.status = models or [], error, status

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if self.error:
            raise self.error
        return httpx.Response(
            self.status,
            json={"models": [{"name": m} for m in self.models]},
            request=httpx.Request("GET", url),
        )


def patch_ollama(monkeypatch, **kw):
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient(**kw))


def test_all_good(client, monkeypatch):
    patch_ollama(monkeypatch, models=["nomic-embed-text:latest", "llama3.2:latest"])
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["qdrant"] == {"ok": True, "collection_exists": True}
    assert body["ollama"] == {"ok": True, "embed_model_present": True, "llm_model_present": True}


def test_missing_llm_model_is_degraded(client, monkeypatch):
    patch_ollama(monkeypatch, models=["nomic-embed-text:latest"])
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["ollama"]["llm_model_present"] is False
    assert body["ollama"]["embed_model_present"] is True


def test_missing_embed_model_is_degraded(client, monkeypatch):
    patch_ollama(monkeypatch, models=["llama3.2"])
    assert client.get("/health").json()["ollama"]["embed_model_present"] is False


def test_ollama_unreachable_is_degraded_but_http_200(client, monkeypatch):
    patch_ollama(monkeypatch, error=httpx.ConnectError("refused"))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["ollama"]["ok"] is False and "refused" in r.json()["ollama"]["error"]


def test_qdrant_down_is_degraded(client, monkeypatch):
    patch_ollama(monkeypatch, models=["nomic-embed-text", "llama3.2"])

    class Broken:
        def get_collections(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "qdrant", Broken())
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["qdrant"]["ok"] is False


def test_missing_collection_is_degraded(client, monkeypatch):
    patch_ollama(monkeypatch, models=["nomic-embed-text", "llama3.2"])
    monkeypatch.setattr(main, "COLLECTION", "other")
    body = client.get("/health").json()
    assert body["status"] == "degraded" and body["qdrant"]["collection_exists"] is False
