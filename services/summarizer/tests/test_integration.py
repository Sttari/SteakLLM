"""On the real stack (make up): a fresh document → a `SummaryReady` on Kafka with backend=bedrock.

The gateway does not exist until 6.7, so this test runs a stub OpenAI-compatible server in a thread
that answers with canned JSON and `x-backend: bedrock`. It proves the wiring: fetch, extract, the
chat call, the catalog write, the event on the real topic. 6.7 re-runs it against the real gateway.
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from kafka import KafkaConsumer
from steakllm_common.clients import catalog_table, s3_client
from steakllm_common.kafka import make_producer
from steakllm_common.logging import configure
from steakllm_common.settings import Settings
from steakllm_contracts.ids import doc_id
from steakllm_contracts.validate import validate

from steakllm_summarizer.gateway import GatewayChat
from steakllm_summarizer.handler import Deps, handle

pytestmark = pytest.mark.integration


class StubGateway(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self):  # noqa: N802 — http.server's naming
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        StubGateway.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        reply = {
            "id": "stub",
            "model": "stub-model",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            '{"summary": "A stubbed summary of the document.", '
                            '"tags": ["stub", "test"]}'
                        ),
                    }
                }
            ],
            "usage": {
                "prompt_tokens": len(body["messages"][0]["content"]) // 4,
                "completion_tokens": 12,
            },
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("x-backend", "bedrock")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        return


def test_fresh_document_becomes_a_summary_ready_event_on_kafka():
    configure("summarizer-it")
    s = Settings()  # the repo's env file (run from the repo root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubGateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    chat = GatewayChat(f"http://127.0.0.1:{port}/v1", s.gateway_api_key)
    deps = Deps(
        settings=s,
        s3=s3_client(s),
        table=catalog_table(s),
        producer=make_producer(s),
        chat=chat.complete,
    )
    body = (f"# Integration {uuid.uuid4()}\n\n" + "quarterly results paragraph. " * 40).encode()
    doc = doc_id(body)
    key = f"{s.quarantine_prefix}it/{doc[:12]}.md"
    deps.s3.put_object(Bucket=s.documents_bucket, Key=key, Body=body, ContentType="text/markdown")
    ev = {
        "id": str(uuid.uuid4()),
        "type": "DocumentUploaded",
        "version": 1,
        "time": "2026-09-02T22:00:00Z",
        "doc_id": doc,
        "trace_id": uuid.uuid4().hex,
        "source": "ingest",
        "data": {
            "bucket": s.documents_bucket,
            "key": key,
            "size_bytes": len(body),
            "content_type": "text/markdown",
            "sha256": doc,
        },
    }
    validate(ev)
    try:
        handle(ev, {}, deps)
        deps.producer.flush()
        row = deps.table.get_item(Key={"doc_id": doc})["Item"]
        assert row["status"] == "summarized" and row["summary_backend"] == "bedrock"
        assert StubGateway.seen[-1]["path"] == "/v1/chat/completions"
        assert StubGateway.seen[-1]["auth"] == f"Bearer {s.gateway_api_key}"

        reader = KafkaConsumer(
            s.topic_documents,
            bootstrap_servers=s.kafka_bootstrap,
            auto_offset_reset="earliest",
            consumer_timeout_ms=30000,
            value_deserializer=lambda b: json.loads(b),
        )
        found = next(
            (
                m.value
                for m in reader
                if m.value.get("type") == "SummaryReady" and m.value.get("doc_id") == doc
            ),
            None,
        )
        assert found is not None, "no SummaryReady for our document within 30 s"
        validate(found)
        assert found["data"]["backend"] == "bedrock" and found["data"]["tags"] == ["stub", "test"]
        assert found["trace_id"] == ev["trace_id"]
    finally:
        server.shutdown()
        deps.table.delete_item(Key={"doc_id": doc})
        deps.s3.delete_object(Bucket=s.documents_bucket, Key=key)
