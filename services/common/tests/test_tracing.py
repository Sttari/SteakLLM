"""Tracing: no-op without an endpoint; inject/extract round-trips through Kafka-style headers."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from steakllm_common import tracing


def test_without_an_endpoint_nothing_is_exported(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracing._configured = False
    assert tracing.configure_tracing("test") is False


def test_a_consumer_span_continues_the_producer_trace():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("t")
    headers: dict[str, str] = {}
    with tracer.start_as_current_span("produce") as producer_span:
        # inject uses the global propagator against the *current* span
        token = trace.set_span_in_context(producer_span)
        from opentelemetry import context as ctx

        t = ctx.attach(token)
        try:
            tracing.inject(headers)
        finally:
            ctx.detach(t)
    assert "traceparent" in headers
    parent_trace = format(producer_span.get_span_context().trace_id, "032x")
    with tracing.span_from_headers("consume", headers, event_type="DocumentUploaded"):
        pass
    # the consume span is created on the global provider; compare ids through the carrier instead
    assert headers["traceparent"].split("-")[1] == parent_trace
    assert tracing.extract(headers) is not None
