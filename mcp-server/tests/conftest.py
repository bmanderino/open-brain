"""The MCP tools are plain async functions that call the Brain API over HTTP. These tests call
them directly with httpx's transport replaced by a fake, so they check exactly which requests
the tools send and what text they hand back to Claude."""
import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SERVER = Path(__file__).resolve().parent.parent / "mcp-server.py"
_spec = importlib.util.spec_from_file_location("mcp_server", SERVER)
mcp_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp_server)

RealAsyncClient = httpx.AsyncClient


class FakeApi:
    """Programmable Brain API: set api.reply(method, path, status, body); read api.requests."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.replies: dict[tuple[str, str], tuple[int, object]] = {}

    def reply(self, method, path, status=200, body=None):
        self.replies[(method, path)] = (status, body if body is not None else {})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.replies:
            return httpx.Response(500, text=f"unexpected request {key}")
        status, body = self.replies[key]
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self):
        return json.loads(self.last.content)

    def last_params(self):
        return dict(self.last.url.params)


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()

    def client_factory(**kwargs):
        return RealAsyncClient(transport=httpx.MockTransport(fake.handler), **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client_factory)
    return fake


@pytest.fixture
def run():
    return asyncio.run


@pytest.fixture
def tools():
    return mcp_server
