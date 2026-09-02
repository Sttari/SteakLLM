"""Entry points: the Lambda handler, and the local runner (`steakllm-ingest upload|delete|watch`).

The runner feeds the handler synthetic S3 records, so the code that runs on the laptop is the code
that runs in Lambda; only the way the record arrives differs.
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steakllm_common.clients import catalog_table, s3_client
from steakllm_common.health import start_probe_server
from steakllm_common.kafka import make_producer
from steakllm_common.logging import configure, get_logger
from steakllm_common.settings import get_settings

from .handler import Deps, handle

log = get_logger(__name__)


def build_deps() -> Deps:
    s = get_settings()
    return Deps(settings=s, s3=s3_client(s), table=catalog_table(s), producer=make_producer(s))


def s3_record(bucket: str, key: str, created: bool = True) -> dict[str, Any]:
    """The shape S3 sends (and EventBridge forwards); the runner fabricates it."""
    return {
        "Records": [
            {
                "eventName": "ObjectCreated:Put" if created else "ObjectRemoved:Delete",
                "s3": {"bucket": {"name": bucket}, "object": {"key": key}},
            }
        ]
    }


# ---- Lambda -----------------------------------------------------------------------------------

_deps: Deps | None = None


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    global _deps
    configure("ingest")
    if _deps is None:  # reused across warm invocations
        _deps = build_deps()
    produced = handle(event, _deps)
    return {"produced": [e["type"] for e in produced]}


# ---- local runner -----------------------------------------------------------------------------


def cli(argv: list[str] | None = None) -> int:
    configure("ingest")
    ap = argparse.ArgumentParser(prog="steakllm-ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upload", help="put a file into quarantine/ and ring the doorbell")
    up.add_argument("file", type=Path)
    up.add_argument("--content-type", help="override the guessed MIME type")
    rm = sub.add_parser("delete", help="delete an object from the bucket and ring the doorbell")
    rm.add_argument("key")
    w = sub.add_parser("watch", help="poll quarantine/ and ring the doorbell for new objects")
    w.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args(argv)

    deps = build_deps()
    s = deps.settings
    if args.cmd == "upload":
        ctype = (
            args.content_type
            or mimetypes.guess_type(args.file.name)[0]
            or "application/octet-stream"
        )
        key = f"{s.quarantine_prefix}{datetime.now(UTC):%Y/%m/%d}/{args.file.name}"
        deps.s3.put_object(
            Bucket=s.documents_bucket, Key=key, Body=args.file.read_bytes(), ContentType=ctype
        )
        produced = handle(s3_record(s.documents_bucket, key), deps)
        for ev in produced:
            print(f"{ev['type']}  doc_id={ev['doc_id']}  key={key}")
        return 0
    if args.cmd == "delete":
        deps.s3.delete_object(Bucket=s.documents_bucket, Key=args.key)
        produced = handle(s3_record(s.documents_bucket, args.key, created=False), deps)
        for ev in produced:
            print(f"{ev['type']}  doc_id={ev['doc_id']}  key={args.key}")
        return 0
    if args.cmd == "watch":
        return _watch(deps, args.interval)
    return 2


def _watch(deps: Deps, interval: float) -> int:
    """Dev-only stand-in for S3 → EventBridge: poll the prefix, ring for keys the catalog lacks."""
    s = deps.settings
    seen: set[str] = set()
    start_probe_server(
        s.probe_port,
        lambda: "Contents" in deps.s3.list_objects_v2(Bucket=s.documents_bucket, MaxKeys=1) or True,
    )
    log.info("watching", bucket=s.documents_bucket, prefix=s.quarantine_prefix, interval=interval)
    try:
        while True:
            resp = deps.s3.list_objects_v2(Bucket=s.documents_bucket, Prefix=s.quarantine_prefix)
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if key in seen:
                    continue
                seen.add(key)
                handle(s3_record(s.documents_bucket, key), deps)
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(cli())
