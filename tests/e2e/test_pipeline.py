# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=8", "httpx>=0.27"]
# ///
"""The step's promise, executable: drop a file → searchable and summarized within 60 s, no human step.

Public API only: presigned upload, PUT, poll GET /v1/documents/{doc_id} (doc_id = sha256 of the
bytes, computed here), ask the docs model, delete. Runs against `make up` (all five services in
containers) locally and in CI. Run: `make e2e` or `uv run --with pytest --with httpx tests/e2e/test_pipeline.py`.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid

import httpx
import pytest

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000/v1").rstrip("/")
KEY = os.environ.get("GATEWAY_API_KEY", "change-me")
BUDGET_SECONDS = float(os.environ.get("E2E_BUDGET_SECONDS", "60"))
AUTH = {"Authorization": f"Bearer {KEY}"}


def test_file_becomes_searchable_and_summarized_within_the_budget():
    marker = uuid.uuid4().hex[:8]
    body = (
        f"# Ferrous Foods memo {marker}\n\nThe Rotterdam hub opened in July and now handles all "
        "EMEA cold-chain logistics. The Leeds depot closed in June. Headcount is 2,140. "
        "Guidance for the year is unchanged: revenue growth of 10 to 12 percent."
    ).encode()
    doc_id = hashlib.sha256(body).hexdigest()
    t0 = time.monotonic()

    with httpx.Client(timeout=30) as c:
        # 1. ask for a presigned URL, then PUT the bytes straight into quarantine/
        r = c.post(
            f"{GATEWAY}/uploads",
            headers=AUTH,
            json={
                "filename": f"memo-{marker}.md",
                "content_type": "text/markdown",
                "size_bytes": len(body),
            },
        )
        assert r.status_code == 201, r.text
        up = r.json()
        put = c.put(up["url"], content=body, headers=up["headers"])
        assert put.status_code == 200, put.text

        # 2. the doorbell rings (ingest watcher), the librarian indexes, the summarizer summarizes:
        #    poll the document's status until it says so
        status, seen = None, []
        while time.monotonic() - t0 < BUDGET_SECONDS:
            r = c.get(f"{GATEWAY}/documents/{doc_id}", headers=AUTH)
            if r.status_code == 200:
                d = r.json()
                status = ",".join(
                    st for st in ("uploaded", "indexed", "summarized") if d.get(st)
                )
                if status != (seen[-1] if seen else None):
                    seen.append(status)
                    print(f"  t+{time.monotonic() - t0:5.1f}s  {status}")
                if d.get("indexed") and d.get("summarized"):
                    break
            time.sleep(1)
        assert "summarized" in status and "indexed" in status, (
            f"stuck at {status!r}; saw {seen}"
        )
        doc = r.json()
        assert doc["chunk_count"] and doc["summary"] and doc["tags"]
        print(f"  summary: {doc['summary'][:100]}…  tags: {doc['tags']}")

        # 3. searchable: the docs model retrieves our document and answers from it
        r = c.post(
            f"{GATEWAY}/chat/completions",
            headers=AUTH,
            json={
                "model": "docs",
                "messages": [
                    {
                        "role": "user",
                        "content": f"According to memo {marker}, where is the hub?",
                    }
                ],
                "max_tokens": 80,
            },
        )
        assert r.status_code == 200, r.text
        assert doc_id in r.headers.get("x-retrieved-doc-ids", "").split(",")
        answer = r.json()["choices"][0]["message"]["content"]
        assert "rotterdam" in answer.lower(), answer
        elapsed = time.monotonic() - t0
        print(
            f"  upload → summarized → answered in {elapsed:.1f}s (backend {r.headers['x-backend']})"
        )
        assert elapsed < BUDGET_SECONDS

        # 4. delete everywhere; the status route forgets the document
        assert (
            c.delete(f"{GATEWAY}/documents/{doc_id}", headers=AUTH).status_code == 204
        )
        assert c.get(f"{GATEWAY}/documents/{doc_id}", headers=AUTH).status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main(["-q", "-s", __file__]))
