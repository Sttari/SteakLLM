"""The circuit breaker's state machine and the router's choices, on fakes and a fake clock."""

from __future__ import annotations

from dataclasses import dataclass, field

from steakllm_gateway.backends import ChatRequest, ChatResult
from steakllm_gateway.router import CircuitBreaker, Router


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@dataclass
class FakeVllm:
    name = "vllm"
    up: bool = True
    fail_calls: bool = False
    probes: int = 0
    calls: int = 0

    def healthy(self):
        self.probes += 1
        return self.up

    def chat(self, req):
        self.calls += 1
        if self.fail_calls:
            raise ConnectionError("vllm died mid-request")
        return ChatResult(
            body={"choices": []}, usage={"prompt_tokens": 1, "completion_tokens": 1}, model="v"
        )


@dataclass
class FakeBedrock:
    name = "bedrock"
    calls: int = 0
    log: list = field(default_factory=list)

    def chat(self, req):
        self.calls += 1
        return ChatResult(
            body={"choices": []}, usage={"prompt_tokens": 2, "completion_tokens": 2}, model="b"
        )


REQ = ChatRequest(model="llm", messages=[{"role": "user", "content": "hi"}])


def make(up=True, fail_calls=False):
    clock = Clock()
    vllm, bedrock = FakeVllm(up=up, fail_calls=fail_calls), FakeBedrock()
    breaker = CircuitBreaker(failures_to_open=3, open_seconds=60, clock=clock)
    router = Router(vllm=vllm, bedrock=bedrock, breaker=breaker, probe_cache_seconds=2, clock=clock)
    return router, vllm, bedrock, breaker, clock


def test_healthy_vllm_is_used_and_probe_is_cached():
    router, vllm, bedrock, *_ = make()
    for _ in range(5):
        backend, _ = router.complete(REQ)
        assert backend == "vllm"
    assert vllm.probes == 1 and vllm.calls == 5 and bedrock.calls == 0


def test_unhealthy_vllm_falls_back_and_bumps_demand():
    router, vllm, bedrock, breaker, clock = make(up=False)
    backend, _ = router.complete(REQ)
    assert backend == "bedrock" and bedrock.calls == 1 and router.demand == 1
    assert breaker.failures == 1 and breaker.state == "closed"


def test_three_failures_open_the_breaker_and_stop_probing():
    router, vllm, bedrock, breaker, clock = make(up=False)
    for _ in range(3):
        clock.t += 3  # past the probe cache each time
        router.complete(REQ)
    assert breaker.state == "open"
    probes = vllm.probes
    clock.t += 3
    router.complete(REQ)
    assert vllm.probes == probes  # open: no probe at all
    assert bedrock.calls == 4 and router.demand == 4


def test_half_open_lets_one_probe_through_and_closes_on_success():
    router, vllm, bedrock, breaker, clock = make(up=False)
    for _ in range(3):
        clock.t += 3
        router.complete(REQ)
    assert breaker.state == "open"
    clock.t += 61
    assert breaker.state == "half-open"
    vllm.up = True
    backend, _ = router.complete(REQ)
    assert backend == "vllm" and breaker.state == "closed" and breaker.failures == 0


def test_half_open_probe_failure_reopens():
    router, vllm, bedrock, breaker, clock = make(up=False)
    for _ in range(3):
        clock.t += 3
        router.complete(REQ)
    clock.t += 61
    backend, _ = router.complete(REQ)  # the one probe, still down
    assert backend == "bedrock" and breaker.state == "open"
    clock.t += 3
    probes = vllm.probes
    router.complete(REQ)
    assert vllm.probes == probes  # back to open: no probing


def test_vllm_failure_mid_request_falls_back_and_counts():
    router, vllm, bedrock, breaker, clock = make(up=True, fail_calls=True)
    backend, result = router.complete(REQ)
    assert backend == "bedrock" and bedrock.calls == 1 and breaker.failures == 1
    assert result.usage["prompt_tokens"] == 2
