import asyncio
import json

import httpx

import main


class FakeGenerateClient:
    """Stands in for httpx.AsyncClient and records what extract_metadata posts."""

    def __init__(self, response=None, status=200):
        self.response, self.status, self.posted = response, status, None

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posted = (url, json)
        return httpx.Response(
            self.status,
            json={"response": self.response},
            request=httpx.Request("POST", url),
        )


def run_extract(monkeypatch, content, **kw):
    fake = FakeGenerateClient(**kw)
    monkeypatch.setattr(main.httpx, "AsyncClient", fake)
    return asyncio.run(main.extract_metadata(content)), fake


def test_generate_request_shape(monkeypatch):
    reply = json.dumps({"type": "decision", "topics": ["x"], "people": [], "action_items": []})
    (metadata, status), fake = run_extract(monkeypatch, "We chose X.", response=reply)
    url, body = fake.posted
    assert url.endswith("/api/generate")
    assert body["model"] == main.LLM_MODEL
    assert body["format"] == "json" and body["stream"] is False
    assert body["think"] is False  # thinking models would otherwise burn the output on reasoning
    assert "We chose X." in body["prompt"]
    assert status == "ok" and metadata.type == "decision"


def test_prompt_survives_braces_in_content(monkeypatch):
    (_, status), fake = run_extract(monkeypatch, 'config is {"a": {1}} done', response="{}")
    assert 'config is {"a": {1}} done' in fake.posted[1]["prompt"]
    assert status == "ok"


def test_invalid_json_is_failed(monkeypatch):
    (metadata, status), _ = run_extract(monkeypatch, "anything", response="not json")
    assert status == "failed" and metadata.type == "other"
