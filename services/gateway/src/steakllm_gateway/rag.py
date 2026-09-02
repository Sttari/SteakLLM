"""The `docs` model: retrieve the closest chunks, cite them, answer through the same router."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SYSTEM = (
    "You answer questions using only the document excerpts provided. Cite the excerpts you use "
    "as [doc:chunk] exactly as labelled. If the excerpts do not contain the answer, say so plainly."
)


@dataclass(frozen=True)
class Hit:
    doc_id: str
    chunk_index: int
    text: str
    score: float
    key: str

    @property
    def label(self) -> str:
        return f"[{self.doc_id[:8]}:{self.chunk_index}]"


@dataclass
class Retriever:
    qdrant: Any
    embed: Callable[[list[str]], list[list[float]]]
    top_k: int = 5

    def search(self, question: str, collection: str) -> list[Hit]:
        if not self.qdrant.collection_exists(collection):
            return []
        vector = self.embed([question])[0]
        points = self.qdrant.query_points(
            collection, query=vector, limit=self.top_k, with_payload=True
        ).points
        return [
            Hit(
                doc_id=p.payload["doc_id"],
                chunk_index=int(p.payload["chunk_index"]),
                text=p.payload["text"],
                score=float(p.score),
                key=p.payload.get("key", ""),
            )
            for p in points
        ]


def build_messages(messages: list[dict[str, Any]], hits: list[Hit]) -> list[dict[str, Any]]:
    """Prepend the system rule and the labelled excerpts; keep the caller's conversation intact."""
    excerpts = "\n\n".join(f"{h.label} {h.text}" for h in hits) or "(no excerpts found)"
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "system", "content": f"EXCERPTS:\n{excerpts}"},
        *[m for m in messages if m.get("role") != "system"],
    ]


def last_user_question(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            return c if isinstance(c, str) else " ".join(p.get("text", "") for p in c)
    return ""
