"""On the real stack (make up): an event on `documents` becomes points; a repeat changes nothing.

Runs the real service loop in a thread with a throwaway consumer group, on a unique Markdown
document, so the shared collection is only touched by this test's own points (deleted at the end).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from functools import partial

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue
from steakllm_common.clients import catalog_table, embed, qdrant_client, s3_client
from steakllm_common.kafka import ConsumerLoop, RetryPolicy, make_consumer, make_producer, produce
from steakllm_common.logging import configure
from steakllm_common.settings import Settings
from steakllm_contracts.ids import doc_id
from steakllm_contracts.validate import validate

from steakllm_embedder.handler import Deps, ensure_collection, handle

pytestmark = pytest.mark.integration


def count(deps: Deps, doc: str) -> int:
    return deps.qdrant.count(
        deps.settings.qdrant_collection,
        count_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc))]),
        exact=True,
    ).count


def wait_for(pred, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.5)
    return False


def test_event_on_the_topic_becomes_points_and_a_second_one_changes_nothing():
    configure("embedder-it")
    s = Settings()  # the repo's env file (run from the repo root)
    deps = Deps(
        settings=s,
        s3=s3_client(s),
        table=catalog_table(s),
        qdrant=qdrant_client(s),
        producer=make_producer(s),
        embed=partial(embed, s),
    )
    ensure_collection(deps)
    body = f"# Integration {uuid.uuid4()}\n\n" + ("integration test paragraph. " * 60)
    body_b = body.encode()
    doc = doc_id(body_b)
    key = f"{s.quarantine_prefix}it/{doc[:12]}.md"
    deps.s3.put_object(Bucket=s.documents_bucket, Key=key, Body=body_b, ContentType="text/markdown")
    ev = {
        "id": str(uuid.uuid4()),
        "type": "DocumentUploaded",
        "version": 1,
        "time": "2026-09-02T21:00:00Z",
        "doc_id": doc,
        "trace_id": uuid.uuid4().hex,
        "source": "ingest",
        "data": {
            "bucket": s.documents_bucket,
            "key": key,
            "size_bytes": len(body_b),
            "content_type": "text/markdown",
            "sha256": doc,
        },
    }
    validate(ev)

    consumer = make_consumer(
        s, group=f"it-embedder-{uuid.uuid4().hex[:6]}", topics=[s.topic_documents]
    )
    loop = ConsumerLoop(
        consumer=consumer,
        producer=deps.producer,
        handler=lambda e, h: handle(e, h, deps),
        retry_topic=s.topic_documents_retry,
        dlq_topic=s.topic_documents_dlq,
        policy=RetryPolicy(3, (0.1, 0.1, 0.1), 6),
        install_signal_handlers=False,
    )
    t = threading.Thread(target=loop.run, daemon=True)
    t.start()
    try:
        produce(deps.producer, s.topic_documents, ev).get(timeout=10)
        assert wait_for(lambda: count(deps, doc) > 0, 90), "no points appeared within 90 s"
        n = count(deps, doc)
        row = deps.table.get_item(Key={"doc_id": doc}).get("Item", {})
        assert row.get("status") == "indexed" and int(row["chunk_count"]) == n

        produce(deps.producer, s.topic_documents, {**ev, "id": str(uuid.uuid4())}).get(timeout=10)
        time.sleep(3)  # let the loop handle it
        assert count(deps, doc) == n  # idempotent: same points, same count
    finally:
        loop.stop()
        t.join(timeout=15)
        handle({**ev, "type": "DocumentDeleted", "data": {"reason": "retention"}}, {}, deps)
        deps.table.delete_item(Key={"doc_id": doc})
        deps.s3.delete_object(Bucket=s.documents_bucket, Key=key)
    assert count(deps, doc) == 0
    assert json.dumps(ev)  # (the event was serialisable all along)
