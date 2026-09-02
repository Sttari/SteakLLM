# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "kafka-python>=2.2", "qdrant-client>=1.12", "python-dotenv>=1.0"]
# ///
"""Chaos drill 1 — kill the embedder mid-batch, restart it, expect no duplicates and no loss.

Prediction (written before the first run, docs/chaos/01-embedder-kill.md):
  1. every document reaches `indexed` after the restart;
  2. Qdrant holds exactly sum(chunk_count) points for them — re-delivery rewrites the same ids;
  3. the embedder group's committed offsets reach the end of `documents`;
  4. nothing lands on documents.retry or documents.dlq because of the kill.

Run against `make up` from the repo root:  uv run tests/chaos/drill_01_embedder_kill.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from kafka import KafkaConsumer, TopicPartition
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
env = os.environ
GATEWAY = env.get("GATEWAY_URL", "http://localhost:8000/v1").rstrip("/")
AUTH = {"Authorization": f"Bearer {env.get('GATEWAY_API_KEY', 'change-me')}"}
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "--profile",
    "services",
    "-f",
    "compose/compose.yaml",
]
N_DOCS = int(env.get("DRILL_DOCS", "10"))
SIGNAL = env.get(
    "DRILL_SIGNAL", "kill"
)  # kill = SIGKILL (the drill); stop = SIGTERM (the contrast)
GROUP = "steakllm-embedder"


def compose(*args: str) -> None:
    subprocess.run([*COMPOSE, *args], cwd=ROOT, check=True, capture_output=True)


def offsets_lag(bootstrap: str, topic: str) -> tuple[int, int]:
    """(committed by the embedder group, end of topic) summed over partitions."""
    c = KafkaConsumer(
        bootstrap_servers=bootstrap, group_id=GROUP, enable_auto_commit=False
    )
    parts = [TopicPartition(topic, p) for p in c.partitions_for_topic(topic) or []]
    ends = c.end_offsets(parts)
    have = sum((c.committed(tp) or 0) for tp in parts)
    c.close()
    return have, sum(ends.values())


def parked_total(bootstrap: str, topics: list[str]) -> int:
    n = 0
    for topic in topics:
        rc = KafkaConsumer(bootstrap_servers=bootstrap)
        parts = [TopicPartition(topic, p) for p in rc.partitions_for_topic(topic) or []]
        n += sum(rc.end_offsets(parts).values())
        rc.close()
    return n


def main() -> int:
    qdrant = QdrantClient(url=env["QDRANT_URL"])
    marker = uuid.uuid4().hex[:6]
    docs: dict[
        str, int
    ] = {}  # doc_id -> expected chunks (filled from the catalog later)
    t0 = time.monotonic()
    parked_before = parked_total(
        env["KAFKA_BOOTSTRAP"],
        [env["TOPIC_DOCUMENTS_RETRY"], env["TOPIC_DOCUMENTS_DLQ"]],
    )
    with httpx.Client(timeout=30) as c:
        # -- 1. upload N documents in a burst -------------------------------------------------
        for i in range(N_DOCS):
            body = (
                f"# Drill {marker} document {i}\n\n"
                + f"Paragraph {i} of the drill. " * 60
            ).encode()
            doc = hashlib.sha256(body).hexdigest()
            r = c.post(
                f"{GATEWAY}/uploads",
                headers=AUTH,
                json={
                    "filename": f"drill-{marker}-{i}.md",
                    "content_type": "text/markdown",
                    "size_bytes": len(body),
                },
            )
            r.raise_for_status()
            up = r.json()
            c.put(up["url"], content=body, headers=up["headers"]).raise_for_status()
            docs[doc] = 0
        print(f"[{time.monotonic() - t0:5.1f}s] uploaded {N_DOCS} documents")

        def indexed_count() -> int:
            n = 0
            for d in docs:
                r = c.get(f"{GATEWAY}/documents/{d}", headers=AUTH)
                if r.status_code == 200 and r.json().get("indexed"):
                    n += 1
            return n

        # -- 2. wait until the embedder is *in the middle* of the batch, then kill it ------------
        while indexed_count() == 0 and time.monotonic() - t0 < 60:
            time.sleep(0.2)
        mid = indexed_count()
        compose(
            SIGNAL, "embedder"
        )  # kill: SIGKILL, no commit; stop: SIGTERM, graceful leave
        killed_at = time.monotonic() - t0
        verb = {"kill": "KILLED (SIGKILL)", "stop": "STOPPED (SIGTERM)"}.get(
            SIGNAL, SIGNAL.upper()
        )
        print(f"[{killed_at:5.1f}s] {verb} the embedder with {mid}/{N_DOCS} indexed")
        time.sleep(2)
        compose("start", "embedder")
        print(f"[{time.monotonic() - t0:5.1f}s] started the embedder again")

        # -- 3. wait for every document to be indexed --------------------------------------------
        deadline = time.monotonic() + 120
        while indexed_count() < N_DOCS and time.monotonic() < deadline:
            time.sleep(1)
        done = indexed_count()
        print(f"[{time.monotonic() - t0:5.1f}s] indexed {done}/{N_DOCS}")
        for d in docs:
            docs[d] = int(
                c.get(f"{GATEWAY}/documents/{d}", headers=AUTH).json()["chunk_count"]
                or 0
            )

        # -- 4. the verdict ------------------------------------------------------------------------
        expected_points = sum(docs.values())
        actual_points = qdrant.count(
            env["QDRANT_COLLECTION"],
            count_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchAny(any=list(docs)))]
            ),
            exact=True,
        ).count
        have, end = offsets_lag(env["KAFKA_BOOTSTRAP"], env["TOPIC_DOCUMENTS"])
        parked = (
            parked_total(
                env["KAFKA_BOOTSTRAP"],
                [env["TOPIC_DOCUMENTS_RETRY"], env["TOPIC_DOCUMENTS_DLQ"]],
            )
            - parked_before
        )
        print("verdict:")
        print(
            f"  documents indexed        {done}/{N_DOCS}   {'OK' if done == N_DOCS else 'FAIL'}"
        )
        print(
            f"  qdrant points            {actual_points} (expected {expected_points})   {'OK' if actual_points == expected_points else 'FAIL'}"
        )
        print(
            f"  embedder group offsets   {have}/{end} committed   {'OK' if have == end else 'FAIL'}"
        )
        print(
            f"  retry+dlq events added   {parked}   {'OK' if parked == 0 else 'FAIL'}"
        )

        # -- 5. clean up: delete the drill's documents through the API ----------------------------
        for d in docs:
            c.delete(f"{GATEWAY}/documents/{d}", headers=AUTH)
        time.sleep(3)
        leftover = qdrant.count(
            env["QDRANT_COLLECTION"],
            count_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchAny(any=list(docs)))]
            ),
            exact=True,
        ).count
        print(f"  cleanup: points left for the drill's docs after delete: {leftover}")
    ok = (
        done == N_DOCS
        and actual_points == expected_points
        and have == end
        and parked == 0
    )
    print("DRILL PASSED" if ok else "DRILL FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
