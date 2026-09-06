# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "boto3>=1.35"]
# ///
"""The nightly eval (Step 11.6): the same twenty fact questions to both chat backends through the
gateway, scored on facts, written to S3 and to CloudWatch metrics for the dashboard.

The fixture memo is uploaded once (presigned PUT), waited for (`summarized`), then each question is
asked with `model=docs` twice: `x-prefer-backend: bedrock`, and `x-prefer-backend: vllm` with
`x-prefer-vllm-seconds` (the gateway waits for the GPU that the first fallbacks summon). A question
scores 1 when every expected fact appears in the answer (case-insensitive substring). The GPU is
summoned by the run and removed by the idle chain; the reaper at 03:00 is the net.

Env: GATEWAY_URL (…/v1), GATEWAY_API_KEY (never printed), EVAL_BUCKET, EVAL_PREFIX (eval/),
EVAL_PREFER_VLLM_SECONDS (600), EVAL_BACKENDS (bedrock,vllm), AWS_REGION.
Run by hand: `uv run services/eval/eval.py --backends bedrock` (no GPU) or with both.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

import boto3
import httpx

HERE = Path(__file__).parent


def upload_fixture(client: httpx.Client, gw: str, key: str, body: bytes) -> str:
    doc_id = hashlib.sha256(body).hexdigest()
    up = client.post(
        f"{gw}/uploads",
        headers={"authorization": f"Bearer {key}"},
        json={
            "filename": "eval-memo.md",
            "content_type": "text/markdown",
            "size_bytes": len(body),
        },
    )
    up.raise_for_status()
    u = up.json()
    put = httpx.request(
        u.get("method", "PUT"),
        u["url"],
        content=body,
        headers=u.get("headers", {}),
        timeout=60,
    )
    put.raise_for_status()
    deadline = time.time() + 180
    while time.time() < deadline:
        r = client.get(
            f"{gw}/documents/{doc_id}", headers={"authorization": f"Bearer {key}"}
        )
        if r.status_code == 200 and r.json().get("summary"):
            return doc_id
        time.sleep(5)
    raise SystemExit("the fixture was not summarized within 180 s")


def ask(
    client: httpx.Client, gw: str, key: str, q: str, backend: str, wait: int
) -> dict:
    headers = {"authorization": f"Bearer {key}", "x-prefer-backend": backend}
    if backend == "vllm":
        headers["x-prefer-vllm-seconds"] = str(wait)
    t0 = time.perf_counter()
    r = client.post(
        f"{gw}/chat/completions",
        headers=headers,
        json={
            "model": "docs",
            "messages": [{"role": "user", "content": q}],
            "max_tokens": 80,
            "temperature": 0,
        },
        timeout=wait + 120,
    )
    dt_s = time.perf_counter() - t0
    r.raise_for_status()
    body = r.json()
    return {
        "answer": body["choices"][0]["message"]["content"],
        "backend": r.headers.get("x-backend", "?"),
        "latency_s": round(dt_s, 2),
        "tokens_out": int(
            r.headers.get("x-tokens-out")
            or body.get("usage", {}).get("completion_tokens", 0)
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--backends", default=os.environ.get("EVAL_BACKENDS", "bedrock,vllm")
    )
    ap.add_argument(
        "--wait",
        type=int,
        default=int(os.environ.get("EVAL_PREFER_VLLM_SECONDS", "600")),
    )
    ap.add_argument(
        "--no-upload", action="store_true", help="the fixture is already indexed"
    )
    a = ap.parse_args()
    gw = os.environ.get("GATEWAY_URL", "http://gateway:8000/v1").rstrip("/")
    key = os.environ["GATEWAY_API_KEY"]
    spec = json.loads((HERE / "questions.json").read_text())
    client = httpx.Client(timeout=120)
    if not a.no_upload:
        doc = upload_fixture(client, gw, key, spec["fixture"].encode())
        print(f"fixture {doc[:12]} summarized")
    results: dict[str, list[dict]] = {}
    for backend in a.backends.split(","):
        rows = []
        for item in spec["questions"]:
            r = ask(client, gw, key, item["q"], backend, a.wait)
            answer = r["answer"].lower()
            r["score"] = (
                1
                if all(
                    any(
                        f in answer for f in ([fact] if isinstance(fact, str) else fact)
                    )
                    for fact in item["facts"]
                )
                else 0
            )
            r["q"] = item["q"]
            rows.append(r)
            print(
                f"  [{backend}→{r['backend']}] {r['score']} {r['latency_s']:>5.1f}s  {item['q'][:50]}"
            )
        results[backend] = rows
    summary = {}
    for backend, rows in results.items():
        served = {r["backend"] for r in rows}
        summary[backend] = {
            "score": sum(r["score"] for r in rows) / len(rows),
            "p50_latency_s": statistics.median(r["latency_s"] for r in rows),
            "tokens_out": sum(r["tokens_out"] for r in rows),
            "answered_by": sorted(served),
        }
        print(
            f"{backend}: score {summary[backend]['score']:.2f} · p50 {summary[backend]['p50_latency_s']:.1f}s · answered by {sorted(served)}"
        )
    day = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    out = {"date": day, "summary": summary, "results": results}
    bucket = os.environ.get("EVAL_BUCKET")
    if bucket:
        region = os.environ.get("AWS_REGION", "us-east-1")
        s3 = boto3.client("s3", region_name=region)
        s3.put_object(
            Bucket=bucket,
            Key=f"{os.environ.get('EVAL_PREFIX', 'eval/')}{day}.json",
            Body=json.dumps(out, indent=1).encode(),
            ContentType="application/json",
        )
        cw = boto3.client("cloudwatch", region_name=region)
        cw.put_metric_data(
            Namespace="SteakLLM/Eval",
            MetricData=[
                {
                    "MetricName": m,
                    "Dimensions": [{"Name": "backend", "Value": b}],
                    "Value": v,
                }
                for b, sm in summary.items()
                for m, v in (
                    ("score", sm["score"]),
                    ("p50_latency_s", sm["p50_latency_s"]),
                )
            ],
        )
        print(f"written s3://{bucket}/eval/{day}.json and CloudWatch SteakLLM/Eval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
