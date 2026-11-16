"""Real PostGIS and MongoDB in throwaway containers (testcontainers).

Everything here is marked ``integration`` and excluded from the default run: it needs Docker.
Run it with ``make test-integration``.
"""

import asyncio
import os
import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.mongodb import MongoDbContainer
from testcontainers.community.postgres import PostgresContainer

# The reaper container is one more image to pull and a common source of hangs on Windows; the
# fixtures below stop their containers themselves.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from real_estate_price_tracking_systems.infrastructure.persistence.postgres.connection import (  # noqa: E402
    create_pg_pool,
)

ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = ROOT / "sql" / "init.sql"
POSTGIS_IMAGE = "postgis/postgis:16-3.4-alpine"  # same image as docker-compose
MONGO_IMAGE = "mongo:7.0"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test under tests/integration is an integration test."""
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    # psycopg's async API cannot run on Windows' default ProactorEventLoop; use the selector loop
    # everywhere so the tests behave the same on every platform.
    return {"selector": asyncio.SelectorEventLoop}


def _wait_until_accepting(dsn: str, timeout: float = 60.0) -> None:
    """The postgres image logs "ready" once for its temporary init server and again for the real
    one, so poll the published port instead of trusting the log line."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with psycopg.connect(dsn, connect_timeout=2):
                return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """A PostGIS database with the schema of ``sql/init.sql`` (what compose runs on a new volume)."""
    with PostgresContainer(
        POSTGIS_IMAGE, username="test", password="test", dbname="test", driver=None
    ) as container:
        dsn = (
            f"postgresql://test:test@{container.get_container_host_ip()}"
            f":{container.get_exposed_port(5432)}/test"
        )
        _wait_until_accepting(dsn)
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(INIT_SQL.read_text(encoding="utf-8"))  # type: ignore[arg-type]
        yield dsn


@pytest.fixture
async def pg_pool(postgres_dsn: str) -> AsyncIterator[AsyncConnectionPool]:
    """A pool on the shared database; the tables the tests write to start empty."""
    pool = create_pg_pool(postgres_dsn, min_size=1, max_size=4, timeout=10)
    await pool.open(wait=True)
    try:
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE crawl_runs, crawler_configs CASCADE")
        yield pool
    finally:
        await pool.close()


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer(MONGO_IMAGE) as container:
        yield container.get_connection_url()
