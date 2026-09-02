"""The routing policy: "is vLLM healthy right now?" — per request, never waited on, never sticky.

    closed ──3 failures──▶ open ──60 s──▶ half-open ──probe ok──▶ closed
                                            └──probe fails──▶ open

While open, Bedrock answers and vLLM is not even probed; the demand signal is bumped on every
fallback so the GPU can be summoned (Step 9). A vLLM call that fails mid-request falls back too.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from steakllm_common.logging import get_logger

from .backends import BedrockBackend, ChatRequest, ChatResult, VllmBackend

log = get_logger(__name__)


@dataclass
class CircuitBreaker:
    failures_to_open: int = 3
    open_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    opened_at: float | None = None
    half_open_probe_taken: bool = False

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self.clock() - self.opened_at >= self.open_seconds:
            return "half-open"
        return "open"

    def allow_vllm(self) -> bool:
        """May this request try vLLM? closed: yes; open: no; half-open: exactly one probe."""
        st = self.state
        if st == "closed":
            return True
        if st == "half-open" and not self.half_open_probe_taken:
            self.half_open_probe_taken = True
            return True
        return False

    def record_success(self) -> None:
        if self.opened_at is not None:
            log.info("circuit closed")
        self.failures, self.opened_at, self.half_open_probe_taken = 0, None, False

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == "half-open" or self.failures >= self.failures_to_open:
            if self.opened_at is None or self.state == "half-open":
                log.warning("circuit open", failures=self.failures, seconds=self.open_seconds)
            self.opened_at = self.clock()
            self.half_open_probe_taken = False


@dataclass
class Router:
    vllm: VllmBackend
    bedrock: BedrockBackend
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    probe_cache_seconds: float = 2.0
    clock: Callable[[], float] = time.monotonic
    demand: int = 0  # bumped on every fallback; Step 9 turns this into the GPU summons
    _probe: tuple[float, bool] | None = None

    def vllm_healthy(self) -> bool:
        now = self.clock()
        if self._probe and now - self._probe[0] < self.probe_cache_seconds:
            return self._probe[1]
        ok = self.vllm.healthy()
        self._probe = (now, ok)
        return ok

    def choose(self) -> str:
        if not self.breaker.allow_vllm():
            self.demand += 1
            return "bedrock"
        if self.vllm_healthy():
            return "vllm"
        self.breaker.record_failure()
        self.demand += 1
        return "bedrock"

    def complete(self, req: ChatRequest) -> tuple[str, ChatResult]:
        backend = self.choose()
        if backend == "vllm":
            try:
                result = self.vllm.chat(req)
                self.breaker.record_success()
                return "vllm", result
            except Exception as e:  # noqa: BLE001 — any vLLM failure means "fall back now"
                log.warning("vllm call failed; falling back", error=repr(e))
                self.breaker.record_failure()
                self.demand += 1
        return "bedrock", self.bedrock.chat(req)
