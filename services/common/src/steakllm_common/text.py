"""Text extraction and chunking, shared by the embedder and the summarizer.

An embedding captures one idea well and a whole document badly, so documents are cut into
overlapping windows of characters. Chunking is deterministic: the same text always yields the same
chunks in the same order, which is what makes `point_id(doc_id, i)` stable across re-runs.
"""

from __future__ import annotations

import io


def extract_text(body: bytes, content_type: str) -> str:
    """Plain text from the supported types. Unknown types raise (the doorbell rejects them)."""
    ctype = content_type.split(";")[0].strip().lower()
    if ctype == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ctype in ("text/markdown", "text/plain"):
        return body.decode("utf-8", errors="replace")
    raise ValueError(f"unsupported content type: {content_type}")


def chunk(text: str, size: int = 400, overlap: int = 80) -> list[str]:
    """Overlapping character windows; whitespace-trimmed; empties dropped. Deterministic."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("need size > 0 and 0 <= overlap < size")
    text = text.strip()
    out: list[str] = []
    step = size - overlap
    for start in range(0, len(text), step):
        piece = text[start : start + size].strip()
        if piece:
            out.append(piece)
        if start + size >= len(text):
            break
    return out
