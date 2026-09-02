"""`steakllm-summarizer`: the consumer loop on `documents` + `documents.retry`; probes on 8080."""

from __future__ import annotations

import sys

import httpx
from steakllm_common.clients import catalog_table, s3_client
from steakllm_common.health import start_probe_server
from steakllm_common.kafka import ConsumerLoop, RetryPolicy, make_consumer, make_producer
from steakllm_common.logging import configure, get_logger
from steakllm_common.settings import get_settings

from .gateway import GatewayChat
from .handler import Deps, handle

log = get_logger(__name__)
GROUP = "steakllm-summarizer"


def build_deps() -> Deps:
    s = get_settings()
    chat = GatewayChat(
        s.gateway_url,
        s.gateway_api_key,  # gitleaks:allow — a settings field, not a literal
        prefer_vllm_seconds=s.summarizer_prefer_vllm_seconds,
    )
    return Deps(
        settings=s,
        s3=s3_client(s),
        table=catalog_table(s),
        producer=make_producer(s),
        chat=chat.complete,
    )


def cli(argv: list[str] | None = None) -> int:
    configure("summarizer")
    deps = build_deps()
    s = deps.settings
    consumer = make_consumer(s, GROUP, [s.topic_documents, s.topic_documents_retry])
    loop = ConsumerLoop(
        consumer=consumer,
        producer=deps.producer,
        handler=lambda ev, h: handle(ev, h, deps),
        retry_topic=s.topic_documents_retry,
        dlq_topic=s.topic_documents_dlq,
        policy=RetryPolicy.from_settings(s),
    )
    health_url = s.gateway_url.rsplit("/v1", 1)[0] + "/healthz"

    def ready() -> bool:
        return bool(consumer.topics()) and httpx.get(health_url, timeout=2).status_code == 200

    start_probe_server(s.probe_port, ready)
    log.info("starting", group=GROUP, gateway=s.gateway_url)
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
