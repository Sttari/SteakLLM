"""validate · hash · record · produce · walk away.

One S3 event record in, zero or one contract event out. Everything external comes through `Deps`,
so the handler runs unchanged in Lambda, in the local runner, and in tests on moto + fakes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from posixpath import basename
from typing import Any

from botocore.exceptions import ClientError
from steakllm_common.kafka import produce
from steakllm_common.logging import bound, get_logger
from steakllm_common.settings import Settings
from steakllm_contracts.ids import doc_id_from_stream
from steakllm_contracts.validate import validate

log = get_logger(__name__)

REJECTED_PREFIX = "rejected/"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Deps:
    settings: Settings
    s3: Any
    table: Any
    producer: Any
    now: Callable[[], str] = _now
    new_trace_id: Callable[[], str] = field(default=lambda: uuid.uuid4().hex)


@dataclass(frozen=True)
class S3Record:
    bucket: str
    key: str
    event: str  # "ObjectCreated" | "ObjectRemoved"


def parse_records(event: dict[str, Any]) -> list[S3Record]:
    """Accept both shapes: the S3 notification (`Records[]`) and EventBridge's (`detail`)."""
    out: list[S3Record] = []
    for r in event.get("Records", []):
        name = r.get("eventName", "")
        kind = "ObjectCreated" if name.startswith("ObjectCreated") else "ObjectRemoved"
        out.append(S3Record(r["s3"]["bucket"]["name"], r["s3"]["object"]["key"], kind))
    if "detail" in event and "detail-type" in event:
        d = event["detail"]
        kind = "ObjectCreated" if "Created" in event["detail-type"] else "ObjectRemoved"
        out.append(S3Record(d["bucket"]["name"], d["object"]["key"], kind))
    return out


def _envelope(type_: str, source: str, doc: str, trace: str, data: dict, now: str) -> dict:
    ev = {
        "id": str(uuid.uuid4()),
        "type": type_,
        "version": 1,
        "time": now,
        "doc_id": doc,
        "trace_id": trace,
        "source": source,
        "data": data,
    }
    validate(ev)
    return ev


def handle(event: dict[str, Any], deps: Deps) -> list[dict[str, Any]]:
    """Handle every record in an S3 / EventBridge event. Returns the contract events produced."""
    produced: list[dict[str, Any]] = []
    for rec in parse_records(event):
        trace = deps.new_trace_id()
        with bound(trace_id=trace, key=rec.key):
            if rec.event == "ObjectCreated":
                ev = _created(rec, deps, trace)
            else:
                ev = _removed(rec, deps, trace)
            if ev:
                produced.append(ev)
    if produced:
        deps.producer.flush()
    return produced


def _created(rec: S3Record, deps: Deps, trace: str) -> dict[str, Any] | None:
    s = deps.settings
    if rec.key.startswith(REJECTED_PREFIX):
        return None  # our own move; never re-ingest a rejection
    if not rec.key.startswith(s.quarantine_prefix):
        log.warning("ignored: outside the quarantine prefix")
        return None
    try:
        head = deps.s3.head_object(Bucket=rec.bucket, Key=rec.key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            log.warning("ignored: object already gone")  # deleted before we got here
            return None
        raise
    size, ctype = head["ContentLength"], head.get("ContentType", "application/octet-stream")
    body = deps.s3.get_object(Bucket=rec.bucket, Key=rec.key)["Body"]
    doc = doc_id_from_stream(body)
    reason = None
    if size > s.upload_max_bytes:
        reason = f"too large: {size} > {s.upload_max_bytes}"
    elif ctype.split(";")[0].strip() not in s.upload_content_types:
        reason = f"content type not allowed: {ctype}"
    with bound(doc_id=doc):
        if reason:
            return _reject(rec, deps, doc, trace, reason)
        deps.table.update_item(
            Key={"doc_id": doc},
            # never regress a document that is already indexed/summarized (at-least-once delivery)
            UpdateExpression=(
                "SET #s = if_not_exists(#s, :uploaded), #k = :k, size_bytes = :sz, "
                "content_type = :ct, trace_id = :tr, updated_at = :now, "
                "uploaded_at = if_not_exists(uploaded_at, :now)"
            ),
            ExpressionAttributeNames={"#s": "status", "#k": "key"},
            ExpressionAttributeValues={
                ":uploaded": "uploaded",
                ":k": rec.key,
                ":sz": size,
                ":ct": ctype,
                ":tr": trace,
                ":now": deps.now(),
            },
        )
        ev = _envelope(
            "DocumentUploaded",
            "ingest",
            doc,
            trace,
            {
                "bucket": rec.bucket,
                "key": rec.key,
                "size_bytes": size,
                "content_type": ctype,
                "sha256": doc,
            },
            deps.now(),
        )
        produce(deps.producer, s.topic_documents, ev)
        log.info("uploaded", size_bytes=size, content_type=ctype)
        return ev


def _reject(rec: S3Record, deps: Deps, doc: str, trace: str, reason: str) -> dict[str, Any]:
    s = deps.settings
    dest = f"{REJECTED_PREFIX}{basename(rec.key)}"
    deps.s3.copy_object(
        Bucket=rec.bucket, CopySource={"Bucket": rec.bucket, "Key": rec.key}, Key=dest
    )
    deps.s3.delete_object(Bucket=rec.bucket, Key=rec.key)
    ev = _envelope(
        "DocumentDeleted",
        "ingest",
        doc,
        trace,
        {"reason": "quarantine_rejected"},
        deps.now(),
    )
    produce(deps.producer, s.topic_documents, ev)
    log.warning("rejected", reason=reason, moved_to=dest)
    return ev


def _removed(rec: S3Record, deps: Deps, trace: str) -> dict[str, Any] | None:
    """An object left the quarantine prefix (not by us): the document is gone everywhere."""
    s = deps.settings
    if not rec.key.startswith(s.quarantine_prefix):
        return None
    doc = _doc_id_for_key(deps, rec.key)
    if not doc:
        log.warning("ignored: no catalog row for the removed key")
        return None
    with bound(doc_id=doc):
        deps.table.delete_item(Key={"doc_id": doc})
        ev = _envelope(
            "DocumentDeleted", "ingest", doc, trace, {"reason": "user_request"}, deps.now()
        )
        produce(deps.producer, s.topic_documents, ev)
        log.info("deleted")
        return ev


def _doc_id_for_key(deps: Deps, key: str) -> str | None:
    """Catalog lookup by object key. A scan is fine for a laptop; Step 10 adds an index."""
    resp = deps.table.scan(
        FilterExpression="#k = :k",
        ExpressionAttributeNames={"#k": "key"},
        ExpressionAttributeValues={":k": key},
        ProjectionExpression="doc_id",
    )
    items = resp.get("Items", [])
    return items[0]["doc_id"] if items else None
