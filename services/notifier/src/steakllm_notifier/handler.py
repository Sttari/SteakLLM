"""match · claim · send. A notification cannot be upserted, so it is claimed by event id first.

`SummaryReady` → does the watch-list match the tags or the summary? → conditional catalog write that
adds the event id to `notified_event_ids` (refused if already there, or if the document is gone) →
send through the sink. A replayed event is a skip; a new SummaryReady for the same document notifies
again (a new fact). A crash between claim and send loses one notification rather than sending twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError
from steakllm_common.logging import get_logger
from steakllm_common.settings import Settings

from .sinks import Notification, Sink

log = get_logger(__name__)


@dataclass
class Deps:
    settings: Settings
    table: Any
    sink: Sink


def matches(watch_list: list[str], tags: list[str], summary: str) -> list[str]:
    """Terms that hit: exact (case-insensitive) on a tag, or substring in the summary."""
    tagset = {t.lower() for t in tags}
    text = summary.lower()
    return [w for w in watch_list if w.lower() in tagset or w.lower() in text]


def handle(event: dict[str, Any], headers: dict[str, str], deps: Deps) -> None:
    if event["type"] != "SummaryReady":
        return
    d, doc, eid = event["data"], event["doc_id"], event["id"]
    hits = matches(deps.settings.watch_list, d.get("tags", []), d.get("summary", ""))
    if not hits:
        log.info("no match", tags=d.get("tags", []))
        return
    try:
        deps.table.update_item(
            Key={"doc_id": doc},
            UpdateExpression="ADD notified_event_ids :ids",
            ConditionExpression=(
                "attribute_exists(doc_id) AND (attribute_not_exists(notified_event_ids) "
                "OR NOT contains(notified_event_ids, :id))"
            ),
            ExpressionAttributeValues={":ids": {eid}, ":id": eid},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log.info("already notified for this event, or document gone; skipped")
        return
    deps.sink.send(
        Notification(
            subject=f"SteakLLM: new document matches {', '.join(hits)}",
            body=d.get("summary", ""),
            doc_id=doc,
            event_id=eid,
            tags=list(d.get("tags", [])),
        )
    )
    log.info("notified", hits=hits)
