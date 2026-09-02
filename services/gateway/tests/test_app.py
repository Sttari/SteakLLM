"""The HTTP surface on a fake router and producer: auth, models, chat, streaming, the event."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from steakllm_gateway.app import Deps, create_app, key_id
from steakllm_gateway.backends import ChatResult


@dataclass
class FakeRouter:
    backend: str = "bedrock"
    seen: list = field(default_factory=list)

    def complete(self, req):
        self.seen.append(req)
        if req.stream:
            chunks = [b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n', b"data: [DONE]\n\n"]
            r = ChatResult(events=iter(chunks), model="m")
            r.usage = {"prompt_tokens": 5, "completion_tokens": 1}
            return self.backend, r
        return self.backend, ChatResult(
            body={"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
            usage={"prompt_tokens": 5, "completion_tokens": 1},
            model="m",
        )


@dataclass
class FakeProducer:
    sent: list[dict] = field(default_factory=list)

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append({"topic": topic, "event": json.loads(value)})

    def flush(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    monkeypatch.setenv("GATEWAY_API_KEY", "dev-key")
    monkeypatch.setenv("GATEWAY_API_KEYS", '["other-key"]')
    s = Settings(_env_file=None)
    deps = Deps(
        settings=s, router=FakeRouter(), producer=FakeProducer(), now=lambda: "2026-09-02T23:00:00Z"
    )
    c = TestClient(create_app(deps))
    c.deps = deps
    return c


AUTH = {"Authorization": "Bearer dev-key"}
BODY = {"model": "llm", "messages": [{"role": "user", "content": "hello"}], "user": "s_1"}


def test_no_key_or_wrong_key_is_401(client):
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert (
        client.get("/v1/models", headers={"Authorization": "Bearer other-key"}).status_code == 200
    )


def test_models_lists_llm_and_docs(client):
    ids = [m["id"] for m in client.get("/v1/models", headers=AUTH).json()["data"]]
    assert ids == ["llm", "docs"]


def test_chat_answers_with_backend_headers_and_emits_chat_completed(client):
    r = client.post("/v1/chat/completions", headers=AUTH, json=BODY)
    assert r.status_code == 200
    assert r.headers["x-backend"] == "bedrock"
    assert r.headers["x-tokens-in"] == "5" and r.headers["x-tokens-out"] == "1"
    assert r.json()["choices"][0]["message"]["content"] == "hi"
    (sent,) = client.deps.producer.sent
    ev = sent["event"]
    validate(ev)
    assert sent["topic"] == "chats" and ev["type"] == "ChatCompleted" and ev["doc_id"] is None
    assert ev["data"]["backend"] == "bedrock" and ev["data"]["session_id"] == "s_1"
    assert ev["data"]["api_key_id"] == key_id("dev-key") and len(ev["data"]["api_key_id"]) == 16
    assert ev["trace_id"] == r.headers["x-trace-id"]


def test_streaming_is_sse_and_the_event_is_emitted_after_the_stream(client):
    with client.stream(
        "POST", "/v1/chat/completions", headers=AUTH, json={**BODY, "stream": True}
    ) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in r.iter_lines() if line]
    assert lines[-1] == "data: [DONE]"
    (sent,) = client.deps.producer.sent
    assert sent["event"]["data"]["tokens_in"] == 5


def test_max_tokens_is_capped_and_defaults_applied(client):
    client.post("/v1/chat/completions", headers=AUTH, json={**BODY, "max_tokens": 999999})
    req = client.deps.router.seen[-1]
    assert req.max_tokens == client.deps.settings.chat_max_tokens_cap and req.temperature == 0.2


def test_unknown_model_is_404_and_docs_is_not_yet_available(client):
    assert (
        client.post("/v1/chat/completions", headers=AUTH, json={**BODY, "model": "gpt"}).status_code
        == 404
    )
    assert (
        client.post(
            "/v1/chat/completions", headers=AUTH, json={**BODY, "model": "docs"}
        ).status_code
        == 501
    )


def test_probes_and_openapi(client):
    assert client.get("/healthz").json() == {"status": "alive"}
    assert client.get("/readyz").status_code == 200
    assert "/v1/chat/completions" in client.get("/openapi.json").json()["paths"]
