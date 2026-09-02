"""Quotas on a fake clock; retrieval on a fake Qdrant; uploads, deletes and the catalog on fakes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from steakllm_gateway.documents import catalog_html, delete_document, presign_upload
from steakllm_gateway.quotas import KeyPolicy, QuotaLedger
from steakllm_gateway.rag import Retriever, build_messages, last_user_question


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_requests_per_minute_is_a_sliding_window_with_retry_after():
    clock = Clock()
    ledger, policy = (
        QuotaLedger(clock=clock),
        KeyPolicy("p", "documents", rpm=3, tokens_per_day=10**6),
    )
    assert [ledger.check("k", policy)[0] for _ in range(3)] == [True, True, True]
    ok, retry = ledger.check("k", policy)
    assert ok is False and 1 <= retry <= 61
    clock.t += 61
    assert ledger.check("k", policy)[0] is True


def test_tokens_per_day_blocks_until_tomorrow():
    clock = Clock()
    ledger, policy = (
        QuotaLedger(clock=clock),
        KeyPolicy("p", "documents", rpm=100, tokens_per_day=1000),
    )
    ledger.add_tokens("k", 999)
    assert ledger.check("k", policy)[0] is True
    ledger.add_tokens("k", 1)
    ok, retry = ledger.check("k", policy)
    assert ok is False and retry > 60
    clock.t += 86400
    assert ledger.check("k", policy)[0] is True and ledger.used_today("k") == 0


@dataclass
class Point:
    payload: dict
    score: float


@dataclass
class FakeQdrant:
    hits: list[Point] = field(default_factory=list)
    queried: list = field(default_factory=list)

    def collection_exists(self, name):
        return name == "documents"

    def query_points(self, collection, query, limit, with_payload):
        self.queried.append((collection, limit))

        class R:
            points = self.hits

        return R()


def test_retriever_searches_only_the_keys_collection_and_labels_hits():
    q = FakeQdrant(
        [
            Point(
                {"doc_id": "a" * 64, "chunk_index": 3, "text": "EMEA grew 21 percent", "key": "k"},
                0.9,
            )
        ]
    )
    r = Retriever(q, embed=lambda texts: [[0.1] * 4 for _ in texts], top_k=2)
    hits = r.search("what grew?", "documents")
    assert q.queried == [("documents", 2)]
    assert hits[0].label == "[aaaaaaaa:3]" and hits[0].score == 0.9
    assert r.search("anything", "demo") == []  # collection missing → no hits, no error


def test_messages_get_the_rule_and_the_excerpts_but_keep_the_conversation():
    hits = [type("H", (), {"label": "[d:0]", "text": "excerpt"})()]
    msgs = build_messages(
        [{"role": "system", "content": "ignored"}, {"role": "user", "content": "q?"}], hits
    )
    assert msgs[0]["role"] == "system" and "[doc:chunk]" in msgs[0]["content"]
    assert "[d:0] excerpt" in msgs[1]["content"]
    assert msgs[-1] == {"role": "user", "content": "q?"}
    assert (
        last_user_question(
            [{"role": "assistant", "content": "a"}, {"role": "user", "content": "q?"}]
        )
        == "q?"
    )


@dataclass
class FakeS3:
    deleted: list = field(default_factory=list)

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803 — boto3's names
        return f"http://minio/{Params['Bucket']}/{Params['Key']}?sig=x&exp={ExpiresIn}"

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


@dataclass
class FakeProducer:
    sent: list = field(default_factory=list)

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append({"topic": topic, "event": json.loads(value)})

    def flush(self):
        pass


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "t")
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "1000")
    return Settings(_env_file=None)


def test_presign_puts_under_quarantine_with_a_safe_name(settings):
    out = presign_upload(FakeS3(), settings, "Q3 report (final).pdf", "application/pdf", 500)
    assert out["method"] == "PUT" and out["headers"] == {"Content-Type": "application/pdf"}
    assert out["key"].startswith("quarantine/") and out["key"].endswith("-Q3-report-final-.pdf")
    assert "exp=300" in out["url"] and out["expires_in"] == 300


def test_presign_rejects_type_and_size_up_front(settings):
    with pytest.raises(ValueError):
        presign_upload(FakeS3(), settings, "x.exe", "application/octet-stream", 10)
    with pytest.raises(OverflowError):
        presign_upload(FakeS3(), settings, "x.pdf", "application/pdf", 5000)


def test_delete_removes_object_and_row_and_announces(settings):
    s3, table, producer = (
        FakeS3(),
        FakeTable({"d" * 64: {"doc_id": "d" * 64, "key": "quarantine/x.pdf"}}),
        FakeProducer(),
    )
    assert delete_document(
        s3, table, producer, settings, "d" * 64, "abcd" * 4, "2026-09-03T00:00:00Z"
    )
    assert s3.deleted == ["quarantine/x.pdf"] and table.rows == {}
    ev = producer.sent[0]["event"]
    validate(ev)
    assert ev["type"] == "DocumentDeleted" and ev["source"] == "gateway"
    assert ev["data"] == {"reason": "user_request", "requested_by": "abcd" * 4}
    assert delete_document(s3, table, producer, settings, "e" * 64, "k", "t") is False


def test_catalog_page_shows_the_three_stages():
    page = catalog_html(
        [
            {
                "doc_id": "a" * 64,
                "key": "quarantine/a.pdf",
                "status": "summarized",
                "chunk_count": 5,
                "summary": "S",
                "tags": ["x"],
            },
            {"doc_id": "b" * 64, "key": "quarantine/b.pdf", "status": "uploaded"},
        ]
    )
    assert page.count('class="on"') == 3 + 1 and page.count('class="off"') == 2
    assert "<td>S</td>" in page and "quarantine/b.pdf" in page
