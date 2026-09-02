"""Per-key quotas: requests per minute (sliding window) and tokens per UTC day. In memory for now;
Step 10 moves the ledger to DynamoDB so every gateway replica shares it."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KeyPolicy:
    name: str
    collection: str  # which Qdrant collection this key may search
    rpm: int
    tokens_per_day: int


@dataclass
class QuotaLedger:
    clock: Callable[[], float] = time.time
    _requests: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _tokens: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))

    def _day(self) -> int:
        return int(self.clock() // 86400)

    def check(self, key_id: str, policy: KeyPolicy) -> tuple[bool, int]:
        """(allowed, retry_after_seconds). Counts the request when allowed."""
        now = self.clock()
        window = self._requests[key_id]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= policy.rpm:
            return False, max(1, int(60 - (now - window[0])) + 1)
        if self._tokens[(key_id, self._day())] >= policy.tokens_per_day:
            return False, int(86400 - (now % 86400)) + 1
        window.append(now)
        return True, 0

    def add_tokens(self, key_id: str, n: int) -> None:
        self._tokens[(key_id, self._day())] += n

    def used_today(self, key_id: str) -> int:
        return self._tokens[(key_id, self._day())]
