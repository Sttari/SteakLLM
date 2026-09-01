"""The idempotency rules, as code.

S3 and Kafka deliver at least once, and workers restart mid-batch. Instead of preventing duplicates
we make them harmless: every identity is derived from *content*, so doing a thing twice produces
the same ids and an upsert keyed on them changes nothing the second time.

  doc_id   = sha256(bytes)                 same file  -> same document, always
  point_id = uuid5(NAMESPACE, doc_id:i)    same chunk -> same vector-store point, always

These values are part of the v1 contract. Changing the hash or the namespace would re-key every
stored document and vector; tests/test_ids.py pins known answers so that cannot happen quietly.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import BinaryIO

__all__ = ["POINT_NAMESPACE", "doc_id", "doc_id_from_stream", "point_id"]

# Fixed for the life of the project. uuid5(NAMESPACE_URL, "steakllm://points"), frozen as a literal
# so the value can never drift with a library change.
POINT_NAMESPACE = uuid.UUID("f4e0d6a9-4c1d-5a7b-9e3f-2b8c1d0e5a67")

_DOC_ID = re.compile(r"^[0-9a-f]{64}$")


def doc_id(data: bytes) -> str:
    """sha256 of the bytes, lowercase hex. The document's identity everywhere: S3 key suffix,
    catalog key, envelope ``doc_id``, ``DocumentUploaded.data.sha256``."""
    return hashlib.sha256(data).hexdigest()


def doc_id_from_stream(stream: BinaryIO, chunk_size: int = 1 << 20) -> str:
    """Same as :func:`doc_id` without loading the whole file into memory (Lambda has 512 MB)."""
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(chunk_size), b""):
        h.update(block)
    return h.hexdigest()


def point_id(document_id: str, chunk_index: int) -> str:
    """Deterministic UUIDv5 for chunk ``chunk_index`` of document ``document_id``.

    Re-embedding the same chunk yields the same id, so the vector store upserts instead of
    duplicating; deleting a document means deleting ``point_id(doc, i)`` for i in range(n).
    """
    if not _DOC_ID.match(document_id):
        raise ValueError(
            f"document_id must be 64 lowercase hex chars (sha256), got {document_id!r}"
        )
    if chunk_index < 0:
        raise ValueError(f"chunk_index must be >= 0, got {chunk_index}")
    return str(uuid.uuid5(POINT_NAMESPACE, f"{document_id}:{chunk_index}"))
