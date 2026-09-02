"""The summarizer on fakes: summarize, skip when done, parse leniently, clear on delete, ignore."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import pytest
from steakllm_common.settings import Settings
from steakllm_contracts.ids import doc_id
from steakllm_contracts.validate import validate

from steakllm_summarizer.gateway import ChatResult
from steakllm_summarizer.handler import BadModelOutputError, Deps, handle, parse_model_output


@dataclass
class FakeS3:
    objects: dict[str, bytes] = field(default_factory=dict)

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.objects[kw["Key"]])}


@dataclass
class FakeTable:
    rows: dict[str, dict] = field(default_factory=dict)

    def get_item(self, **kw):
        row = self.rows.get(kw["Key"]["doc_id"])
        return {"Item": row} if row is not None else {}

    def update_item(self, **kw):
        key = kw["Key"]["doc_id"]
        if kw.get("ConditionExpression") == "attribute_exists(doc_id)" and key not in self.rows:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        row = self.rows.setdefault(key, {})
        expr = kw["UpdateExpression"]
        if expr.startswith("REMOVE"):
            for attr in expr[len("REMOVE ") :].split(", "):
                row.pop(attr, None)
            return
        v = kw["ExpressionAttributeValues"]
        row.update(status="summarized", summary=v[":sum"], tags=v[":tags"], summary_backend=v[":b"])


@dataclass
class FakeProducer:
    sent: list[dict] = field(default_factory=list)

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append({"topic": topic, "event": json.loads(value)})

    def flush(self):
        pass


@dataclass
class FakeChat:
    reply: str = '{"summary": "A report about growth.", "tags": ["Finance", "growth", "finance"]}'
    calls: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> ChatResult:
        self.calls.append(prompt)
        return ChatResult(self.reply, "bedrock", "amazon.nova-micro-v1:0", 432, 95)


@pytest.fixture
def deps(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    s = Settings(_env_file=None)
    return Deps(
        settings=s,
        s3=FakeS3(),
        table=FakeTable(),
        producer=FakeProducer(),
        chat=FakeChat(),
        now=lambda: "2026-09-02T22:00:00Z",
    )


def uploaded(deps, body=b"Revenue grew 12 percent, driven by EMEA.", key="quarantine/r.md"):
    deps.s3.objects[key] = body
    ev = {
        "id": "0f6a7b8c-1d2e-4f30-9a1b-000000000001",
        "type": "DocumentUploaded",
        "version": 1,
        "time": "2026-09-02T21:59:00Z",
        "doc_id": doc_id(body),
        "trace_id": "c" * 32,
        "source": "ingest",
        "data": {
            "bucket": "b",
            "key": key,
            "size_bytes": len(body),
            "content_type": "text/markdown",
            "sha256": doc_id(body),
        },
    }
    validate(ev)
    return ev


def test_uploaded_becomes_a_summary_a_row_and_an_event(deps):
    ev = uploaded(deps)
    handle(ev, {}, deps)
    row = deps.table.rows[ev["doc_id"]]
    assert row["status"] == "summarized" and row["summary"] == "A report about growth."
    assert row["tags"] == ["finance", "growth"]  # lowercased, deduplicated
    (sent,) = deps.producer.sent
    out = sent["event"]
    validate(out)
    assert out["type"] == "SummaryReady" and out["source"] == "summarizer"
    assert out["trace_id"] == ev["trace_id"]
    assert out["data"]["backend"] == "bedrock" and out["data"]["tokens_in"] == 432
    assert "Revenue grew" in deps.chat.calls[0]  # the document text reached the prompt


def test_already_summarized_is_skipped_before_any_llm_call(deps):
    ev = uploaded(deps)
    deps.table.rows[ev["doc_id"]] = {"status": "summarized", "summary": "old"}
    handle(ev, {}, deps)
    assert deps.chat.calls == [] and deps.producer.sent == []
    assert deps.table.rows[ev["doc_id"]]["summary"] == "old"


def test_prompt_is_capped_at_the_budget(deps, monkeypatch):
    monkeypatch.setenv("SUMMARIZER_MAX_CHARS", "50")
    deps.settings = Settings(_env_file=None)
    ev = uploaded(deps, body=b"x" * 5000)
    handle(ev, {}, deps)
    assert deps.chat.calls[0].endswith("x" * 50) and "x" * 51 not in deps.chat.calls[0]


def test_bad_model_output_raises_so_the_loop_retries(deps):
    deps.chat = FakeChat(reply="Sure! Here is a summary without any JSON.")
    with pytest.raises(BadModelOutputError):
        handle(uploaded(deps), {}, deps)
    assert deps.producer.sent == []


@pytest.mark.parametrize(
    "text",
    [
        '{"summary": "S", "tags": ["a"]}',
        '```json\n{"summary": "S", "tags": ["a"]}\n```',
        'Here you go:\n{"summary": "S", "tags": ["a", "A", " b "]}\nHope this helps.',
    ],
)
def test_parse_is_lenient_about_fences_and_chatter(text):
    summary, tags = parse_model_output(text)
    assert summary == "S" and tags[0] == "a" and len(tags) == len(set(tags))


def test_parse_rejects_empty_summary():
    with pytest.raises(BadModelOutputError):
        parse_model_output('{"summary": "", "tags": []}')


def test_deleted_clears_the_summary_and_tolerates_a_missing_row(deps):
    ev = uploaded(deps)
    handle(ev, {}, deps)
    handle({**ev, "type": "DocumentDeleted", "data": {"reason": "user_request"}}, {}, deps)
    assert "summary" not in deps.table.rows[ev["doc_id"]]
    handle(
        {"type": "DocumentDeleted", "doc_id": "e" * 64, "data": {"reason": "retention"}}, {}, deps
    )


def test_other_event_types_are_ignored(deps):
    handle({"type": "DocumentIndexed", "doc_id": "x", "data": {}}, {}, deps)
    assert deps.chat.calls == [] and deps.producer.sent == []
