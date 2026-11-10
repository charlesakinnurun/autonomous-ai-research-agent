"""Alembic migration tests.

The apply/downgrade test requires pgvector because the initial schema contains
VECTOR columns and HNSW indexes. It is skipped on hosts without the extension;
the offline SQL test always runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from research_agent.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["APP_ENV"] = "test"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.integration
def test_offline_sql_contains_vector_schema(settings: Settings) -> None:
    result = _run_alembic("upgrade", "head", "--sql", database_url=settings.database_url)
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "VECTOR(384)" in sql
    assert "CREATE TABLE runs" in sql
    assert "ix_chunks_embedding_hnsw" in sql


@pytest.mark.integration
def test_upgrade_and_downgrade_on_empty_database(postgres_settings: Settings) -> None:
    base_url = make_url(postgres_settings.database_url)
    admin_engine = create_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    db_name = f"research_migrate_{uuid.uuid4().hex[:12]}"
    with admin_engine.connect() as connection:
        available = connection.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if available != 1:
            admin_engine.dispose()
            pytest.skip("pgvector is not available on this Postgres server")
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    temp_url = base_url.set(database=db_name).render_as_string(hide_password=False)
    try:
        upgrade = _run_alembic("upgrade", "head", database_url=temp_url)
        assert upgrade.returncode == 0, upgrade.stderr
        engine = create_engine(temp_url)
        tables = set(inspect(engine).get_table_names())
        assert {"runs", "sources", "documents", "chunks", "claims", "citations"} <= tables
        assert "alembic_version" in tables
        engine.dispose()

        downgrade = _run_alembic("downgrade", "base", database_url=temp_url)
        assert downgrade.returncode == 0, downgrade.stderr
        engine = create_engine(temp_url)
        remaining = set(inspect(engine).get_table_names())
        assert "runs" not in remaining
        engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()
