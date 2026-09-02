"""The FastAPI app: OpenAI-compatible /v1 (llm + docs), quotas, uploads, deletes, the catalog page.

Every completion emits ChatCompleted; every response carries x-backend and token headers; keys are
never logged or emitted — only their 16-hex id.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from steakllm_common.kafka import produce
from steakllm_common.logging import bound, get_logger
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from .backends import ChatRequest
from .documents import catalog_html, delete_document, presign_upload
from .quotas import KeyPolicy, QuotaLedger
from .rag import Retriever, build_messages, last_user_question
from .router import Router

log = get_logger(__name__)

MODELS = ("llm", "docs")


def key_id(key: str) -> str:
    """16 hex chars derived from the key; what events and logs carry, never the key itself."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def policies_from_settings(s: Settings) -> dict[str, KeyPolicy]:
    """key id → policy. The demo key, if set, gets the tight quota and the demo collection."""
    default = KeyPolicy("default", s.qdrant_collection, s.gateway_rpm, s.gateway_tokens_per_day)
    out = {key_id(k): default for k in (s.gateway_api_key, *s.gateway_api_keys)}
    if s.gateway_demo_key:
        out[key_id(s.gateway_demo_key)] = KeyPolicy(
            "demo", s.qdrant_demo_collection, s.gateway_demo_rpm, s.gateway_demo_tokens_per_day
        )
    return out


@dataclass
class Deps:
    settings: Settings
    router: Router
    producer: Any
    s3: Any = None
    table: Any = None
    retriever: Retriever | None = None
    ledger: QuotaLedger = field(default_factory=QuotaLedger)
    policies: dict[str, KeyPolicy] | None = None
    ready: Callable[[], bool] = lambda: True
    now: Callable[[], str] = lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChatBody(BaseModel):
    model: str = Field(description="`llm` for plain chat, `docs` for chat over your documents")
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    user: str | None = Field(default=None, description="opaque session id (OpenAI's `user`)")


class UploadBody(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(examples=["application/pdf"])
    size_bytes: int = Field(gt=0)


def create_app(deps: Deps) -> FastAPI:
    s = deps.settings
    policies = deps.policies if deps.policies is not None else policies_from_settings(s)
    app = FastAPI(
        title="SteakLLM gateway",
        version="0.1.0",
        docs_url="/docs",
        description=(
            "The one public door. OpenAI-compatible chat (`llm`) and chat over your documents "
            "(`docs`), presigned uploads, deletes, and the catalog. Every response carries "
            "`x-backend` (vllm|bedrock) and token counts."
        ),
    )

    def auth(request: Request) -> str:
        header = request.headers.get("authorization", "")
        bearer = header.startswith("Bearer ")
        key = header[7:].strip() if bearer else request.query_params.get("key")
        kid = key_id(key) if key else ""
        if kid not in policies:
            raise HTTPException(
                401, {"error": {"message": "invalid API key", "type": "auth_error"}}
            )
        return kid

    def check_quota(kid: str) -> KeyPolicy:
        policy = policies[kid]
        ok, retry_after = deps.ledger.check(kid, policy)
        if not ok:
            raise HTTPException(
                429,
                {"error": {"message": "quota exceeded", "type": "rate_limit_error"}},
                headers={"Retry-After": str(retry_after)},
            )
        return policy

    # ---- probes ----------------------------------------------------------------------------
    @app.get("/healthz", summary="Liveness", tags=["probes"])
    def healthz() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/readyz", summary="Readiness: the broker answers", tags=["probes"])
    def readyz() -> JSONResponse:
        try:
            ok = bool(deps.ready())
        except Exception:  # noqa: BLE001 — a readiness check that throws is "not ready"
            ok = False
        return JSONResponse(
            {"status": "ready" if ok else "not ready"}, status_code=200 if ok else 503
        )

    # ---- OpenAI surface ----------------------------------------------------------------------
    @app.get("/v1/models", summary="The two models: llm and docs", tags=["openai"])
    def models(_: str = Depends(auth)) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": m, "object": "model", "owned_by": "steakllm"} for m in MODELS],
        }

    @app.post(
        "/v1/chat/completions",
        summary="Chat (llm) or chat over your documents (docs); streaming supported",
        tags=["openai"],
    )
    def chat(body: ChatBody, request: Request, kid: str = Depends(auth)):
        if body.model not in MODELS:
            raise HTTPException(404, {"error": {"message": f"unknown model {body.model!r}"}})
        policy = check_quota(kid)
        session = body.user or request.headers.get("x-session-id") or f"s_{uuid.uuid4().hex[:8]}"
        messages: list[dict[str, Any]] = body.messages
        retrieved: list[str] = []
        if body.model == "docs":
            if deps.retriever is None:
                raise HTTPException(503, {"error": {"message": "retrieval not configured"}})
            hits = deps.retriever.search(last_user_question(body.messages), policy.collection)
            messages = build_messages(body.messages, hits)
            retrieved = list(dict.fromkeys(h.doc_id for h in hits))
        req = ChatRequest(
            model=body.model,
            messages=messages,
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
                tokens_in = int(usage.get("prompt_tokens", 0))
                tokens_out = int(usage.get("completion_tokens", 0))
                deps.ledger.add_tokens(kid, tokens_in + tokens_out)
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
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "latency_ms": latency_ms,
                        "api_key_id": kid,
                        "retrieved_doc_ids": retrieved,
                    },
                }
                validate(ev)
                produce(deps.producer, s.topic_chats, ev)
                log.info(
                    "chat completed",
                    backend=backend,
                    model=body.model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    stream=body.stream,
                    retrieved=len(retrieved),
                )

            headers = {"x-backend": backend, "x-trace-id": trace}
            if retrieved:
                headers["x-retrieved-doc-ids"] = ",".join(retrieved)
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

    # ---- documents ---------------------------------------------------------------------------
    @app.post(
        "/v1/uploads",
        summary="Get a presigned PUT URL into quarantine/ (5 minutes)",
        tags=["documents"],
        status_code=201,
    )
    def uploads(body: UploadBody, kid: str = Depends(auth)) -> dict[str, Any]:
        check_quota(kid)
        try:
            out = presign_upload(deps.s3, s, body.filename, body.content_type, body.size_bytes)
        except ValueError as e:
            raise HTTPException(415, {"error": {"message": str(e)}}) from e
        except OverflowError as e:
            raise HTTPException(413, {"error": {"message": str(e)}}) from e
        log.info("upload presigned", key=out["key"], api_key_id=kid)
        return out

    @app.delete(
        "/v1/documents/{doc_id}",
        summary="Delete a document everywhere (object, vectors, summary, row)",
        tags=["documents"],
        status_code=204,
    )
    def delete(doc_id: str, kid: str = Depends(auth)) -> Response:
        check_quota(kid)
        if not delete_document(deps.s3, deps.table, deps.producer, s, doc_id, kid, deps.now()):
            raise HTTPException(404, {"error": {"message": "unknown document"}})
        log.info("document deleted", doc_id=doc_id, api_key_id=kid)
        return Response(status_code=204)

    @app.get(
        "/catalog",
        summary="Every document's journey: uploaded → indexed → summarized",
        tags=["documents"],
        response_class=HTMLResponse,
    )
    def catalog(_: str = Depends(auth)) -> HTMLResponse:
        rows = deps.table.scan().get("Items", []) if deps.table is not None else []
        return HTMLResponse(catalog_html(rows))

    return app
