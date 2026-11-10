"""Shared pytest fixtures.

Windows note: psycopg's async driver cannot use the default ProactorEventLoop.
The policy is set at import time, before pytest-asyncio creates a loop.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Table, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from research_agent.cache import CacheStore
from research_agent.config import Settings
from research_agent.db.base import Base
from research_agent.db.models import (
    Approval,
    Claim,
    Document,
    IdempotencyKey,
    ProviderHealth,
    QuotaReservation,
    QuotaUsage,
    Run,
    RunEvent,
    RunJob,
    Source,
)
from research_agent.db.session import Database

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEFAULT_TEST_DATABASE = "postgresql+psycopg://research:research@localhost:5432/research"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        llm_mode="replay",
        cache_dir=tmp_path / "cache",
        database_url=os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE),
    )


@pytest.fixture
def cache_factory(tmp_path: Path) -> Callable[[str], CacheStore]:
    def factory(mode: str = "record") -> CacheStore:
        return CacheStore(tmp_path / f"cache-{mode}", mode=mode)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve test hostnames to a public documentation IP."""

    def fake_getaddrinfo(
        host: str, port: object, *args: object, **kwargs: object
    ) -> list[tuple[object, ...]]:
        if host in {"localhost", "127.0.0.1", "::1", "10.0.0.1", "169.254.169.254"}:
            address = "127.0.0.1" if host == "localhost" else host
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def _database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get(
        "DATABASE_URL", DEFAULT_TEST_DATABASE
    )


def _can_connect(url: str) -> bool:
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
def postgres_settings() -> Settings:
    url = _database_url()
    if not _can_connect(url):
        pytest.skip(f"Postgres is not reachable at {url}")
    return Settings(_env_file=None, app_env="test", llm_mode="replay", database_url=url)


@pytest_asyncio.fixture
async def vector_available(database: Database) -> bool:
    async with database.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        available = result.scalar() == 1
    if not available:
        pytest.skip("pgvector extension is not installed in the test database")
    return True


def _core_tables() -> list[Table]:
    return [
        Run.__table__,
        RunEvent.__table__,
        Source.__table__,
        Document.__table__,
        Claim.__table__,
        Approval.__table__,
        QuotaUsage.__table__,
        QuotaReservation.__table__,
        RunJob.__table__,
        IdempotencyKey.__table__,
        ProviderHealth.__table__,
    ]


def _vector_tables() -> list[Table]:
    from research_agent.db.models import Chunk, Citation, ClaimEvidence, MemoryItem

    return [Chunk.__table__, Citation.__table__, ClaimEvidence.__table__, MemoryItem.__table__]


async def _has_vector(database: Database) -> bool:
    async with database.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        return result.scalar() == 1


@pytest_asyncio.fixture
async def database(postgres_settings: Settings) -> AsyncIterator[Database]:
    db = Database(postgres_settings)
    tables = list(_core_tables())
    if await _has_vector(db):
        tables.extend(_vector_tables())
    async with db.engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.drop_all(sync_connection, tables=tables)
        )
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables)
        )
    try:
        yield db
    finally:
        async with db.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.drop_all(sync_connection, tables=tables)
            )
        await db.dispose()


@pytest_asyncio.fixture
async def db_session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as session:
        yield session
        await session.rollback()
