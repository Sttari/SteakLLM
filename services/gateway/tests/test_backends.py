"""Bedrock ↔ OpenAI translation on a fake Bedrock client; vLLM passthrough on a mock transport."""

from __future__ import annotations

import json

import httpx

from steakllm_gateway.backends import BedrockBackend, ChatRequest, VllmBackend, to_converse


def test_openai_messages_become_converse_system_and_alternating_turns():
    system, convo = to_converse(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "again"},  # two user turns in a row → merged
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ]
    )
    assert system == [{"text": "Be brief."}]
    assert [m["role"] for m in convo] == ["user", "assistant"]
    assert convo[0]["content"] == [{"text": "hi"}, {"text": "again"}]
    assert convo[1]["content"] == [{"text": "hello"}]


class FakeBedrockClient:
    def converse(self, **kw):
        assert (
            kw["modelId"] == "amazon.nova-micro-v1:0" and kw["inferenceConfig"]["maxTokens"] == 32
        )
        return {
            "output": {"message": {"content": [{"text": "hello "}, {"text": "there"}]}},
            "usage": {"inputTokens": 7, "outputTokens": 2},
            "stopReason": "end_turn",
        }

    def converse_stream(self, **kw):
        return {
            "stream": iter(
                [
                    {"contentBlockDelta": {"delta": {"text": "hel"}}},
                    {"contentBlockDelta": {"delta": {"text": "lo"}}},
                    {"messageStop": {"stopReason": "max_tokens"}},
                    {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 2}}},
                ]
            )
        }


def test_bedrock_non_streaming_reply_has_the_openai_shape():
    b = BedrockBackend(FakeBedrockClient(), "amazon.nova-micro-v1:0")
    r = b.chat(ChatRequest("llm", [{"role": "user", "content": "hi"}], max_tokens=32))
    assert r.body["object"] == "chat.completion"
    assert r.body["choices"][0]["message"] == {"role": "assistant", "content": "hello there"}
    assert r.body["choices"][0]["finish_reason"] == "stop"
    assert r.usage == {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}


def test_bedrock_streaming_reply_is_openai_sse_with_usage_at_the_end():
    b = BedrockBackend(FakeBedrockClient(), "amazon.nova-micro-v1:0")
    r = b.chat(ChatRequest("llm", [{"role": "user", "content": "hi"}], stream=True, max_tokens=32))
    lines = [line.decode() for line in r.events]
    assert lines[-1] == "data: [DONE]\n\n"
    chunks = [json.loads(line[6:]) for line in lines[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "hello"
    assert chunks[-1]["choices"][0]["finish_reason"] == "length"
    assert r.usage["completion_tokens"] == 2  # captured only after the stream ended


def test_vllm_passthrough_and_probe():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        body = json.loads(request.read())
        assert body["model"] == "llm" and body["stream"] is False
        return httpx.Response(
            200,
            json={
                "model": "Qwen",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    v = VllmBackend("http://vllm", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert v.healthy()
    r = v.chat(ChatRequest("llm", [{"role": "user", "content": "hi"}]))
    assert r.model == "Qwen" and r.usage["prompt_tokens"] == 3


def test_vllm_probe_failure_is_false_not_an_exception():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    v = VllmBackend("http://vllm", client=httpx.Client(transport=httpx.MockTransport(down)))
    assert v.healthy() is False
