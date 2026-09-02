"""Uploads (presigned PUT into quarantine/), deletes (one event, four consumers), the catalog."""

from __future__ import annotations

import html
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from steakllm_common.kafka import produce
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def presign_upload(
    s3: Any, s: Settings, filename: str, content_type: str, size_bytes: int
) -> dict[str, Any]:
    """A five-minute PUT URL straight into quarantine/. Type and size are checked here for a fast
    answer and again by ingest after the upload (a presigned PUT cannot enforce Content-Length)."""
    ctype = content_type.split(";")[0].strip().lower()
    if ctype not in s.upload_content_types:
        raise ValueError(f"content type not allowed: {content_type}")
    if size_bytes <= 0 or size_bytes > s.upload_max_bytes:
        raise OverflowError(f"size must be 1..{s.upload_max_bytes} bytes")
    name = _SAFE.sub("-", filename).strip("-") or "upload"
    key = f"{s.quarantine_prefix}{datetime.now(UTC):%Y/%m/%d}/{uuid.uuid4().hex[:8]}-{name}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": s.documents_bucket, "Key": key, "ContentType": ctype},
        ExpiresIn=s.presign_expires_seconds,
    )
    return {
        "url": url,
        "method": "PUT",
        "headers": {"Content-Type": ctype},
        "key": key,
        "expires_in": s.presign_expires_seconds,
    }


def delete_document(
    s3: Any, table: Any, producer: Any, s: Settings, doc_id: str, key_id: str, now: str
) -> bool:
    """Remove the object and the row, announce DocumentDeleted. False if unknown."""
    row = table.get_item(Key={"doc_id": doc_id}).get("Item")
    if not row:
        return False
    if row.get("key"):
        s3.delete_object(Bucket=s.documents_bucket, Key=row["key"])
    table.delete_item(Key={"doc_id": doc_id})
    ev = {
        "id": str(uuid.uuid4()),
        "type": "DocumentDeleted",
        "version": 1,
        "time": now,
        "doc_id": doc_id,
        "trace_id": uuid.uuid4().hex,
        "source": "gateway",
        "data": {"reason": "user_request", "requested_by": key_id},
    }
    validate(ev)
    produce(producer, s.topic_documents, ev)
    producer.flush()
    return True


STAGES = ("uploaded", "indexed", "summarized")


def catalog_html(rows: list[dict[str, Any]]) -> str:
    def stage_cells(status: str) -> str:
        reached = STAGES.index(status) if status in STAGES else -1
        return "".join(
            f'<td class="{"on" if i <= reached else "off"}">'
            f"{'✓ ' if i <= reached else '· '}{st}</td>"
            for i, st in enumerate(STAGES)
        )

    body = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(r.get('doc_id', ''))[:12])}…</code></td>"
        f"<td>{html.escape(str(r.get('key', '')))}</td>"
        f"{stage_cells(str(r.get('status', '')))}"
        f"<td>{html.escape(str(r.get('summary', '')))}</td>"
        f"<td>{html.escape(', '.join(r.get('tags', []) or []))}</td>"
        "</tr>"
        for r in sorted(rows, key=lambda r: str(r.get("updated_at", "")), reverse=True)
    )
    return f"""<!doctype html><meta charset="utf-8"><title>SteakLLM catalog</title>
<style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:.4rem .6rem;text-align:left;vertical-align:top}}
.on{{color:#0a7}}.off{{color:#aaa}}code{{font-size:12px}}</style>
<h1>SteakLLM catalog</h1>
<p>{len(rows)} document(s). Each one travels uploaded → indexed → summarized.</p>
<table><tr><th>doc</th><th>key</th><th>uploaded</th><th>indexed</th><th>summarized</th>
<th>summary</th><th>tags</th></tr>
{body}</table>"""
