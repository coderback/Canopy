"""Per-tenant rate limiting.

Xero limits are 60 calls/min and 5,000/day PER TENANT, so fan-out across
tenants parallelises safely — but each tenant needs its own limiter.
"""

import asyncio
import time
from collections import defaultdict, deque


class PerTenantRateLimiter:
    def __init__(self, max_calls: int = 55, window_seconds: float = 60.0):
        # 55/min leaves headroom under Xero's 60/min tenant limit.
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, tenant_id: str) -> None:
        async with self._locks[tenant_id]:
            calls = self._calls[tenant_id]
            now = time.monotonic()
            while calls and now - calls[0] > self.window:
                calls.popleft()
            if len(calls) >= self.max_calls:
                sleep_for = self.window - (now - calls[0]) + 0.05
                await asyncio.sleep(max(sleep_for, 0))
                now = time.monotonic()
                while calls and now - calls[0] > self.window:
                    calls.popleft()
            calls.append(time.monotonic())


limiter = PerTenantRateLimiter()
