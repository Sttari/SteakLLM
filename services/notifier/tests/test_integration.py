"""On the real stack (make up): the claim is exactly-once on real DynamoDB Local."""

from __future__ import annotations

import json
import uuid

import pytest
from steakllm_common.clients import catalog_table
from steakllm_common.settings import Settings
from steakllm_contracts import EXAMPLE_DIR

from steakllm_notifier.handler import Deps, handle
from steakllm_notifier.sinks import StdoutSink

pytestmark = pytest.mark.integration


def test_claim_is_exactly_once_on_real_dynamodb():
    s = Settings()
    table = catalog_table(s)
    ev = json.loads((EXAMPLE_DIR / "SummaryReady.json").read_text())
    ev["id"] = str(uuid.uuid4())
    ev["doc_id"] = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex, unique to this run
    ev["data"]["tags"] = ["finance"]
    table.put_item(Item={"doc_id": ev["doc_id"], "status": "summarized"})
    deps = Deps(settings=s, table=table, sink=StdoutSink())
    try:
        handle(ev, {}, deps)
        handle(ev, {}, deps)
        assert len(deps.sink.sent) == 1
        row = table.get_item(Key={"doc_id": ev["doc_id"]})["Item"]
        assert row["notified_event_ids"] == {ev["id"]}
    finally:
        table.delete_item(Key={"doc_id": ev["doc_id"]})
