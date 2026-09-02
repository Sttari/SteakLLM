"""The librarian on fakes: index, index again (no change), verify, delete, ignore, never regress."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from steakllm_common.settings import Settings
from steakllm_common.text import chunk
from steakllm_contracts.ids import doc_id, point_id
from steakllm_contracts.validate import validate

from steakllm_embedder.handler import Deps, ShaMismatchError, handle

SAMPLE = Path(__file__).resolve().parents[3] / "compose" / "sample" / "quarterly-report.pdf"
DIM = 8


@dataclass
class FakeS3:
    objects: dict[str, bytes] = field(default_factory=dict)

    def get_object(self, Bucket, Key):  # noqa: N803 — boto3's names
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}


@dataclass
class FakeTable:
    rows: dict[str, dict] = field(default_factory=dict)

    def update_item(self, **kw):  # boto3's keyword names, taken as a dict
        row = self.rows.setdefault(kw["Key"]["doc_id"], {})
        if kw.get("ConditionExpression") and row.get("status") not in (None, "uploaded", "indexed"):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        v = kw["ExpressionAttributeValues"]
        row.update(
            status="indexed", chunk_count=v[":n"], embedding_model=v[":m"], indexed_at=v[":now"]
        )


@dataclass
class FakeQdrant:
    points: dict[str, dict] = field(default_factory=dict)  # id -> payload
    collections: set = field(default_factory=set)
    indexes: list = field(default_factory=list)

    def collection_exists(self, name):
        return name in self.collections

    def create_collection(self, name, vectors_config):
        self.collections.add(name)

    def create_payload_index(self, name, field_name, field_schema):
        self.indexes.append((name, field_name))

    def upsert(self, name, points):
        for p in points:
            self.points[p.id] = {"vector": p.vector, **p.payload}

    def delete(self, name, points_selector):
        doc = points_selector.filter.must[0].match.value
        self.points = {k: v for k, v in self.points.items() if v["doc_id"] != doc}


@dataclass
class FakeProducer:
    sent: list[dict] = field(default_factory=list)

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append({"topic": topic, "key": key, "event": json.loads(value)})

    def flush(self):
        pass


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [[float(len(t) % 7)] * DIM for t in texts]  # deterministic, dimension DIM


@pytest.fixture
def deps(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    monkeypatch.setenv("EMBEDDING_DIM", str(DIM))
    s = Settings(_env_file=None)
    return Deps(
        settings=s,
        s3=FakeS3(),
        table=FakeTable(),
        qdrant=FakeQdrant(),
        producer=FakeProducer(),
        embed=fake_embed,
        now=lambda: "2026-09-02T21:00:00Z",
    )


def uploaded(deps, key="quarantine/r.pdf", body=None, ctype="application/pdf"):
    body = SAMPLE.read_bytes() if body is None else body
    deps.s3.objects[key] = body
    ev = {
        "id": "0f6a7b8c-1d2e-4f30-9a1b-000000000001",
        "type": "DocumentUploaded",
        "version": 1,
        "time": "2026-09-02T20:59:00Z",
        "doc_id": doc_id(body),
        "trace_id": "b" * 32,
        "source": "ingest",
        "data": {
            "bucket": "b",
            "key": key,
            "size_bytes": len(body),
            "content_type": ctype,
            "sha256": doc_id(body),
        },
    }
    validate(ev)
    return ev


def test_uploaded_becomes_points_a_row_and_an_event(deps):
    ev = uploaded(deps)
    handle(ev, {}, deps)
    doc = ev["doc_id"]
    n = len(
        chunk(
            __import__("steakllm_common.text", fromlist=["extract_text"]).extract_text(
                SAMPLE.read_bytes(), "application/pdf"
            )
        )
    )
    assert n == 5
    assert set(deps.qdrant.points) == {point_id(doc, i) for i in range(n)}
    assert all(p["doc_id"] == doc and len(p["vector"]) == DIM for p in deps.qdrant.points.values())
    assert deps.table.rows[doc]["status"] == "indexed" and deps.table.rows[doc]["chunk_count"] == n
    (sent,) = deps.producer.sent
    out = sent["event"]
    validate(out)
    assert out["type"] == "DocumentIndexed" and out["source"] == "embedder"
    assert out["trace_id"] == ev["trace_id"] and out["data"]["chunk_count"] == n
    assert deps.qdrant.indexes == [("documents", "doc_id")]


def test_the_same_event_twice_changes_nothing_in_the_store(deps):
    ev = uploaded(deps)
    handle(ev, {}, deps)
    before = dict(deps.qdrant.points)
    handle(ev, {}, deps)
    assert deps.qdrant.points == before  # same ids, same payloads: an upsert, not a duplicate
    assert len(deps.producer.sent) == 2  # events are facts; consumers of ours are idempotent too


def test_sha_mismatch_raises_so_the_loop_retries_then_dead_letters(deps):
    ev = uploaded(deps)
    deps.s3.objects[ev["data"]["key"]] = b"tampered"
    with pytest.raises(ShaMismatchError):
        handle(ev, {}, deps)
    assert deps.qdrant.points == {} and deps.producer.sent == []


def test_markdown_is_indexed_too(deps):
    ev = uploaded(
        deps, key="quarantine/n.md", body=b"# Notes\n\n" + b"word " * 300, ctype="text/markdown"
    )
    handle(ev, {}, deps)
    assert len(deps.qdrant.points) == len(chunk("# Notes\n\n" + "word " * 300))


def test_deleted_removes_only_that_documents_points(deps):
    a = uploaded(deps, key="quarantine/a.md", body=b"alpha " * 200, ctype="text/markdown")
    b = uploaded(deps, key="quarantine/b.md", body=b"beta " * 200, ctype="text/markdown")
    handle(a, {}, deps)
    handle(b, {}, deps)
    total = len(deps.qdrant.points)
    handle(
        {**a, "type": "DocumentDeleted", "source": "ingest", "data": {"reason": "user_request"}},
        {},
        deps,
    )
    assert all(p["doc_id"] == b["doc_id"] for p in deps.qdrant.points.values())
    assert 0 < len(deps.qdrant.points) < total


def test_object_gone_is_a_skip_not_a_failure(deps):
    ev = uploaded(deps)
    del deps.s3.objects[ev["data"]["key"]]  # deleted before the librarian got to it
    handle(ev, {}, deps)
    assert deps.qdrant.points == {} and deps.producer.sent == []


def test_other_event_types_are_ignored(deps):
    handle({"type": "SummaryReady", "doc_id": "x", "data": {}}, {}, deps)
    handle({"type": "ChatCompleted", "doc_id": None, "data": {}}, {}, deps)
    assert deps.qdrant.points == {} and deps.producer.sent == []


def test_delete_before_any_collection_exists_is_fine(deps):
    handle(
        {"type": "DocumentDeleted", "doc_id": "d" * 64, "data": {"reason": "retention"}}, {}, deps
    )


def test_a_redelivery_for_a_summarized_document_is_a_successful_no_op(deps):
    ev = uploaded(deps)
    deps.table.rows[ev["doc_id"]] = {"status": "summarized", "summary": "kept"}
    handle(ev, {}, deps)  # must not raise: a retry storm for a finished document is a bug
    assert deps.table.rows[ev["doc_id"]]["status"] == "summarized"  # row untouched
    assert len(deps.qdrant.points) == 5  # points refreshed with the same ids
    assert deps.producer.sent[0]["event"]["type"] == "DocumentIndexed"
