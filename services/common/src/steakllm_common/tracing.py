"""Traces (ADR-0013): one OpenTelemetry SDK for every service and the Lambda.

`configure_tracing(service)` installs a tracer provider that exports over OTLP/HTTP when
OTEL_EXPORTER_OTLP_ENDPOINT is set (Tempo, `http://tempo.logging.svc:4318`), and a no-op provider
otherwise, so tests and the local stack run unchanged. The trace context travels in Kafka headers
(`traceparent`, W3C): `inject(headers)` on the producing side, `extract(headers)` on the consuming
side; the consumer loop opens a span per event with the extracted parent.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import inject as _inject
from opentelemetry.propagators.textmap import Getter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_PROPAGATOR = TraceContextTextMapPropagator()
_configured = False


def configure_tracing(service: str) -> bool:
    """Install the provider once. Returns True when spans are exported somewhere."""
    global _configured
    if _configured:
        return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
    _configured = True
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    return True


def tracer(name: str = "steakllm"):
    return trace.get_tracer(name)


def inject(headers: dict[str, str]) -> dict[str, str]:
    """Add the current span's `traceparent` (and `tracestate`) to a header dict; returns it."""
    _inject(headers)
    return headers


class _DictGetter(Getter[dict[str, str]]):
    def get(self, carrier: dict[str, str], key: str) -> list[str] | None:
        v = carrier.get(key)
        return [v] if v is not None else None

    def keys(self, carrier: dict[str, str]) -> list[str]:
        return list(carrier.keys())


def extract(headers: dict[str, str] | None) -> otel_context.Context:
    return _PROPAGATOR.extract(carrier=headers or {}, getter=_DictGetter())


@contextmanager
def span_from_headers(name: str, headers: dict[str, str] | None, **attrs: Any) -> Iterator[Any]:
    """A span whose parent is the trace carried in `headers` (a consumed Kafka record)."""
    ctx = extract(headers)
    with tracer().start_as_current_span(name, context=ctx) as span:
        for k, v in attrs.items():
            if v is not None:
                span.set_attribute(k, v)
        yield span


def current_trace_id() -> str | None:
    """The active trace id as 32 hex chars, for log lines and the `x-trace-id` header."""
    sc = trace.get_current_span().get_span_context()
    return format(sc.trace_id, "032x") if sc.is_valid else None
