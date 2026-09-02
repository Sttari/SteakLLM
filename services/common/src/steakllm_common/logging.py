"""One JSON object per line on stdout, carrying the ids that let Loki follow a document anywhere.

configure("embedder")            # once, in main()
log = get_logger(__name__)
with bound(doc_id=..., trace_id=..., event_id=..., event_type=...):
    log.info("indexed", chunk_count=5)   # ->
    {"ts":…,"level":"info","service":"embedder","msg":"indexed",
                                         #     "doc_id":…,"trace_id":…,"event_id":…,"chunk_count":5}
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_context")
_service = "unknown"

_STD_KEYS = {"ts", "level", "service", "msg"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "level": record.levelname.lower(),
            "service": _service,
            "msg": record.getMessage(),
        }
        line.update(_context.get({}))
        extra = getattr(record, "fields", None)
        if extra:
            line.update({k: v for k, v in extra.items() if k not in _STD_KEYS})
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(line, default=str)


class Logger(logging.LoggerAdapter):
    """`log.info("msg", key=value, …)` — keyword fields become JSON keys."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        fields = {k: kwargs.pop(k) for k in list(kwargs) if k not in ("exc_info", "stack_info")}
        kwargs["extra"] = {"fields": fields}
        return msg, kwargs


def configure(service: str, level: str = "INFO") -> None:
    global _service
    _service = service
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("kafka", "botocore", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel("WARNING")


def get_logger(name: str) -> Logger:
    return Logger(logging.getLogger(name), {})


@contextmanager
def bound(**fields: Any) -> Iterator[None]:
    """Attach fields to every log line emitted inside the block (nests; restores on exit)."""
    token = _context.set({**_context.get({}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def event_fields(event: dict[str, Any]) -> dict[str, Any]:
    """The four envelope ids every line should carry while handling an event."""
    return {
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "doc_id": event.get("doc_id"),
        "trace_id": event.get("trace_id"),
    }
