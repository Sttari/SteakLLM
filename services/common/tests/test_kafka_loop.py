"""The consumer loop's contract on fakes: retries, retry topic, dead-letter topic, commits,
skips."""

import json

import pytest
from conftest import FakeConsumer, FakeProducer, FakeRecord, record
from steakllm_contracts import EXAMPLE_DIR

from steakllm_common.kafka import ConsumerLoop, RetryPolicy, headers_to_dict, produce

FAST = RetryPolicy(attempts=3, backoff_seconds=(0.0, 0.0, 0.0), max_attempts=6)


def example(name: str) -> dict:
    return json.loads((EXAMPLE_DIR / f"{name}.json").read_text())


def make_loop(batches, handler, policy=FAST):
    consumer, producer = FakeConsumer(batches), FakeProducer()
    sleeps: list[float] = []
    loop = ConsumerLoop(
        consumer=consumer,
        producer=producer,
        handler=handler,
        retry_topic="documents.retry",
        dlq_topic="documents.dlq",
        policy=policy,
        sleep=sleeps.append,
        install_signal_handlers=False,
    )
    consumer.loop = loop
    return loop, consumer, producer, sleeps


def test_happy_path_handles_and_commits_after_the_batch():
    seen = []
    loop, consumer, producer, _ = make_loop(
        [[record(example("DocumentUploaded")), record(example("DocumentIndexed"))]],
        lambda ev, h: seen.append(ev["type"]),
    )
    loop.run()
    assert seen == ["DocumentUploaded", "DocumentIndexed"]
    assert consumer.commits == 1 and consumer.closed
    assert producer.sent == [] and loop.handled == 2
    (pos,) = consumer.committed.values()
    assert pos.offset == 2  # explicit: both handled → next offset 2


def test_failure_is_retried_with_backoff_then_parked_on_the_retry_topic():
    calls = []

    def bad(ev, h):
        calls.append(1)
        raise RuntimeError("qdrant down")

    loop, consumer, producer, sleeps = make_loop(
        [[record(example("DocumentUploaded"))]], bad, RetryPolicy(3, (0.1, 0.2, 0.4), 6)
    )
    loop.run()
    assert len(calls) == 3 and sleeps == [0.1, 0.2]  # 3 attempts, 2 waits between them
    (parked,) = producer.sent
    assert parked["topic"] == "documents.retry"
    assert parked["headers"]["x-attempts"] == "3"
    assert "qdrant down" in parked["headers"]["x-last-error"]
    assert parked["headers"]["x-origin-topic"] == "documents"
    assert json.loads(parked["value"])["id"] == example("DocumentUploaded")["id"]  # unchanged
    assert consumer.commits == 1  # the log keeps moving


def test_second_delivery_from_the_retry_topic_goes_to_the_dead_letter_topic():
    def bad(ev, h):
        raise RuntimeError("still down")

    rec = record(example("DocumentUploaded"), topic="documents.retry", headers={"x-attempts": "3"})
    loop, _, producer, _ = make_loop([[rec]], bad)
    loop.run()
    (parked,) = producer.sent
    assert parked["topic"] == "documents.dlq"
    assert parked["headers"]["x-attempts"] == "6"


def test_unknown_event_type_is_skipped_not_failed():
    called = []
    loop, consumer, producer, _ = make_loop(
        [[record({"id": "x", "type": "SomethingNew", "data": {}})]], lambda ev, h: called.append(1)
    )
    loop.run()
    assert called == [] and producer.sent == [] and consumer.commits == 1


def test_invalid_json_goes_straight_to_the_dead_letter_topic():
    loop, _, producer, _ = make_loop([[FakeRecord("documents", b"{not json")]], lambda ev, h: None)
    loop.run()
    (parked,) = producer.sent
    assert (
        parked["topic"] == "documents.dlq" and "invalid json" in parked["headers"]["x-last-error"]
    )


def test_handler_sees_the_headers():
    seen = {}
    rec = record(
        example("SummaryReady"), headers={"x-attempts": "3", "x-origin-topic": "documents"}
    )
    loop, *_ = make_loop([[rec]], lambda ev, h: seen.update(h))
    loop.run()
    assert seen["x-attempts"] == "3"


def test_produce_keys_by_doc_id_and_serialises_headers():
    producer = FakeProducer()
    produce(producer, "documents", example("DocumentUploaded"), {"x-a": "1"})
    (sent,) = producer.sent
    assert sent["key"] == example("DocumentUploaded")["doc_id"].encode()
    assert sent["headers"] == {"x-a": "1"}
    assert json.loads(sent["value"])["type"] == "DocumentUploaded"


def test_chat_completed_is_keyed_by_event_id_when_doc_id_is_null():
    producer = FakeProducer()
    ev = example("ChatCompleted")
    produce(producer, "chats", ev)
    assert producer.sent[0]["key"] == ev["id"].encode()


def test_stop_mid_batch_commits_only_what_was_handled():
    events = [record(example("DocumentUploaded")) for _ in range(5)]
    loop, consumer, producer, _ = make_loop([events], lambda ev, h: None)

    seen = []

    def stop_after_two(ev, h):
        seen.append(1)
        if len(seen) == 2:
            loop.stop(15)

    loop.handler = stop_after_two
    loop.run()
    assert loop.handled == 2
    (pos,) = consumer.committed.values()
    assert pos.offset == 2  # offsets 0 and 1 handled → next is 2; records 2–4 stay uncommitted


def test_stop_then_second_signal_exits():
    loop, *_ = make_loop([], lambda ev, h: None)
    loop.stop(15)
    with pytest.raises(SystemExit):
        loop.stop(15)


def test_headers_to_dict_decodes_bytes():
    assert headers_to_dict([("a", b"1"), ("b", b"x")]) == {"a": "1", "b": "x"}
    assert headers_to_dict(None) == {}
