"""The HTTP surface on fakes: auth, models, chat, streaming, docs, quotas, uploads, catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from steakllm_gateway.app import Deps, create_app, key_id
from steakllm_gateway.backends import ChatResult
from steakllm_gateway.quotas import QuotaLedger
from steakllm_gateway.rag import Hit


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


@dataclass
class FakeRetriever:
    searched: list = field(default_factory=list)

    def search(self, question, collection):
        self.searched.append((question, collection))
        return [Hit("a" * 64, 1, "EMEA grew 21 percent", 0.9, "quarantine/r.pdf")]


@dataclass
class FakeS3:
    deleted: list = field(default_factory=list)

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803 — boto3's names
        return f"http://minio/{Params['Key']}"

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)


@dataclass
class FakeTable:
    rows: dict = field(default_factory=dict)

    def get_item(self, Key):  # noqa: N803
        return {"Item": self.rows[Key["doc_id"]]} if Key["doc_id"] in self.rows else {}

    def delete_item(self, Key):  # noqa: N803
        self.rows.pop(Key["doc_id"], None)

    def scan(self):
        return {"Items": list(self.rows.values())}


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    monkeypatch.setenv("GATEWAY_API_KEY", "dev-key")
    monkeypatch.setenv("GATEWAY_API_KEYS", '["other-key"]')
    monkeypatch.setenv("GATEWAY_DEMO_KEY", "demo-key")
    monkeypatch.setenv("GATEWAY_DEMO_RPM", "2")
    s = Settings(_env_file=None)
    clock = Clock()
    deps = Deps(
        settings=s,
        router=FakeRouter(),
        producer=FakeProducer(),
        s3=FakeS3(),
        table=FakeTable(
            {
                "d" * 64: {
                    "doc_id": "d" * 64,
                    "key": "quarantine/d.pdf",
                    "status": "indexed",
                    "chunk_count": 3,  # the fact the stage is derived from
                }
            }
        ),
        retriever=FakeRetriever(),
        ledger=QuotaLedger(clock=clock),
        now=lambda: "2026-09-02T23:00:00Z",
    )
    c = TestClient(create_app(deps))
    c.deps, c.clock = deps, clock
    return c


AUTH = {"Authorization": "Bearer dev-key"}
DEMO = {"Authorization": "Bearer demo-key"}
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
    assert client.deps.ledger.used_today(key_id("dev-key")) == 6


def test_streaming_is_sse_and_the_event_is_emitted_after_the_stream(client):
    with client.stream(
        "POST", "/v1/chat/completions", headers=AUTH, json={**BODY, "stream": True}
    ) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in r.iter_lines() if line]
    assert lines[-1] == "data: [DONE]"
    (sent,) = client.deps.producer.sent
    assert sent["event"]["data"]["tokens_in"] == 5


def test_docs_model_retrieves_cites_and_records_the_documents(client):
    r = client.post("/v1/chat/completions", headers=AUTH, json={**BODY, "model": "docs"})
    assert r.status_code == 200
    assert client.deps.retriever.searched == [("hello", "documents")]
    req = client.deps.router.seen[-1]
    assert (
        req.messages[0]["role"] == "system"
        and "[aaaaaaaa:1] EMEA grew" in req.messages[1]["content"]
    )
    assert req.messages[-1] == {"role": "user", "content": "hello"}
    assert r.headers["x-retrieved-doc-ids"] == "a" * 64
    assert client.deps.producer.sent[0]["event"]["data"]["retrieved_doc_ids"] == ["a" * 64]


def test_demo_key_searches_the_demo_collection_and_has_a_tight_quota(client):
    client.post("/v1/chat/completions", headers=DEMO, json={**BODY, "model": "docs"})
    assert client.deps.retriever.searched[-1] == ("hello", "demo")
    client.post("/v1/chat/completions", headers=DEMO, json=BODY)
    r = client.post("/v1/chat/completions", headers=DEMO, json=BODY)  # third within a minute: over
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    client.clock.t += 61
    assert client.post("/v1/chat/completions", headers=DEMO, json=BODY).status_code == 200


def test_max_tokens_is_capped_and_defaults_applied(client):
    client.post("/v1/chat/completions", headers=AUTH, json={**BODY, "max_tokens": 999999})
    req = client.deps.router.seen[-1]
    assert req.max_tokens == client.deps.settings.chat_max_tokens_cap and req.temperature == 0.2


def test_unknown_model_is_404(client):
    r = client.post("/v1/chat/completions", headers=AUTH, json={**BODY, "model": "gpt"})
    assert r.status_code == 404


def test_upload_is_presigned_and_validated(client):
    r = client.post(
        "/v1/uploads",
        headers=AUTH,
        json={"filename": "Q3.pdf", "content_type": "application/pdf", "size_bytes": 1234},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["method"] == "PUT" and body["key"].startswith("quarantine/")
    assert body["url"] == f"http://minio/{body['key']}"
    bad_type = {"filename": "x.exe", "content_type": "application/octet-stream", "size_bytes": 1}
    assert client.post("/v1/uploads", headers=AUTH, json=bad_type).status_code == 415
    too_big = {"filename": "x.pdf", "content_type": "application/pdf", "size_bytes": 10**9}
    assert client.post("/v1/uploads", headers=AUTH, json=too_big).status_code == 413


def test_document_status_is_readable_by_doc_id(client):
    r = client.get(f"/v1/documents/{'d' * 64}", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "indexed"
    assert r.json()["uploaded"] and r.json()["indexed"] and not r.json()["summarized"]
    assert client.get(f"/v1/documents/{'e' * 64}", headers=AUTH).status_code == 404


def test_delete_removes_and_announces_then_404s(client):
    r = client.delete(f"/v1/documents/{'d' * 64}", headers=AUTH)
    assert r.status_code == 204
    assert client.deps.s3.deleted == ["quarantine/d.pdf"] and client.deps.table.rows == {}
    ev = client.deps.producer.sent[0]["event"]
    validate(ev)
    assert ev["type"] == "DocumentDeleted" and ev["data"]["requested_by"] == key_id("dev-key")
    assert client.delete(f"/v1/documents/{'d' * 64}", headers=AUTH).status_code == 404


def test_catalog_page_needs_a_key_and_shows_the_stages(client):
    assert client.get("/catalog").status_code == 401
    r = client.get("/catalog?key=dev-key")  # browser-friendly form
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "✓ indexed" in r.text and "· summarized" in r.text


def test_probes_and_openapi(client):
    assert client.get("/healthz").json() == {"status": "alive"}
    assert client.get("/readyz").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/v1/chat/completions", "/v1/uploads", "/v1/documents/{doc_id}", "/catalog"} <= set(
        paths
    )
