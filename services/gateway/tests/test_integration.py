"""On the real stack (make up) with real Bedrock: the stub is down, so every answer is bedrock.

Cost: one short Bedrock call (a fraction of a cent). The ChatCompleted is read back off `chats`.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from kafka import KafkaConsumer
from steakllm_common.clients import bedrock_client
from steakllm_common.kafka import make_producer
from steakllm_common.logging import configure
from steakllm_common.settings import Settings
from steakllm_contracts.validate import validate

from steakllm_gateway.app import Deps, create_app
from steakllm_gateway.backends import BedrockBackend, VllmBackend
from steakllm_gateway.router import CircuitBreaker, Router

pytestmark = pytest.mark.integration


def test_with_the_stub_down_every_answer_is_bedrock_and_an_event_lands_on_chats():
    configure("gateway-it")
    s = Settings()
    router = Router(
        vllm=VllmBackend(s.vllm_url, probe_timeout=s.vllm_probe_timeout_seconds),
        bedrock=BedrockBackend(bedrock_client(s), s.bedrock_model_id),
        breaker=CircuitBreaker(s.breaker_failures, s.breaker_open_seconds),
    )
    producer = make_producer(s)
    client = TestClient(create_app(Deps(settings=s, router=router, producer=producer)))
    session = f"it_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {s.gateway_api_key}"},
        json={
            "model": "llm",
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            "max_tokens": 5,
            "user": session,
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["x-backend"] == "bedrock"
    assert "ready" in r.json()["choices"][0]["message"]["content"].lower()
    assert int(r.headers["x-tokens-in"]) > 0
    assert router.demand >= 1 and router.breaker.failures >= 1  # the stub was probed and found dead
    producer.flush()

    reader = KafkaConsumer(
        s.topic_chats,
        bootstrap_servers=s.kafka_bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=30000,
        value_deserializer=lambda b: json.loads(b),
    )
    found = next(
        (m.value for m in reader if m.value.get("data", {}).get("session_id") == session), None
    )
    assert found is not None, "no ChatCompleted for this session within 30 s"
    validate(found)
    assert found["data"]["backend"] == "bedrock" and found["data"]["tokens_out"] > 0
