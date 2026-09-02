"""The summarizer's only way to an LLM: the gateway's OpenAI-compatible chat route.

It never talks to vLLM or Bedrock itself, so it inherits the routing policy. The gateway reports
which backend answered (`x-backend`) and the token counts (`x-tokens-in`, `x-tokens-out`), or, for
any OpenAI-compatible server, the `usage` block in the body.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ChatResult:
    text: str
    backend: str  # "vllm" | "bedrock"
    model: str
    tokens_in: int
    tokens_out: int


class GatewayChat:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "llm",
        prefer_vllm_seconds: int = 600,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prefer_vllm_seconds = prefer_vllm_seconds
        self.client = client or httpx.Client(timeout=120)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def complete(self, prompt: str, max_tokens: int = 400) -> ChatResult:
        r = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={**self.headers, "x-prefer-vllm-seconds": str(self.prefer_vllm_seconds)},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
        )
        r.raise_for_status()
        body = r.json()
        usage = body.get("usage") or {}
        backend = r.headers.get("x-backend") or "bedrock"
        if backend not in ("vllm", "bedrock"):
            backend = "bedrock"  # a tolerant reader: an unknown backend is "not the GPU"
        return ChatResult(
            text=body["choices"][0]["message"]["content"],
            backend=backend,
            model=body.get("model") or self.model,
            tokens_in=int(r.headers.get("x-tokens-in") or usage.get("prompt_tokens") or 0),
            tokens_out=int(r.headers.get("x-tokens-out") or usage.get("completion_tokens") or 0),
        )
