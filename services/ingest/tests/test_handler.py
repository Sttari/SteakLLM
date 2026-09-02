"""The doorbell on moto (S3 + DynamoDB in-process) and a fake producer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import boto3
import pytest
from moto import mock_aws
from steakllm_common.settings import Settings
from steakllm_contracts.ids import doc_id
from steakllm_contracts.validate import validate

from steakllm_ingest.handler import Deps, handle, parse_records
from steakllm_ingest.main import s3_record

BUCKET, TABLE = "steakllm-documents", "catalog"


@dataclass
class FakeProducer:
    sent: list[dict] = field(default_factory=list)

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append({"topic": topic, "key": key, "event": json.loads(value)})

    def flush(self):
        pass


@pytest.fixture
def deps(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "DOCUMENTS_BUCKET": BUCKET,
        "CATALOG_TABLE": TABLE,
        "UPLOAD_MAX_BYTES": "1000",
    }.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        s = Settings(_env_file=None)
        s3 = boto3.client("s3", region_name=s.aws_region)
        s3.create_bucket(Bucket=BUCKET)
        ddb = boto3.resource("dynamodb", region_name=s.aws_region)
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ticks = iter(f"2026-09-02T20:00:{i:02d}Z" for i in range(60))
        yield Deps(
            settings=s,
            s3=s3,
            table=ddb.Table(TABLE),
            producer=FakeProducer(),
            now=lambda: next(ticks),
            new_trace_id=lambda: "a" * 32,
        )


def put(deps, key, body=b"hello", ctype="text/plain"):
    deps.s3.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType=ctype)


def test_accept_writes_row_and_produces_document_uploaded(deps):
    put(deps, "quarantine/a.txt", b"hello")
    (ev,) = handle(s3_record(BUCKET, "quarantine/a.txt"), deps)
    validate(ev)
    assert ev["type"] == "DocumentUploaded" and ev["source"] == "ingest"
    assert ev["doc_id"] == doc_id(b"hello") == ev["data"]["sha256"]
    assert ev["data"] == {
        "bucket": BUCKET,
        "key": "quarantine/a.txt",
        "size_bytes": 5,
        "content_type": "text/plain",
        "sha256": doc_id(b"hello"),
    }
    row = deps.table.get_item(Key={"doc_id": ev["doc_id"]})["Item"]
    assert row["status"] == "uploaded" and row["key"] == "quarantine/a.txt"
    (sent,) = deps.producer.sent
    assert sent["topic"] == "documents" and sent["key"] == ev["doc_id"].encode()


def test_same_bytes_twice_is_the_same_document(deps):
    put(deps, "quarantine/a.txt", b"same")
    put(deps, "quarantine/b.txt", b"same")
    a = handle(s3_record(BUCKET, "quarantine/a.txt"), deps)[0]
    b = handle(s3_record(BUCKET, "quarantine/b.txt"), deps)[0]
    assert a["doc_id"] == b["doc_id"]
    assert deps.table.scan(Select="COUNT")["Count"] == 1  # one row, not two


def test_redelivery_of_the_same_key_is_recorded_once_and_announced_once(deps):
    put(deps, "quarantine/a.txt", b"hello")
    (ev,) = handle(s3_record(BUCKET, "quarantine/a.txt"), deps)
    deps.table.update_item(
        Key={"doc_id": ev["doc_id"]},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "indexed"},
    )
    again = handle(s3_record(BUCKET, "quarantine/a.txt"), deps)  # S3 delivered the event again
    assert deps.table.get_item(Key={"doc_id": ev["doc_id"]})["Item"]["status"] == "indexed"
    assert again == [] and len(deps.producer.sent) == 1  # not re-announced: no second index run


def test_too_large_is_rejected_moved_and_announced(deps):
    put(deps, "quarantine/big.txt", b"x" * 2000)
    (ev,) = handle(s3_record(BUCKET, "quarantine/big.txt"), deps)
    validate(ev)
    assert ev["type"] == "DocumentDeleted" and ev["data"]["reason"] == "quarantine_rejected"
    keys = [o["Key"] for o in deps.s3.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == ["rejected/big.txt"]
    assert deps.table.scan(Select="COUNT")["Count"] == 0


def test_wrong_content_type_is_rejected(deps):
    put(deps, "quarantine/x.exe", b"MZ", ctype="application/octet-stream")
    (ev,) = handle(s3_record(BUCKET, "quarantine/x.exe"), deps)
    assert ev["type"] == "DocumentDeleted" and ev["data"]["reason"] == "quarantine_rejected"


def test_outside_quarantine_and_own_rejections_are_ignored(deps):
    put(deps, "somewhere/a.txt")
    put(deps, "rejected/a.txt")
    assert handle(s3_record(BUCKET, "somewhere/a.txt"), deps) == []
    assert handle(s3_record(BUCKET, "rejected/a.txt"), deps) == []
    assert deps.producer.sent == []


def test_object_gone_before_we_arrive_is_ignored(deps):
    assert handle(s3_record(BUCKET, "quarantine/ghost.txt"), deps) == []


def test_removal_deletes_the_row_and_announces(deps):
    put(deps, "quarantine/a.txt", b"hello")
    (up,) = handle(s3_record(BUCKET, "quarantine/a.txt"), deps)
    deps.s3.delete_object(Bucket=BUCKET, Key="quarantine/a.txt")
    (ev,) = handle(s3_record(BUCKET, "quarantine/a.txt", created=False), deps)
    validate(ev)
    assert ev["type"] == "DocumentDeleted" and ev["doc_id"] == up["doc_id"]
    assert ev["data"]["reason"] == "user_request"
    assert "Item" not in deps.table.get_item(Key={"doc_id": up["doc_id"]})


def test_removal_of_unknown_key_is_ignored(deps):
    assert handle(s3_record(BUCKET, "quarantine/never-seen.txt", created=False), deps) == []


def test_parse_accepts_the_eventbridge_shape():
    eb = {
        "detail-type": "Object Created",
        "detail": {"bucket": {"name": BUCKET}, "object": {"key": "quarantine/e.txt"}},
    }
    (rec,) = parse_records(eb)
    assert rec.key == "quarantine/e.txt" and rec.event == "ObjectCreated"
    eb["detail-type"] = "Object Deleted"
    assert parse_records(eb)[0].event == "ObjectRemoved"
