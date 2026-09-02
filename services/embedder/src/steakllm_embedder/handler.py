"""fetch · verify · extract · chunk · embed · upsert — idempotently.

`point_id(doc_id, i)` is deterministic, so a re-delivered event or a restart mid-batch rewrites the
same points instead of adding new ones. Everything external comes through `Deps` (fakes in tests).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)
from steakllm_common.kafka import produce
from steakllm_common.logging import get_logger
from steakllm_common.settings import Settings
from steakllm_common.text import chunk, extract_text
from steakllm_contracts.ids import doc_id as make_doc_id
from steakllm_contracts.ids import point_id
from steakllm_contracts.validate import validate

log = get_logger(__name__)

EMBED_BATCH = 32


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Deps:
    settings: Settings
    s3: Any
    table: Any
    qdrant: Any
    producer: Any
    embed: Callable[[list[str]], list[list[float]]]
    now: Callable[[], str] = _now


class ShaMismatchError(RuntimeError):
    """The bytes in the bucket are not the bytes the event announced. Retry, then dead-letter."""


def ensure_collection(deps: Deps) -> None:
    """Create the collection and the doc_id payload index if missing. Safe to call every time."""
    s = deps.settings
    if not deps.qdrant.collection_exists(s.qdrant_collection):
        deps.qdrant.create_collection(
            s.qdrant_collection,
            vectors_config=VectorParams(size=s.embedding_dim, distance=Distance.COSINE),
        )
        deps.qdrant.create_payload_index(
            s.qdrant_collection, field_name="doc_id", field_schema=PayloadSchemaType.KEYWORD
        )


def handle(event: dict[str, Any], headers: dict[str, str], deps: Deps) -> None:
    kind = event["type"]
    if kind == "DocumentUploaded":
        _index(event, deps)
    elif kind == "DocumentDeleted":
        _delete(event, deps)
    # every other type is someone else's business


def _index(event: dict[str, Any], deps: Deps) -> None:
    s, d = deps.settings, event["data"]
    doc = event["doc_id"]
    try:
        body = deps.s3.get_object(Bucket=d["bucket"], Key=d["key"])["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
            log.info("object gone; skipped (deleted before indexing)")  # stale event, not poison
            return
        raise
    if make_doc_id(body) != d["sha256"]:
        raise ShaMismatchError(f"sha256 of s3://{d['bucket']}/{d['key']} != announced")
    pieces = chunk(extract_text(body, d["content_type"]))
    vectors: list[list[float]] = []
    for i in range(0, len(pieces), EMBED_BATCH):
        vectors.extend(deps.embed(pieces[i : i + EMBED_BATCH]))
    ensure_collection(deps)
    if pieces:
        deps.qdrant.upsert(
            s.qdrant_collection,
            points=[
                PointStruct(
                    id=point_id(doc, i),
                    vector=v,
                    payload={"doc_id": doc, "chunk_index": i, "text": pieces[i], "key": d["key"]},
                )
                for i, v in enumerate(vectors)
            ],
        )
    # The facts of indexing are always recorded (the summarizer may have finished first: workers
    # run in parallel — Incident 23). Only the status *word* is conditional: never regress
    # `summarized` to `indexed` (Incident 18).
    now = deps.now()
    deps.table.update_item(
        Key={"doc_id": doc},
        UpdateExpression=(
            "SET chunk_count = :n, embedding_model = :m, indexed_at = :now, updated_at = :now"
        ),
        ExpressionAttributeValues={":n": len(pieces), ":m": s.embedding_model, ":now": now},
    )
    try:
        deps.table.update_item(
            Key={"doc_id": doc},
            UpdateExpression="SET #s = :indexed",
            ConditionExpression="attribute_not_exists(#s) OR #s IN (:uploaded, :indexed)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":indexed": "indexed", ":uploaded": "uploaded"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log.info("status already past indexed; facts recorded, word kept", chunk_count=len(pieces))
    ev = {
        "id": str(uuid.uuid4()),
        "type": "DocumentIndexed",
        "version": 1,
        "time": deps.now(),
        "doc_id": doc,
        "trace_id": event["trace_id"],
        "source": "embedder",
        "data": {
            "collection": s.qdrant_collection,
            "chunk_count": len(pieces),
            "embedding_model": s.embedding_model,
            "embedding_dim": s.embedding_dim,
        },
    }
    validate(ev)
    produce(deps.producer, s.topic_documents, ev)
    log.info("indexed", chunk_count=len(pieces), collection=s.qdrant_collection)


def _delete(event: dict[str, Any], deps: Deps) -> None:
    s = deps.settings
    if not deps.qdrant.collection_exists(s.qdrant_collection):
        return
    deps.qdrant.delete(
        s.qdrant_collection,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=event["doc_id"]))]
            )
        ),
    )
    log.info("points deleted", reason=event["data"].get("reason"))
