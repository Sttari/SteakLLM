"""On real Kafka (make up): a poison event travels topic → .retry → .dlq with its headers intact.

Uses throwaway topics so the shared `documents*` topics are never polluted.
"""

import json
import threading
import time
import uuid

import pytest
from steakllm_contracts import EXAMPLE_DIR

from steakllm_common.kafka import ConsumerLoop, RetryPolicy, make_consumer, make_producer, produce
from steakllm_common.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def topics(monkeypatch):
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic

    base = f"it-{uuid.uuid4().hex[:8]}"
    names = [base, f"{base}.retry", f"{base}.dlq"]
    monkeypatch.setenv("DOCUMENTS_BUCKET", "x")
    monkeypatch.setenv("CATALOG_TABLE", "x")
    s = Settings(_env_file=None)
    admin = KafkaAdminClient(bootstrap_servers=s.kafka_bootstrap)
    admin.create_topics([NewTopic(n, num_partitions=1, replication_factor=1) for n in names])
    try:
        yield s, names
    finally:
        admin.delete_topics(names)
        admin.close()


def test_poison_event_lands_in_the_dead_letter_topic_with_headers(topics):
    s, (topic, retry, dlq) = topics
    event = json.loads((EXAMPLE_DIR / "DocumentUploaded.json").read_text())
    producer = make_producer(s)
    produce(producer, topic, event).get(timeout=10)
    producer.flush()

    def always_fails(ev, headers):
        raise RuntimeError("poison")

    consumer = make_consumer(s, group=f"it-{uuid.uuid4().hex[:6]}", topics=[topic, retry])
    loop = ConsumerLoop(
        consumer=consumer,
        producer=producer,
        handler=always_fails,
        retry_topic=retry,
        dlq_topic=dlq,
        policy=RetryPolicy(attempts=3, backoff_seconds=(0.01, 0.01, 0.01), max_attempts=6),
        install_signal_handlers=False,
    )
    t = threading.Thread(target=loop.run, daemon=True)
    t.start()

    from kafka import KafkaConsumer

    reader = KafkaConsumer(
        dlq,
        bootstrap_servers=s.kafka_bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=30000,
    )
    deadline = time.time() + 40
    parked = None
    for msg in reader:
        parked = msg
        break
    loop.stop()
    t.join(timeout=15)
    assert parked is not None, "nothing reached the dead-letter topic within the deadline"
    assert time.time() < deadline
    headers = {k: v.decode() for k, v in parked.headers}
    assert headers["x-attempts"] == "6"
    assert "poison" in headers["x-last-error"]
    assert headers["x-origin-topic"] == "documents"
    assert json.loads(parked.value)["id"] == event["id"]  # the event itself is unchanged
