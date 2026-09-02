"""`steakllm-embedder`: the consumer loop on `documents` + `documents.retry`; probes on 8080."""

from __future__ import annotations

import sys
from functools import partial

from steakllm_common.clients import catalog_table, embed, qdrant_client, s3_client
from steakllm_common.health import start_probe_server
from steakllm_common.kafka import ConsumerLoop, RetryPolicy, make_consumer, make_producer
from steakllm_common.logging import configure, get_logger
from steakllm_common.settings import get_settings

from .handler import Deps, ensure_collection, handle

log = get_logger(__name__)
GROUP = "steakllm-embedder"


def build_deps() -> Deps:
    s = get_settings()
    return Deps(
        settings=s,
        s3=s3_client(s),
        table=catalog_table(s),
        qdrant=qdrant_client(s),
        producer=make_producer(s),
        embed=partial(embed, s),
    )


def cli(argv: list[str] | None = None) -> int:
    configure("embedder")
    deps = build_deps()
    s = deps.settings
    ensure_collection(deps)
    consumer = make_consumer(s, GROUP, [s.topic_documents, s.topic_documents_retry])
    loop = ConsumerLoop(
        consumer=consumer,
        producer=deps.producer,
        handler=lambda ev, h: handle(ev, h, deps),
        retry_topic=s.topic_documents_retry,
        dlq_topic=s.topic_documents_dlq,
        policy=RetryPolicy.from_settings(s),
    )

    def ready() -> bool:
        return deps.qdrant.collection_exists(s.qdrant_collection) and bool(consumer.topics())

    start_probe_server(s.probe_port, ready)
    log.info("starting", group=GROUP, topics=[s.topic_documents, s.topic_documents_retry])
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
