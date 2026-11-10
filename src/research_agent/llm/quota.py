"""Quota tracking: daily counters + per-minute windows.

Daily counters are persisted by the store (Postgres in production, in-memory in
tests). Minute windows are process-local; a restart loses at most one minute of
rate-limit state, which is acceptable for the laptop deployment and is
documented in ``docs/QUOTA_PLAN.md``.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID

from research_agent.core.errors import QuotaExceeded
from research_agent.core.ids import utc_now
from research_agent.models.common import (
    QuotaLimits,
    QuotaReservationRecord,
    QuotaSnapshot,
    TokenUsage,
)


class QuotaStore(Protocol):
    async def get_usage(self, provider: str, model: str, day: date) -> QuotaSnapshot: ...

    async def reserve(
        self,
        *,
        provider: str,
        model: str,
        day: date,
        tokens: int,
        expires_at: datetime,
        run_id: UUID | None,
    ) -> QuotaReservationRecord: ...

    async def commit(
        self,
        *,
        reservation_id: UUID,
        tokens_in: int,
        tokens_out: int,
        requests: int = 1,
    ) -> None: ...

    async def release(self, reservation_id: UUID) -> None: ...


class InMemoryQuotaStore:
    """Deterministic store for unit tests and single-process dry runs."""

    def __init__(self) -> None:
        self._usage: dict[tuple[str, str, date], QuotaSnapshot] = {}
        self._reservations: dict[UUID, QuotaReservationRecord] = {}
        self._lock = asyncio.Lock()

    async def get_usage(self, provider: str, model: str, day: date) -> QuotaSnapshot:
        async with self._lock:
            return self._usage.get(
                (provider, model, day),
                QuotaSnapshot(provider=provider, model=model, day=day),
            )

    async def reserve(
        self,
        *,
        provider: str,
        model: str,
        day: date,
        tokens: int,
        expires_at: datetime,
        run_id: UUID | None,
    ) -> QuotaReservationRecord:
        async with self._lock:
            snapshot = self._usage.get(
                (provider, model, day),
                QuotaSnapshot(provider=provider, model=model, day=day),
            )
            updated = snapshot.model_copy(update={"reserved": snapshot.reserved + tokens})
            self._usage[(provider, model, day)] = updated
            record = _reservation(provider, model, day, tokens, expires_at)
            self._reservations[record.id] = record
            return record

    async def commit(
        self,
        *,
        reservation_id: UUID,
        tokens_in: int,
        tokens_out: int,
        requests: int = 1,
    ) -> None:
        async with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return
            key = (reservation.provider, reservation.model, reservation.day)
            snapshot = self._usage.get(
                key,
                QuotaSnapshot(
                    provider=reservation.provider, model=reservation.model, day=reservation.day
                ),
            )
            self._usage[key] = QuotaSnapshot(
                provider=snapshot.provider,
                model=snapshot.model,
                day=snapshot.day,
                requests=snapshot.requests + requests,
                tokens_in=snapshot.tokens_in + tokens_in,
                tokens_out=snapshot.tokens_out + tokens_out,
                reserved=max(0, snapshot.reserved - reservation.tokens),
            )

    async def release(self, reservation_id: UUID) -> None:
        async with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return
            key = (reservation.provider, reservation.model, reservation.day)
            snapshot = self._usage.get(key)
            if snapshot is not None:
                self._usage[key] = snapshot.model_copy(
                    update={"reserved": max(0, snapshot.reserved - reservation.tokens)}
                )


class _MinuteWindow:
    def __init__(self) -> None:
        self._events: deque[tuple[float, int]] = deque()

    def check_and_add(self, *, now: float, tokens: int, rpm: int, tpm: int) -> bool:
        while self._events and now - self._events[0][0] >= 60.0:
            self._events.popleft()
        requests = len(self._events)
        token_total = sum(item[1] for item in self._events)
        if rpm > 0 and requests + 1 > rpm:
            return False
        if tpm > 0 and token_total + tokens > tpm:
            return False
        self._events.append((now, tokens))
        return True


class QuotaTracker:
    """Reserve/commit quota around a provider call.

    The caller must reserve *before* the call and either commit or release after
    it. A crashed worker leaves a reservation that expires after
    ``reservation_ttl_seconds`` and is reclaimed by the Postgres store's cleanup.
    """

    def __init__(
        self,
        store: QuotaStore,
        limits_by_provider: dict[str, QuotaLimits],
        *,
        reservation_ttl_seconds: float = 600.0,
    ) -> None:
        self.store = store
        self.limits_by_provider = limits_by_provider
        self.reservation_ttl_seconds = reservation_ttl_seconds
        self._windows: dict[tuple[str, str], _MinuteWindow] = defaultdict(_MinuteWindow)

    def limits_for(self, provider: str) -> QuotaLimits:
        try:
            return self.limits_by_provider[provider]
        except KeyError as exc:
            raise QuotaExceeded(f"no quota limits configured for provider: {provider}") from exc

    async def reserve(
        self,
        *,
        provider: str,
        model: str,
        estimated_tokens: int,
        run_id: UUID | None = None,
    ) -> QuotaReservationRecord:
        limits = self.limits_for(provider)
        day = utc_now().date()
        snapshot = await self.store.get_usage(provider, model, day)
        if limits.rpd > 0 and snapshot.requests + 1 > limits.rpd:
            raise QuotaExceeded(
                f"daily request limit reached for {provider}",
                details={"provider": provider, "model": model, "rpd": str(limits.rpd)},
            )
        if limits.tpd > 0 and snapshot.total_tokens + estimated_tokens > limits.tpd:
            raise QuotaExceeded(
                f"daily token limit reached for {provider}",
                details={
                    "provider": provider,
                    "model": model,
                    "tpd": str(limits.tpd),
                    "used": str(snapshot.total_tokens),
                    "requested": str(estimated_tokens),
                },
            )
        window = self._windows[(provider, model)]
        if not window.check_and_add(
            now=time.monotonic(),
            tokens=estimated_tokens,
            rpm=limits.rpm,
            tpm=limits.tpm,
        ):
            raise QuotaExceeded(
                f"per-minute quota reached for {provider}",
                details={"provider": provider, "model": model},
            )
        return await self.store.reserve(
            provider=provider,
            model=model,
            day=day,
            tokens=max(0, estimated_tokens),
            expires_at=datetime.now(UTC) + timedelta(seconds=self.reservation_ttl_seconds),
            run_id=run_id,
        )

    async def commit(self, reservation_id: UUID, usage: TokenUsage) -> None:
        await self.store.commit(
            reservation_id=reservation_id,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            requests=max(1, usage.requests),
        )

    async def release(self, reservation_id: UUID) -> None:
        await self.store.release(reservation_id)


def _reservation(
    provider: str, model: str, day: date, tokens: int, expires_at: datetime
) -> QuotaReservationRecord:
    from uuid import uuid4

    return QuotaReservationRecord(
        id=uuid4(),
        provider=provider,
        model=model,
        day=day,
        tokens=tokens,
        expires_at=expires_at,
    )
