# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "boto3>=1.35",
#   "kafka-python>=2.2",
#   "qdrant-client>=1.12",
#   "pypdf>=5",
#   "httpx>=0.27",
#   "python-dotenv>=1.0",
#   "steakllm-contracts",
# ]
# [tool.uv.sources]
# steakllm-contracts = { path = "../services/contracts" }
# ///
"""The pipeline, by hand — the dress rehearsal for Step 6 (`make demo`).

One script plays every worker in turn, making the same calls the real services will make against the
local stack: upload to MinIO → DocumentUploaded on Kafka → read it back → chunk → embed (Ollama) →
upsert into Qdrant → catalog row → search → summary + tags from Bedrock → SummaryReady → catalog row.
Run it twice: the second run must leave the same point count and one catalog row (the idempotency rules).
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3
import httpx
from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaProducer
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from steakllm_contracts.ids import doc_id as make_doc_id
from steakllm_contracts.ids import point_id
from steakllm_contracts.validate import validate

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
env = os.environ

SAMPLE = ROOT / "compose" / "sample" / "quarterly-report.pdf"
QUESTION = "What drove revenue growth this quarter?"
CHUNK, OVERLAP = 400, 80


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(type_: str, source: str, doc: str | None, trace: str, data: dict) -> dict:
    ev = {
        "id": str(uuid.uuid4()),
        "type": type_,
        "version": 1,
        "time": now(),
        "doc_id": doc,
        "trace_id": trace,
        "source": source,
        "data": data,
    }
    validate(ev)  # raises with every problem listed; a bad event never reaches the log
    return ev


def step(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")


def chunks(text: str) -> list[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i : i + CHUNK].strip())
        i += CHUNK - OVERLAP
    return [c for c in out if c]


def main() -> None:
    trace = uuid.uuid4().hex
    s3 = boto3.client(
        "s3",
        endpoint_url=env["S3_ENDPOINT_URL"],
        aws_access_key_id=env["MINIO_ROOT_USER"],
        aws_secret_access_key=env["MINIO_ROOT_PASSWORD"],
        region_name=env["AWS_REGION"],
    )
    ddb = boto3.resource(
        "dynamodb",
        endpoint_url=env["DYNAMODB_ENDPOINT_URL"],
        aws_access_key_id="local",
        aws_secret_access_key="local",
        region_name=env["AWS_REGION"],
    ).Table(env["CATALOG_TABLE"])
    producer = KafkaProducer(
        bootstrap_servers=env["KAFKA_BOOTSTRAP"],
        value_serializer=lambda v: json.dumps(v).encode(),
        key_serializer=lambda k: k.encode(),
    )
    qdrant = QdrantClient(url=env["QDRANT_URL"])
    bucket, topic, collection = (
        env["DOCUMENTS_BUCKET"],
        env["TOPIC_DOCUMENTS"],
        env["QDRANT_COLLECTION"],
    )

    # -- 1. ingest: upload, identify, announce -----------------------------------------------
    step(1, "ingest: upload the PDF to MinIO, hash it, write DocumentUploaded")
    data = SAMPLE.read_bytes()
    doc = make_doc_id(data)
    key = f"{env['QUARANTINE_PREFIX']}{datetime.now(UTC):%Y/%m/%d}/{SAMPLE.name}"
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/pdf")
    uploaded = envelope(
        "DocumentUploaded",
        "ingest",
        doc,
        trace,
        {
            "bucket": bucket,
            "key": key,
            "size_bytes": len(data),
            "content_type": "application/pdf",
            "sha256": doc,
        },
    )
    producer.send(topic, key=doc, value=uploaded).get(timeout=10)
    producer.flush()
    print(f"    doc_id  {doc}")
    print(f"    s3://{bucket}/{key}  ({len(data)} bytes)")
    print(f"    event   {uploaded['id']} -> {topic}")

    # -- 2. embedder: read the event back, fetch the bytes, chunk, embed, upsert ---------------
    step(2, "embedder: consume DocumentUploaded from Kafka")
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=env["KAFKA_BOOTSTRAP"],
        group_id=f"demo-{trace[:8]}",
        auto_offset_reset="earliest",
        consumer_timeout_ms=15000,
        value_deserializer=lambda b: json.loads(b),
    )
    got = next((m.value for m in consumer if m.value.get("id") == uploaded["id"]), None)
    consumer.close()
    if not got:
        sys.exit("did not see our own event on the topic")
    validate(got)
    print(f"    read back {got['type']} for doc {got['doc_id'][:12]}… (validated)")

    step(
        2,
        "embedder: fetch from MinIO, extract text, chunk, embed with Ollama, upsert into Qdrant",
    )
    body = s3.get_object(Bucket=got["data"]["bucket"], Key=got["data"]["key"])[
        "Body"
    ].read()
    assert make_doc_id(body) == got["data"]["sha256"], (
        "bytes do not match the announced sha256"
    )
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages)
    pieces = chunks(text)
    dim = int(env["EMBEDDING_DIM"])
    r = httpx.post(
        f"{env['EMBEDDINGS_URL']}/embeddings",
        json={"model": env["EMBEDDING_MODEL"], "input": pieces},
        timeout=120,
    )
    r.raise_for_status()
    vectors = [d["embedding"] for d in r.json()["data"]]
    assert all(len(v) == dim for v in vectors), (
        "embedding size differs from EMBEDDING_DIM"
    )
    if not qdrant.collection_exists(collection):
        qdrant.create_collection(
            collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )
    qdrant.upsert(
        collection,
        points=[
            PointStruct(
                id=point_id(
                    doc, i
                ),  # same chunk -> same point: an upsert, never a duplicate
                vector=v,
                payload={
                    "doc_id": doc,
                    "chunk_index": i,
                    "text": pieces[i],
                    "key": key,
                },
            )
            for i, v in enumerate(vectors)
        ],
    )
    ddb.put_item(
        Item={
            "doc_id": doc,
            "status": "indexed",
            "key": key,
            "chunk_count": len(pieces),
            "trace_id": trace,
            "updated_at": now(),
        }
    )
    indexed = envelope(
        "DocumentIndexed",
        "embedder",
        doc,
        trace,
        {
            "collection": collection,
            "chunk_count": len(pieces),
            "embedding_model": env["EMBEDDING_MODEL"],
            "embedding_dim": dim,
        },
    )
    producer.send(topic, key=doc, value=indexed).get(timeout=10)
    print(
        f"    {len(text)} chars -> {len(pieces)} chunks -> {len(vectors)} vectors of {dim} -> upserted"
    )
    print(f"    catalog: {doc[:12]}… = indexed; event {indexed['id']} -> {topic}")

    # -- 3. gateway (docs model): search --------------------------------------------------------
    step(3, f"search: {QUESTION!r}")
    q = httpx.post(
        f"{env['EMBEDDINGS_URL']}/embeddings",
        json={"model": env["EMBEDDING_MODEL"], "input": QUESTION},
        timeout=60,
    ).json()["data"][0]["embedding"]
    hits = qdrant.query_points(collection, query=q, limit=3, with_payload=True).points
    best = hits[0]
    print(f"    best hit: score {best.score:.3f}, chunk {best.payload['chunk_index']}:")
    print("    | " + best.payload["text"][:240].replace("\n", " ") + " …")

    # -- 4. summarizer: Bedrock ------------------------------------------------------------------
    step(
        4, f"summarizer: ask Bedrock ({env['BEDROCK_MODEL_ID']}) for a summary and tags"
    )
    bedrock = boto3.Session(
        profile_name=env.get("AWS_PROFILE") or None, region_name=env["AWS_REGION"]
    ).client("bedrock-runtime")
    prompt = (
        "You are a careful analyst. Summarize the document in three sentences, then give three short "
        'lowercase topic tags. Answer with JSON only: {"summary": "...", "tags": ["a","b","c"]}\n\n'
        f"DOCUMENT:\n{text[:6000]}"
    )
    t0 = time.time()
    resp = bedrock.converse(
        modelId=env["BEDROCK_MODEL_ID"],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.2},
    )
    raw = resp["output"]["message"]["content"][0]["text"].strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(raw)
    usage = resp["usage"]
    ready = envelope(
        "SummaryReady",
        "summarizer",
        doc,
        trace,
        {
            "summary": parsed["summary"],
            "tags": [str(t) for t in parsed["tags"]][:32],
            "model": env["BEDROCK_MODEL_ID"],
            "backend": "bedrock",
            "tokens_in": usage["inputTokens"],
            "tokens_out": usage["outputTokens"],
        },
    )
    producer.send(topic, key=doc, value=ready).get(timeout=10)
    producer.flush()
    ddb.update_item(
        Key={"doc_id": doc},
        UpdateExpression="SET #s = :s, summary = :sum, tags = :t, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "summarized",
            ":sum": parsed["summary"],
            ":t": ready["data"]["tags"],
            ":u": now(),
        },
    )
    print(
        f"    {time.time() - t0:.1f}s, {usage['inputTokens']} in / {usage['outputTokens']} out tokens"
    )
    print(f"    summary: {parsed['summary']}")
    print(f"    tags:    {ready['data']['tags']}")
    print(f"    catalog: {doc[:12]}… = summarized; event {ready['id']} -> {topic}")

    # -- 5. the idempotency report ---------------------------------------------------------------
    step(5, "idempotency: what the stores hold after this run")
    mine = qdrant.count(
        collection,
        count_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc))]
        ),
        exact=True,
    ).count
    total = qdrant.count(collection, exact=True).count
    rows = ddb.scan(Select="COUNT")["Count"]
    row = ddb.get_item(Key={"doc_id": doc})["Item"]
    print(f"    qdrant points for this doc: {mine}  (collection total: {total})")
    print(
        f"    catalog rows: {rows}  (this doc: status={row['status']}, chunk_count={row['chunk_count']})"
    )
    print("    run it again: these numbers must not change.")


if __name__ == "__main__":
    main()
