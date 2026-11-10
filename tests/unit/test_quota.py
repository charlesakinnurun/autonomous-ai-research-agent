"""Quota tracker and store tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from research_agent.core.errors import QuotaExceeded
from research_agent.db.repositories.quota import PostgresQuotaStore
from research_agent.db.session import Database
from research_agent.llm.quota import InMemoryQuotaStore, QuotaTracker
from research_agent.models.common import QuotaLimits, TokenUsage


def _tracker(limits: QuotaLimits) -> QuotaTracker:
    return QuotaTracker(InMemoryQuotaStore(), {"groq": limits})


@pytest.mark.asyncio
async def test_reserve_commit_release() -> None:
    tracker = _tracker(QuotaLimits())
    reservation = await tracker.reserve(provider="groq", model="m", estimated_tokens=100)
    snapshot = await tracker.store.get_usage("groq", "m", reservation.day)
    assert snapshot.reserved == 100
    await tracker.commit(reservation.id, TokenUsage(input_tokens=40, output_tokens=10, requests=1))
    snapshot = await tracker.store.get_usage("groq", "m", reservation.day)
    assert snapshot.reserved == 0
    assert snapshot.requests == 1
    assert snapshot.total_tokens == 50

    other = await tracker.reserve(provider="groq", model="m", estimated_tokens=25)
    await tracker.release(other.id)
    snapshot = await tracker.store.get_usage("groq", "m", reservation.day)
    assert snapshot.reserved == 0


@pytest.mark.asyncio
async def test_daily_request_limit() -> None:
    tracker = _tracker(QuotaLimits(rpd=1))
    reservation = await tracker.reserve(provider="groq", model="m", estimated_tokens=10)
    await tracker.commit(reservation.id, TokenUsage(input_tokens=1, output_tokens=1, requests=1))
    with pytest.raises(QuotaExceeded):
        await tracker.reserve(provider="groq", model="m", estimated_tokens=10)


@pytest.mark.asyncio
async def test_daily_token_limit() -> None:
    tracker = _tracker(QuotaLimits(tpd=100))
    reservation = await tracker.reserve(provider="groq", model="m", estimated_tokens=60)
    await tracker.commit(reservation.id, TokenUsage(input_tokens=50, output_tokens=10, requests=1))
    with pytest.raises(QuotaExceeded):
        await tracker.reserve(provider="groq", model="m", estimated_tokens=60)


@pytest.mark.asyncio
async def test_minute_limits() -> None:
    rpm = _tracker(QuotaLimits(rpm=1))
    await rpm.reserve(provider="groq", model="m", estimated_tokens=10)
    with pytest.raises(QuotaExceeded):
        await rpm.reserve(provider="groq", model="m", estimated_tokens=10)

    tpm = _tracker(QuotaLimits(tpm=20))
    with pytest.raises(QuotaExceeded):
        await tpm.reserve(provider="groq", model="m", estimated_tokens=21)


@pytest.mark.asyncio
async def test_unknown_provider_fails_closed() -> None:
    tracker = QuotaTracker(InMemoryQuotaStore(), {})
    with pytest.raises(QuotaExceeded):
        await tracker.reserve(provider="unknown", model="m", estimated_tokens=1)


@pytest.mark.asyncio
async def test_postgres_quota_store_round_trip(database: Database) -> None:
    async with database.session_factory() as session:
        store = PostgresQuotaStore(session)
        tracker = QuotaTracker(store, {"groq": QuotaLimits(rpd=10, tpd=1000)})
        reservation = await tracker.reserve(provider="groq", model="m", estimated_tokens=100)
        snapshot = await store.get_usage("groq", "m", reservation.day)
        assert snapshot.reserved == 100
        await tracker.commit(
            reservation.id, TokenUsage(input_tokens=40, output_tokens=20, requests=1)
        )
        await session.commit()
        snapshot = await store.get_usage("groq", "m", reservation.day)
        assert snapshot.requests == 1
        assert snapshot.total_tokens == 60
        assert snapshot.reserved == 0

        stale = await store.reserve(
            provider="groq",
            model="m",
            day=reservation.day,
            tokens=10,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            run_id=None,
        )
        assert await store.expire_stale(now=datetime.now(UTC)) >= 1
        snapshot = await store.get_usage("groq", "m", reservation.day)
        assert snapshot.reserved == 0
        assert stale.id
        await session.commit()
