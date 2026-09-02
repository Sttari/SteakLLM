"""fetch · extract · ask the gateway · parse · record · announce — skipping what is already done.

A re-delivered event for a document that is already `summarized` is a skip *before* any LLM call:
tokens cost money and the second summary would be the same. `DocumentDeleted` clears the summary.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError
from steakllm_common.kafka import produce
from steakllm_common.logging import get_logger
from steakllm_common.settings import Settings
from steakllm_common.text import extract_text
from steakllm_contracts.validate import validate

from .gateway import ChatResult

log = get_logger(__name__)

PROMPT = (
    "You are a careful analyst. Summarize the document in three sentences, then give three short "
    'lowercase topic tags. Answer with JSON only: {"summary": "...", "tags": ["a", "b", "c"]}\n\n'
    "DOCUMENT:\n"
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Deps:
    settings: Settings
    s3: Any
    table: Any
    producer: Any
    chat: Callable[[str], ChatResult]
    now: Callable[[], str] = _now


class BadModelOutputError(ValueError):
    """The model did not answer with the JSON we asked for. Retrying usually fixes it."""


def parse_model_output(text: str) -> tuple[str, list[str]]:
    """Lenient: strips code fences and anything around the first {...} block."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise BadModelOutputError(f"no JSON object in model output: {text[:120]!r}")
    try:
        obj = json.loads(m.group(0))
    except ValueError as e:
        raise BadModelOutputError(f"invalid JSON from model: {e}") from e
    summary = str(obj.get("summary", "")).strip()
    tags = [str(t).strip().lower() for t in obj.get("tags", []) if str(t).strip()]
    if not summary:
        raise BadModelOutputError("model output has no summary")
    seen: list[str] = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return summary[:8000], seen[:32]


def handle(event: dict[str, Any], headers: dict[str, str], deps: Deps) -> None:
    kind = event["type"]
    if kind == "DocumentUploaded":
        _summarize(event, deps)
    elif kind == "DocumentDeleted":
        _clear(event, deps)


def _summarize(event: dict[str, Any], deps: Deps) -> None:
    s, d, doc = deps.settings, event["data"], event["doc_id"]
    row = deps.table.get_item(Key={"doc_id": doc}).get("Item") or {}
    if row.get("status") == "summarized":
        log.info("already summarized; skipped before any LLM call")
        return
    body = deps.s3.get_object(Bucket=d["bucket"], Key=d["key"])["Body"].read()
    text = extract_text(body, d["content_type"])[: s.summarizer_max_chars]
    result = deps.chat(PROMPT + text)
    summary, tags = parse_model_output(result.text)
    deps.table.update_item(
        Key={"doc_id": doc},
        UpdateExpression=(
            "SET #s = :summarized, summary = :sum, tags = :tags, summary_model = :m, "
            "summary_backend = :b, summarized_at = :now, updated_at = :now"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":summarized": "summarized",
            ":sum": summary,
            ":tags": tags,
            ":m": result.model,
            ":b": result.backend,
            ":now": deps.now(),
        },
    )
    ev = {
        "id": str(uuid.uuid4()),
        "type": "SummaryReady",
        "version": 1,
        "time": deps.now(),
        "doc_id": doc,
        "trace_id": event["trace_id"],
        "source": "summarizer",
        "data": {
            "summary": summary,
            "tags": tags,
            "model": result.model,
            "backend": result.backend,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
        },
    }
    validate(ev)
    produce(deps.producer, s.topic_documents, ev)
    log.info(
        "summarized",
        backend=result.backend,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tags=tags,
    )


def _clear(event: dict[str, Any], deps: Deps) -> None:
    try:
        deps.table.update_item(
            Key={"doc_id": event["doc_id"]},
            UpdateExpression="REMOVE summary, tags, summary_model, summary_backend, summarized_at",
            ConditionExpression="attribute_exists(doc_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return  # no row (ingest already deleted it, or it never existed): nothing to clear
    log.info("summary cleared", reason=event["data"].get("reason"))
