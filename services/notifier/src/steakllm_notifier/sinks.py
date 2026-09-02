"""Where notifications go. One interface, two homes: stdout on the laptop, SNS in the cloud."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from steakllm_common.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Notification:
    subject: str
    body: str
    doc_id: str
    event_id: str
    tags: list[str]


class Sink(Protocol):
    def send(self, n: Notification) -> None: ...


@dataclass
class StdoutSink:
    """Local: one JSON log line per notification (msg=notification), nothing else."""

    sent: list[Notification] = field(default_factory=list)

    def send(self, n: Notification) -> None:
        self.sent.append(n)
        log.info("notification", subject=n.subject, body=n.body, tags=n.tags, event_id=n.event_id)


@dataclass
class SnsSink:
    client: Any
    topic_arn: str

    def send(self, n: Notification) -> None:
        self.client.publish(
            TopicArn=self.topic_arn,
            Subject=n.subject[:100],
            Message=json.dumps(
                {"body": n.body, "doc_id": n.doc_id, "event_id": n.event_id, "tags": n.tags}
            ),
            MessageAttributes={
                "doc_id": {"DataType": "String", "StringValue": n.doc_id},
                "event_id": {"DataType": "String", "StringValue": n.event_id},
            },
        )
