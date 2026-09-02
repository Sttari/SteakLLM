"""Shared fakes: an in-memory consumer/producer pair the loop can't tell from kafka-python's."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from steakllm_common.settings import Settings

REQUIRED_ENV = {"DOCUMENTS_BUCKET": "steakllm-documents", "CATALOG_TABLE": "catalog"}


@pytest.fixture
def settings(monkeypatch) -> Settings:
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)  # never read a .env in unit tests


@dataclass
class FakeRecord:
    topic: str
    value: bytes
    key: bytes | None = None
    headers: list[tuple[str, bytes]] = field(default_factory=list)
    partition: int = 0
    offset: int = 0


@dataclass
class FakeConsumer:
    """Hands out its batches one poll at a time, then stops the loop it is attached to."""

    batches: list[list[FakeRecord]]
    loop: object = None
    commits: int = 0
    closed: bool = False
    next_offset: int = 0

    def poll(self, timeout_ms: int = 0):
        if self.batches:
            batch = self.batches.pop(0)
            for i, rec in enumerate(batch):
                rec.offset = self.next_offset + i
            self.next_offset += len(batch)
            return {("t", 0): batch}
        if self.loop is not None:
            self.loop.stop()
        return {}

    committed: dict = field(default_factory=dict)

    def commit(self, offsets=None):
        self.commits += 1
        if offsets:
            self.committed.update(offsets)

    def close(self):
        self.closed = True


@dataclass
class FakeProducer:
    sent: list[dict] = field(default_factory=list)
    flushes: int = 0

    def send(self, topic, key=None, value=None, headers=None):
        self.sent.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "headers": {k: v.decode() for k, v in (headers or [])},
            }
        )

    def flush(self):
        self.flushes += 1


def record(
    event: dict, topic: str = "documents", headers: dict[str, str] | None = None
) -> FakeRecord:
    return FakeRecord(
        topic=topic,
        value=json.dumps(event).encode(),
        key=(event.get("doc_id") or event.get("id", "")).encode(),
        headers=[(k, v.encode()) for k, v in (headers or {}).items()],
    )
