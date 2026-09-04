# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""The load table (Step 9.8): N concurrent chats of a fixed prompt through the gateway, per concurrency
level, and one Markdown row per level: requests/s, completion tokens/s, p50 and p95 latency, the
x-backend split, and how many were refused by the quota (429) or failed.

Run over the tailnet with the key in the environment (never on the command line):
  GATEWAY_API_KEY=$(aws secretsmanager get-secret-value --secret-id steakllm/gateway --query SecretString --output text | python3 -c 'import sys,json; print(json.load(sys.stdin)["api_key"])') \
  uv run tests/load/chat_load.py --levels 1,8,32 --label vllm

The gateway's quota is 60 requests per minute per key (sliding window), so each level sends
8 × min(level, 4) requests (8, 32, 32) and the script waits --pause seconds between levels.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from collections import Counter

import httpx

PROMPT = "Explain in about 100 words why a cast-iron pan sears a steak better than a thin aluminium one."


async def one(client: httpx.AsyncClient, url: str, key: str, max_tokens: int) -> dict:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{url}/v1/chat/completions",
            headers={"authorization": f"Bearer {key}"},
            json={
                "model": "llm",
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
        )
        dt = time.perf_counter() - t0
        out = 0
        if r.status_code == 200:
            usage = r.json().get("usage") or {}
            out = int(
                usage.get("completion_tokens") or r.headers.get("x-tokens-out") or 0
            )
        return {
            "status": r.status_code,
            "backend": r.headers.get("x-backend", "-"),
            "latency": dt,
            "tokens_out": out,
        }
    except httpx.HTTPError as e:
        return {
            "status": 0,
            "backend": type(e).__name__,
            "latency": time.perf_counter() - t0,
            "tokens_out": 0,
        }


async def level(
    url: str, key: str, concurrency: int, requests: int, max_tokens: int
) -> dict:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=180) as client:

        async def guarded():
            async with sem:
                return await one(client, url, key, max_tokens)

        t0 = time.perf_counter()
        results = await asyncio.gather(*(guarded() for _ in range(requests)))
        wall = time.perf_counter() - t0
    ok = [r for r in results if r["status"] == 200]
    lat = sorted(r["latency"] for r in ok) or [0.0]
    p95 = lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))]
    return {
        "concurrency": concurrency,
        "requests": requests,
        "ok": len(ok),
        "quota_429": sum(1 for r in results if r["status"] == 429),
        "failed": sum(1 for r in results if r["status"] not in (200, 429)),
        "wall": wall,
        "rps": len(ok) / wall if wall else 0.0,
        "tps": sum(r["tokens_out"] for r in ok) / wall if wall else 0.0,
        "p50": statistics.median(lat),
        "p95": p95,
        "backends": Counter(r["backend"] for r in ok),
    }


def row(x: dict) -> str:
    split = ", ".join(f"{b} {n}" for b, n in sorted(x["backends"].items())) or "-"
    return (
        f"| {x['concurrency']} | {x['requests']} | {x['ok']} / {x['quota_429']} / {x['failed']} | {x['rps']:.2f} | {x['tps']:.0f} "
        f"| {x['p50']:.2f} s | {x['p95']:.2f} s | {split} |"
    )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url", default=os.environ.get("GATEWAY_URL", "http://gateway:8000")
    )
    ap.add_argument("--levels", default="1,8,32")
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument(
        "--pause",
        type=float,
        default=60.0,
        help="seconds between levels (the 60 rpm quota)",
    )
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    key = os.environ.get("GATEWAY_API_KEY")
    if not key:
        print("GATEWAY_API_KEY is not set", file=sys.stderr)
        return 2
    levels = [int(x) for x in a.levels.split(",")]
    print(
        f"### chat load{(' — ' + a.label) if a.label else ''} · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · max_tokens {a.max_tokens}\n"
    )
    print(
        "| concurrency | requests | ok / 429 / failed | req/s | tokens/s | p50 | p95 | x-backend |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(levels):
        if i:
            await asyncio.sleep(a.pause)
        x = await level(a.url.rstrip("/"), key, c, 8 * min(c, 4), a.max_tokens)
        print(row(x), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
