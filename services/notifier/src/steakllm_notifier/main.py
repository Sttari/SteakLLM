"""`steakllm-notifier`: the consumer loop on `documents` + `documents.retry`; probes on 8080."""

from __future__ import annotations

import sys

import boto3
from steakllm_common.clients import catalog_table
from steakllm_common.health import start_probe_server
from steakllm_common.kafka import ConsumerLoop, RetryPolicy, make_consumer, make_producer
from steakllm_common.logging import configure, get_logger
from steakllm_common.settings import get_settings

from .handler import Deps, handle
from .sinks import Sink, SnsSink, StdoutSink

log = get_logger(__name__)
GROUP = "steakllm-notifier"


def build_sink() -> Sink:
    s = get_settings()
    if s.notify_sink == "sns":
        if not s.sns_topic_arn:
            raise SystemExit("NOTIFY_SINK=sns needs SNS_TOPIC_ARN")
        return SnsSink(boto3.client("sns", region_name=s.aws_region), s.sns_topic_arn)
    return StdoutSink()


def cli(argv: list[str] | None = None) -> int:
    configure("notifier")
    s = get_settings()
    deps = Deps(settings=s, table=catalog_table(s), sink=build_sink())
    consumer = make_consumer(s, GROUP, [s.topic_documents, s.topic_documents_retry])
    loop = ConsumerLoop(
        consumer=consumer,
        producer=make_producer(s),
        handler=lambda ev, h: handle(ev, h, deps),
        retry_topic=s.topic_documents_retry,
        dlq_topic=s.topic_documents_dlq,
        policy=RetryPolicy.from_settings(s),
    )
    start_probe_server(s.probe_port, lambda: bool(consumer.topics()))
    log.info("starting", group=GROUP, sink=s.notify_sink, watch_list=s.watch_list)
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
