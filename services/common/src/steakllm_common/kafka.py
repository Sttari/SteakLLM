"""The producer and the consumer loop: the retry / dead-letter policy and graceful shutdown as code.

Policy (services/README.md): a handler failure is retried in place `attempts` times with backoff;
still failing, the event is produced unchanged to the retry topic with headers (`x-attempts`,
`x-last-error`, `x-origin-topic`) and the offset is committed so the log keeps moving. The same loop
also consumes the retry topic; after `max_attempts` total the event goes to the dead-letter topic.
Nothing is dropped
silently. Offsets are committed after a batch is fully handled. SIGTERM finishes the batch in hand.

The loop takes its consumer and producer as objects (kafka-python's, or fakes in tests).
"""

from __future__ import annotations

import json
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from steakllm_contracts import EVENT_TYPES

from .logging import bound, event_fields, get_logger
from .settings import Settings

log = get_logger(__name__)

Handler = Callable[[dict[str, Any], dict[str, str]], None]


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3  # in-place attempts per delivery
    backoff_seconds: tuple[float, ...] = (1.0, 4.0, 16.0)
    max_attempts: int = 6  # total across deliveries before the dead-letter topic

    @classmethod
    def from_settings(cls, s: Settings) -> RetryPolicy:
        return cls(
            attempts=s.retry_attempts,
            backoff_seconds=tuple(s.retry_backoff_seconds),
            max_attempts=s.retry_attempts * 2,
        )


class Record(Protocol):  # the subset of kafka-python's ConsumerRecord the loop uses
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes
    headers: list[tuple[str, bytes]]


def make_producer(s: Settings):
    from kafka import KafkaProducer

    return KafkaProducer(bootstrap_servers=s.kafka_bootstrap, acks="all", linger_ms=5)


def make_consumer(s: Settings, group: str, topics: list[str]):
    from kafka import KafkaConsumer

    c = KafkaConsumer(
        bootstrap_servers=s.kafka_bootstrap,
        group_id=group,
        enable_auto_commit=False,  # the loop commits what it handled, never before
        auto_offset_reset="earliest",
        max_poll_records=s.consumer_batch_size,
        # A killed member holds its partitions until its session expires; 10 s, not the broker's
        # 45 s default, is the price of a hard kill we are willing to pay (chaos drill 1).
        session_timeout_ms=10_000,
        heartbeat_interval_ms=3_000,
    )
    c.subscribe(topics)
    return c


def produce(producer, topic: str, event: dict[str, Any], headers: dict[str, str] | None = None):
    """Send one event. Key = doc_id (one document's events stay ordered in one partition) or id."""
    key = (event.get("doc_id") or event["id"]).encode()
    hdrs = [(k, v.encode()) for k, v in (headers or {}).items()]
    return producer.send(topic, key=key, value=json.dumps(event).encode(), headers=hdrs)


def _next(rec: Record):
    """The commit position after ``rec``: kafka-python wants OffsetAndMetadata(offset + 1)."""
    try:
        from kafka import OffsetAndMetadata

        return OffsetAndMetadata(rec.offset + 1, "", -1)
    except ImportError:  # pragma: no cover
        return rec.offset + 1


def headers_to_dict(headers: list[tuple[str, bytes]] | None) -> dict[str, str]:
    return {k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in (headers or [])}


@dataclass
class ConsumerLoop:
    consumer: Any
    producer: Any
    handler: Handler
    retry_topic: str
    dlq_topic: str
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    poll_timeout_ms: int = 1000
    sleep: Callable[[float], None] = time.sleep
    install_signal_handlers: bool = True
    _stopping: bool = field(default=False, init=False)
    handled: int = field(default=0, init=False)

    # -- lifecycle -----------------------------------------------------------------------------
    def stop(self, signum: int | None = None, _frame: Any = None) -> None:
        if self._stopping:  # second signal: leave now
            log.warning("second signal, exiting immediately", signal=signum)
            sys.exit(130)
        self._stopping = True
        log.info("stopping after the batch in hand", signal=signum)

    def run(self) -> None:
        if self.install_signal_handlers:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, self.stop)
        try:
            while not self._stopping:
                batch = self.consumer.poll(timeout_ms=self.poll_timeout_ms)
                if not batch:
                    continue
                positions: dict[Any, Any] = {}  # partition -> next offset, for what we handled
                for tp, records in batch.items():
                    for rec in records:
                        self.handle_record(rec)
                        positions[tp] = _next(rec)
                        if self._stopping:  # SIGTERM: finish this record, not the batch
                            break
                    if self._stopping:
                        break
                self.producer.flush()
                # explicit offsets: a bare commit() would commit the whole polled batch, including
                # records we never handled when stopping early (chaos drill 1)
                self.consumer.commit(positions)
        finally:
            self.producer.flush()
            self.consumer.close()
            log.info("consumer closed", handled=self.handled)

    # -- one record ----------------------------------------------------------------------------
    def handle_record(self, rec: Record) -> None:
        headers = headers_to_dict(rec.headers)
        prior = int(headers.get("x-attempts", "0"))
        try:
            event = json.loads(rec.value)
            assert isinstance(event, dict)
        except (ValueError, AssertionError) as e:
            self._park(rec.value, rec.key, headers, self.dlq_topic, prior, f"invalid json: {e}")
            return
        if event.get("type") not in EVENT_TYPES:  # tolerant reader: skip, never fail
            log.warning("unknown event type skipped", event_type=event.get("type"), topic=rec.topic)
            return
        with bound(**event_fields(event)):
            last: BaseException | None = None
            for i in range(self.policy.attempts):
                try:
                    self.handler(event, headers)
                    self.handled += 1
                    return
                except Exception as e:  # noqa: BLE001 — the loop is the boundary; failures are routed
                    last = e
                    log.warning("handler failed", attempt=prior + i + 1, error=repr(e))
                    if i < self.policy.attempts - 1:
                        self.sleep(
                            self.policy.backoff_seconds[
                                min(i, len(self.policy.backoff_seconds) - 1)
                            ]
                        )
            total = prior + self.policy.attempts
            dest = self.dlq_topic if total >= self.policy.max_attempts else self.retry_topic
            self._park(rec.value, rec.key, headers, dest, total, repr(last))

    def _park(
        self,
        value: bytes,
        key: bytes | None,
        headers: dict[str, str],
        dest: str,
        attempts: int,
        err: str,
    ) -> None:
        hdrs = {
            **headers,
            "x-attempts": str(attempts),
            "x-last-error": err[:500],
            "x-origin-topic": headers.get("x-origin-topic") or "documents",
        }
        self.producer.send(
            dest, key=key, value=value, headers=[(k, v.encode()) for k, v in hdrs.items()]
        )
        level = log.error if dest == self.dlq_topic else log.warning
        level("event parked", destination=dest, attempts=attempts, error=err[:200])
