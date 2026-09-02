"""The FastAPI app: OpenAI-compatible /v1, auth by Bearer key, ChatCompleted on every completion."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from steakllm_common.kafka import produce
from steakllm_common.logging import bound, get_logger
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from .backends import ChatRequest
from .router import Router

log = get_logger(__name__)

MODELS = ("llm", "docs")


@dataclass
class Deps:
    settings: Settings
    router: Router
    producer: Any
    ready: Callable[[], bool] = lambda: True
    now: Callable[[], str] = lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChatBody(BaseModel):
    model: str
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    user: str | None = None  # OpenAI's opaque end-user id; we use it as the session id


def key_id(key: str) -> str:
    """16 hex chars derived from the key; what events and logs carry, never the key itself."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def create_app(deps: Deps) -> FastAPI:
    s = deps.settings
    accepted = {s.gateway_api_key, *s.gateway_api_keys}
    app = FastAPI(title="SteakLLM gateway", version="0.1.0", docs_url="/docs")

    def auth(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or header[7:].strip() not in accepted:
            raise HTTPException(
                401, {"error": {"message": "invalid API key", "type": "auth_error"}}
            )
        return key_id(header[7:].strip())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        try:
            ok = bool(deps.ready())
        except Exception:  # noqa: BLE001 — a readiness check that throws is "not ready"
            ok = False
        return JSONResponse(
            {"status": "ready" if ok else "not ready"}, status_code=200 if ok else 503
        )

    @app.get("/v1/models")
    def models(_: str = Depends(auth)) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": m, "object": "model", "owned_by": "steakllm"} for m in MODELS],
        }

    @app.post("/v1/chat/completions")
    def chat(body: ChatBody, request: Request, kid: str = Depends(auth)):
        if body.model not in MODELS:
            raise HTTPException(404, {"error": {"message": f"unknown model {body.model!r}"}})
        if body.model == "docs":
            raise HTTPException(501, {"error": {"message": "the docs model arrives in 6.8"}})
        session = body.user or request.headers.get("x-session-id") or f"s_{uuid.uuid4().hex[:8]}"
        req = ChatRequest(
            model=body.model,
            messages=body.messages,
            stream=body.stream,
            max_tokens=min(body.max_tokens or 512, s.chat_max_tokens_cap),
            temperature=0.2 if body.temperature is None else body.temperature,
        )
        trace = uuid.uuid4().hex
        t0 = time.monotonic()
        with bound(trace_id=trace, api_key_id=kid, session_id=session):
            backend, result = deps.router.complete(req)

            def finish() -> None:
                usage = result.usage or {}
                latency_ms = int((time.monotonic() - t0) * 1000)
                ev = {
                    "id": str(uuid.uuid4()),
                    "type": "ChatCompleted",
                    "version": 1,
                    "time": deps.now(),
                    "doc_id": None,
                    "trace_id": trace,
                    "source": "gateway",
                    "data": {
                        "session_id": session,
                        "model": body.model,
                        "backend": backend,
                        "tokens_in": int(usage.get("prompt_tokens", 0)),
                        "tokens_out": int(usage.get("completion_tokens", 0)),
                        "latency_ms": latency_ms,
                        "api_key_id": kid,
                        "retrieved_doc_ids": [],
                    },
                }
                validate(ev)
                produce(deps.producer, s.topic_chats, ev)
                log.info(
                    "chat completed",
                    backend=backend,
                    model=body.model,
                    tokens_in=ev["data"]["tokens_in"],
                    tokens_out=ev["data"]["tokens_out"],
                    latency_ms=latency_ms,
                    stream=body.stream,
                )

            headers = {"x-backend": backend, "x-trace-id": trace}
            if not body.stream:
                finish()
                usage = result.usage or {}
                headers["x-tokens-in"] = str(usage.get("prompt_tokens", 0))
                headers["x-tokens-out"] = str(usage.get("completion_tokens", 0))
                return JSONResponse(result.body, headers=headers)

            def stream_then_finish() -> Iterator[bytes]:
                try:
                    yield from result.events or iter(())
                finally:
                    finish()  # usage is known only once the stream has ended

            return StreamingResponse(
                stream_then_finish(), media_type="text/event-stream", headers=headers
            )

    return app
