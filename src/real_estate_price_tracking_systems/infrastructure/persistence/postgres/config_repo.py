"""PostgreSQL implementation of :class:`ConfigRepository`."""

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncCursor
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from real_estate_price_tracking_systems.application.ports import ConfigRepository
from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.domain.exceptions import (
    ConfigAlreadyExistsError,
    ConfigNotFoundError,
)
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
    COLUMN_FIELDS,
    config_to_row,
    row_to_config,
)

_SELECT_COLUMNS = (*COLUMN_FIELDS, "config_json")
_WRITE_COLUMNS = tuple(c for c in _SELECT_COLUMNS if c != "site_id")
_COLS = ", ".join(_SELECT_COLUMNS)

_GET = f"SELECT {_COLS} FROM crawler_configs WHERE site_id = %s"
_GET_ENABLED = f"SELECT {_COLS} FROM crawler_configs WHERE enabled ORDER BY site_id"
_INSERT = (
    f"INSERT INTO crawler_configs ({_COLS}) "
    f"VALUES ({', '.join(['%s'] * len(_SELECT_COLUMNS))}) ON CONFLICT (site_id) DO NOTHING"
)
_UPDATE = (
    f"UPDATE crawler_configs SET {', '.join(f'{c} = %s' for c in _WRITE_COLUMNS)}, "
    "updated_at = NOW() WHERE site_id = %s"
)
_DELETE = "DELETE FROM crawler_configs WHERE site_id = %s"
_TOUCH_LAST_RUN = "UPDATE crawler_configs SET last_run_at = NOW(), updated_at = NOW() WHERE site_id = %s"  # fmt: skip


class PostgresConfigRepository(ConfigRepository):
    """Crawler configurations in ``crawler_configs``.

    Every statement runs in its own transaction with ``statement_timeout`` set locally, so a
    stuck query frees its connection instead of blocking the scheduler.
    """

    def __init__(self, pool: AsyncConnectionPool, query_timeout: float = 5.0) -> None:
        if (
            isinstance(query_timeout, bool)
            or not math.isfinite(query_timeout)
            or query_timeout <= 0
        ):
            raise ValueError("Query timeout must be a finite positive number.")
        self._pool = pool
        self._timeout_ms = str(max(1, math.ceil(query_timeout * 1000)))

    @asynccontextmanager
    async def _cursor(self) -> AsyncIterator[AsyncCursor[dict[str, Any]]]:
        async with self._pool.connection() as conn, conn.transaction():
            # is_local=true: the timeout ends with the transaction and never leaks to the pool.
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)", (self._timeout_ms,)
            )
            async with conn.cursor(row_factory=dict_row) as cur:
                yield cur

    @staticmethod
    def _values(config: CrawlerConfig, columns: tuple[str, ...]) -> list[Any]:
        row = config_to_row(config)
        return [Jsonb(row[c]) if c == "config_json" else row[c] for c in columns]

    @staticmethod
    def _not_found(site_id: str) -> ConfigNotFoundError:
        return ConfigNotFoundError(f"Config with site_id '{site_id}' not found.")

    async def get_config(self, site_id: str) -> CrawlerConfig:
        async with self._cursor() as cur:
            await cur.execute(_GET, (site_id,))
            row = await cur.fetchone()
        if row is None:
            raise self._not_found(site_id)
        return row_to_config(row)

    async def get_enabled_configs(self) -> list[CrawlerConfig]:
        async with self._cursor() as cur:
            await cur.execute(_GET_ENABLED)
            rows = await cur.fetchall()
        return [row_to_config(row) for row in rows]

    async def create_config(self, config: CrawlerConfig) -> None:
        async with self._cursor() as cur:
            await cur.execute(_INSERT, self._values(config, _SELECT_COLUMNS))
            inserted = cur.rowcount
        if inserted == 0:
            raise ConfigAlreadyExistsError(
                f"Config with site_id '{config.site_id}' already exists."
            )

    async def update_config(self, site_id: str, config: CrawlerConfig) -> None:
        if config.site_id != site_id:
            raise ValueError("Config site_id does not match the requested site_id.")
        async with self._cursor() as cur:
            await cur.execute(_UPDATE, [*self._values(config, _WRITE_COLUMNS), site_id])
            updated = cur.rowcount
        if updated == 0:
            raise self._not_found(site_id)

    async def delete_config(self, site_id: str) -> None:
        async with self._cursor() as cur:
            await cur.execute(_DELETE, (site_id,))
            deleted = cur.rowcount
        if deleted == 0:
            raise self._not_found(site_id)

    async def update_last_run(self, site_id: str) -> None:
        async with self._cursor() as cur:
            await cur.execute(_TOUCH_LAST_RUN, (site_id,))
            updated = cur.rowcount
        if updated == 0:
            raise self._not_found(site_id)
