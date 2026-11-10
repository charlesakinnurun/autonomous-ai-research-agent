"""Bounded async retries.

Only errors marked ``retryable`` are retried. This prevents a 401/403 or a
validation error from burning the daily quota.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from research_agent.core.errors import ResearchAgentError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter: float = 0.25

    def delay_for(self, attempt: int, *, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_delay_seconds)
        exponential = self.base_delay_seconds * (2 ** max(attempt - 1, 0))
        capped = min(exponential, self.max_delay_seconds)
        jitter_amount: float = capped * self.jitter * random.random()  # noqa: S311
        return float(capped + jitter_amount)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ResearchAgentError):
        return exc.retryable
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError))


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    should_retry: Callable[[BaseException], bool] = is_retryable,
) -> T:
    """Execute ``operation`` with bounded exponential backoff + jitter."""
    policy = policy or RetryPolicy()
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except BaseException as exc:
            last_error = exc
            if attempt >= policy.max_attempts or not should_retry(exc):
                raise
            retry_after = getattr(exc, "retry_after_seconds", None)
            await asyncio.sleep(policy.delay_for(attempt, retry_after=retry_after))
    assert last_error is not None  # pragma: no cover - loop always sets it
    raise last_error
