"""The Postgres repositories against a real PostGIS built from sql/init.sql."""

from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from real_estate_price_tracking_systems.domain.entities import (
    CrawlerConfig,
    CrawlRunStatus,
    RunMode,
)
from real_estate_price_tracking_systems.domain.exceptions import (
    ConfigAlreadyExistsError,
    ConfigNotFoundError,
)
from real_estate_price_tracking_systems.infrastructure.config import load_site_config
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_repo import (
    PostgresConfigRepository,
)
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.crawl_run_repo import (
    PostgresCrawlRunRepository,
)

SITES = Path(__file__).resolve().parents[2] / "configs" / "sites"


@pytest.fixture
def meeyland() -> CrawlerConfig:
    return load_site_config(SITES / "meeyland.yaml")


@pytest.fixture
def mogi() -> CrawlerConfig:
    return load_site_config(SITES / "mogi.yaml")


# --- configs --------------------------------------------------------------------------------


async def test_config_round_trip_through_postgres(
    pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig
) -> None:
    repo = PostgresConfigRepository(pg_pool)
    await repo.create_config(meeyland)
    assert await repo.get_config("meeyland") == meeyland


async def test_duplicate_config_is_rejected(
    pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig
) -> None:
    repo = PostgresConfigRepository(pg_pool)
    await repo.create_config(meeyland)
    with pytest.raises(ConfigAlreadyExistsError):
        await repo.create_config(meeyland)


async def test_missing_config(pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig) -> None:
    repo = PostgresConfigRepository(pg_pool)
    with pytest.raises(ConfigNotFoundError):
        await repo.get_config("nope")
    with pytest.raises(ConfigNotFoundError):
        await repo.update_config("meeyland", meeyland)
    with pytest.raises(ConfigNotFoundError):
        await repo.delete_config("nope")
    with pytest.raises(ConfigNotFoundError):
        await repo.update_last_run("nope")


async def test_update_and_enabled_filter(
    pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig, mogi: CrawlerConfig
) -> None:
    repo = PostgresConfigRepository(pg_pool)
    await repo.create_config(meeyland)
    await repo.create_config(mogi)
    assert [c.site_id for c in await repo.get_enabled_configs()] == ["meeyland", "mogi"]

    await repo.update_config("mogi", mogi.model_copy(update={"enabled": False}))
    assert [c.site_id for c in await repo.get_enabled_configs()] == ["meeyland"]
    assert (await repo.get_config("mogi")).enabled is False


async def test_update_last_run_sets_the_timestamp(
    pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig
) -> None:
    repo = PostgresConfigRepository(pg_pool)
    await repo.create_config(meeyland)
    await repo.update_last_run("meeyland")
    async with pg_pool.connection() as conn:
        cur = await conn.execute("SELECT last_run_at FROM crawler_configs")
        row = await cur.fetchone()
    assert row is not None and row[0] is not None


async def test_statement_timeout_is_local_to_the_transaction(
    pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig
) -> None:
    """A repository call must not leave statement_timeout set on the pooled connection."""
    repo = PostgresConfigRepository(pg_pool, query_timeout=1.5)
    await repo.create_config(meeyland)
    async with pg_pool.connection() as conn:
        cur = await conn.execute("SHOW statement_timeout")
        row = await cur.fetchone()
    assert row == ("0",)


async def test_database_rejects_a_config_without_schedule(pg_pool: AsyncConnectionPool) -> None:
    async with pg_pool.connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation, match="chk_has_schedule"):
            await conn.execute(
                "INSERT INTO crawler_configs (site_id, name, config_json) VALUES ('x', 'X', '{}')"
            )


# --- crawl runs -----------------------------------------------------------------------------


@pytest.fixture
async def runs(pg_pool: AsyncConnectionPool, meeyland: CrawlerConfig) -> PostgresCrawlRunRepository:
    await PostgresConfigRepository(pg_pool).create_config(meeyland)
    return PostgresCrawlRunRepository(pg_pool)


async def test_run_lifecycle(
    runs: PostgresCrawlRunRepository, pg_pool: AsyncConnectionPool
) -> None:
    created = await runs.create_run("r1", "meeyland", RunMode.FULL_SWEEP)
    assert created["status"] == "running" and created["run_mode"] == "full_sweep"

    await runs.update_metrics("r1", items_scraped=20, pages_crawled=2)
    await runs.update_metrics("r1", items_scraped=10, pages_crawled=1)  # pages never go back
    await runs.complete_run("r1", CrawlRunStatus.COMPLETED)

    async with pg_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM crawl_runs WHERE crawl_run_id = 'r1'")
        row = await cur.fetchone()
    assert row is not None
    assert (row["items_scraped"], row["pages_crawled"], row["status"]) == (30, 2, "completed")
    assert row["finished_at"] is not None


async def test_a_feed_cannot_have_two_running_runs(runs: PostgresCrawlRunRepository) -> None:
    await runs.create_run("r1", "meeyland")
    with pytest.raises(psycopg.errors.UniqueViolation):
        await runs.create_run("r2", "meeyland")
    await runs.complete_run("r1")
    await runs.create_run("r2", "meeyland")  # free again once the first one finished


async def test_stale_and_interrupted_runs_are_failed(
    runs: PostgresCrawlRunRepository, pg_pool: AsyncConnectionPool
) -> None:
    await runs.create_run("old", "meeyland")
    async with pg_pool.connection() as conn:
        await conn.execute(
            "UPDATE crawl_runs SET started_at = NOW() - INTERVAL '2 hours' WHERE crawl_run_id = 'old'"
        )

    assert await runs.abort_stale_runs("meeyland", max_age_minutes=60) == 1
    assert await runs.abort_stale_runs("meeyland", max_age_minutes=60) == 0  # nothing left

    await runs.create_run("fresh", "meeyland")
    assert await runs.fail_interrupted_runs(max_age_minutes=60) == 0  # too young to be stale
    assert await runs.fail_interrupted_runs(max_age_minutes=0) == 1  # a restart fails everything
