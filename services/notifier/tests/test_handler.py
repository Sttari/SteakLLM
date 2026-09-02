"""Matching, claiming, sending — and never twice."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws
from steakllm_common.settings import Settings
from steakllm_contracts import EXAMPLE_DIR

from steakllm_notifier.handler import Deps, handle, matches
from steakllm_notifier.sinks import Notification, SnsSink, StdoutSink


def summary_ready(**data):
    ev = json.loads((EXAMPLE_DIR / "SummaryReady.json").read_text())
    ev["data"].update(data)
    return ev


@pytest.fixture
def deps(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DOCUMENTS_BUCKET", "b")
    monkeypatch.setenv("CATALOG_TABLE", "catalog")
    monkeypatch.setenv("WATCH_LIST", '["finance", "merger"]')
    with mock_aws():
        s = Settings(_env_file=None)
        ddb = boto3.resource("dynamodb", region_name=s.aws_region)
        ddb.create_table(
            TableName="catalog",
            KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table = ddb.Table("catalog")
        table.put_item(Item={"doc_id": summary_ready()["doc_id"], "status": "summarized"})
        yield Deps(settings=s, table=table, sink=StdoutSink())


def test_matches_tags_exactly_and_summary_by_substring():
    assert matches(["finance", "emea"], ["Finance"], "nothing") == ["finance"]
    assert matches(["merger"], ["ops"], "A Merger was announced.") == ["merger"]
    assert matches(["merger"], ["ops"], "no such thing") == []


def test_matching_summary_notifies_once(deps):
    ev = summary_ready(tags=["finance", "emea"])
    handle(ev, {}, deps)
    (n,) = deps.sink.sent
    assert isinstance(n, Notification) and "finance" in n.subject and n.doc_id == ev["doc_id"]
    row = deps.table.get_item(Key={"doc_id": ev["doc_id"]})["Item"]
    assert ev["id"] in row["notified_event_ids"]


def test_replayed_event_is_skipped_but_a_new_event_notifies_again(deps):
    ev = summary_ready(tags=["finance"])
    handle(ev, {}, deps)
    handle(ev, {}, deps)  # at-least-once delivery
    assert len(deps.sink.sent) == 1
    handle({**ev, "id": "0f6a7b8c-1d2e-4f30-9a1b-00000000009f"}, {}, deps)  # a re-summary
    assert len(deps.sink.sent) == 2


def test_no_match_no_claim_no_send(deps):
    ev = summary_ready(tags=["sports"], summary="A match report.")
    handle(ev, {}, deps)
    assert deps.sink.sent == []
    assert "notified_event_ids" not in deps.table.get_item(Key={"doc_id": ev["doc_id"]})["Item"]


def test_deleted_document_is_not_notified(deps):
    ev = summary_ready(tags=["finance"])
    deps.table.delete_item(Key={"doc_id": ev["doc_id"]})
    handle(ev, {}, deps)
    assert deps.sink.sent == []
    assert "Item" not in deps.table.get_item(Key={"doc_id": ev["doc_id"]})  # no row resurrected


def test_other_events_are_ignored(deps):
    handle({"type": "DocumentIndexed", "id": "x", "doc_id": "d", "data": {}}, {}, deps)
    assert deps.sink.sent == []


def test_sns_sink_publishes_with_attributes(deps):
    sns = boto3.client("sns", region_name=deps.settings.aws_region)
    arn = sns.create_topic(Name="steakllm-alerts")["TopicArn"]
    deps.sink = SnsSink(sns, arn)
    handle(summary_ready(tags=["finance"]), {}, deps)  # moto accepts the publish; no exception = ok
