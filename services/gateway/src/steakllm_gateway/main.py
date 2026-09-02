"""`steakllm-gateway`: build the real dependencies and serve with uvicorn."""

from __future__ import annotations

import sys
from functools import partial

import uvicorn
from steakllm_common.clients import (
    bedrock_client,
    catalog_table,
    embed,
    qdrant_client,
    s3_client,
)
from steakllm_common.kafka import make_producer
from steakllm_common.logging import configure, get_logger
from steakllm_common.settings import get_settings

from .app import Deps, create_app
from .backends import BedrockBackend, VllmBackend
from .rag import Retriever
from .router import CircuitBreaker, Router

log = get_logger(__name__)


def build_deps() -> Deps:
    s = get_settings()
    router = Router(
        vllm=VllmBackend(s.vllm_url, probe_timeout=s.vllm_probe_timeout_seconds),
        bedrock=BedrockBackend(bedrock_client(s), s.bedrock_model_id),
        breaker=CircuitBreaker(s.breaker_failures, s.breaker_open_seconds),
        probe_cache_seconds=s.vllm_probe_cache_seconds,
    )
    producer = make_producer(s)
    # ready = the broker answers a metadata request for the chats topic (bootstrap_connected() stays
    # False until the first send, so it is not the question we mean to ask)
    return Deps(
        settings=s,
        router=router,
        producer=producer,
        s3=s3_client(s),
        s3_public=s3_client(s, public=True),
        table=catalog_table(s),
        retriever=Retriever(qdrant_client(s), partial(embed, s), top_k=s.rag_top_k),
        ready=lambda: bool(producer.partitions_for(s.topic_chats)),
    )


def app():
    """uvicorn factory: `uvicorn steakllm_gateway.main:app --factory`."""
    configure("gateway")
    return create_app(build_deps())


def cli(argv: list[str] | None = None) -> int:
    configure("gateway")
    s = get_settings()
    log.info("starting", port=s.gateway_port, vllm=s.vllm_url, bedrock=s.bedrock_model_id)
    uvicorn.run(
        "steakllm_gateway.main:app",
        factory=True,
        host="0.0.0.0",
        port=s.gateway_port,
        log_level="warning",  # our JSON logs, not uvicorn's access log
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
