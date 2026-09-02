"""Two backends, one interface: vLLM (OpenAI passthrough) and Bedrock (Converse, translated).

Both take an OpenAI-shaped chat request and return an OpenAI-shaped result — either a full
response dict, or an async/sync iterator of Server-Sent-Event lines for streaming — plus the token
usage, so the router and the event emitter never care which one answered.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ChatRequest:
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    max_tokens: int = 512
    temperature: float = 0.2


@dataclass
class ChatResult:
    body: dict[str, Any] | None = None  # non-streaming
    events: Iterator[bytes] | None = None  # streaming: raw SSE lines
    usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0}
    )
    model: str = ""


def _sse(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj)}\n\n".encode()


# ---- vLLM: pass the request through; capture usage from the reply ----------------------------


class VllmBackend:
    name = "vllm"

    def __init__(self, url: str, client: httpx.Client | None = None, probe_timeout: float = 0.3):
        self.url = url.rstrip("/")
        self.client = client or httpx.Client(timeout=120)
        self.probe_timeout = probe_timeout

    def healthy(self) -> bool:
        try:
            return (
                self.client.get(f"{self.url}/health", timeout=self.probe_timeout).status_code == 200
            )
        except httpx.HTTPError:
            return False

    def chat(self, req: ChatRequest) -> ChatResult:
        payload = {
            "model": req.model,
            "messages": req.messages,
            "stream": req.stream,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.stream:
            payload["stream_options"] = {"include_usage": True}
            r = self.client.send(
                self.client.build_request("POST", f"{self.url}/v1/chat/completions", json=payload),
                stream=True,
            )
            r.raise_for_status()
            result = ChatResult(model=req.model)

            def events() -> Iterator[bytes]:
                try:
                    for line in r.iter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            chunk = json.loads(line[6:])
                            if chunk.get("usage"):
                                result.usage = chunk["usage"]
                            result.model = chunk.get("model", result.model)
                        if line:
                            yield (line + "\n\n").encode()
                finally:
                    r.close()

            result.events = events()
            return result
        r = self.client.post(f"{self.url}/v1/chat/completions", json=payload)
        r.raise_for_status()
        body = r.json()
        return ChatResult(
            body=body, usage=body.get("usage", {}), model=body.get("model", req.model)
        )


# ---- Bedrock: OpenAI messages → Converse → OpenAI shape -----------------------------------------


def to_converse(messages: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """OpenAI roles → Converse: system messages become `system`; others alternate user/assistant."""
    system, convo = [], []
    for m in messages:
        text = (
            m["content"]
            if isinstance(m["content"], str)
            else "".join(p.get("text", "") for p in m["content"] if isinstance(p, dict))
        )
        if m["role"] == "system":
            system.append({"text": text})
        else:
            role = "assistant" if m["role"] == "assistant" else "user"
            if convo and convo[-1]["role"] == role:  # Converse insists on alternation
                convo[-1]["content"].append({"text": text})
            else:
                convo.append({"role": role, "content": [{"text": text}]})
    return system, convo


class BedrockBackend:
    name = "bedrock"

    def __init__(self, client: Any, model_id: str):
        self.client = client
        self.model_id = model_id

    def chat(self, req: ChatRequest) -> ChatResult:
        system, convo = to_converse(req.messages)
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": convo,
            "inferenceConfig": {"maxTokens": req.max_tokens, "temperature": req.temperature},
        }
        if system:
            kwargs["system"] = system
        cid, created = f"chatcmpl-{uuid.uuid4().hex[:12]}", int(time.time())
        if not req.stream:
            resp = self.client.converse(**kwargs)
            text = "".join(p.get("text", "") for p in resp["output"]["message"]["content"])
            usage = {
                "prompt_tokens": resp["usage"]["inputTokens"],
                "completion_tokens": resp["usage"]["outputTokens"],
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            body = {
                "id": cid,
                "object": "chat.completion",
                "created": created,
                "model": self.model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": _finish(resp.get("stopReason")),
                    }
                ],
                "usage": usage,
            }
            return ChatResult(body=body, usage=usage, model=self.model_id)

        stream = self.client.converse_stream(**kwargs)
        result = ChatResult(model=self.model_id)

        def events() -> Iterator[bytes]:
            base = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": self.model_id,
            }
            yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}}]})
            finish = "stop"
            for ev in stream["stream"]:
                if "contentBlockDelta" in ev:
                    text = ev["contentBlockDelta"]["delta"].get("text", "")
                    if text:
                        yield _sse({**base, "choices": [{"index": 0, "delta": {"content": text}}]})
                elif "messageStop" in ev:
                    finish = _finish(ev["messageStop"].get("stopReason"))
                elif "metadata" in ev and "usage" in ev["metadata"]:
                    u = ev["metadata"]["usage"]
                    result.usage = {
                        "prompt_tokens": u["inputTokens"],
                        "completion_tokens": u["outputTokens"],
                        "total_tokens": u["inputTokens"] + u["outputTokens"],
                    }
            yield _sse(
                {
                    **base,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    "usage": result.usage,
                }
            )
            yield b"data: [DONE]\n\n"

        result.events = events()
        return result


def _finish(stop_reason: str | None) -> str:
    return "length" if stop_reason == "max_tokens" else "stop"
