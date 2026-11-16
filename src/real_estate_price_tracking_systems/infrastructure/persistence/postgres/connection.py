"""Async connection pool for PostgreSQL."""

from psycopg_pool import AsyncConnectionPool


def create_pg_pool(
    dsn: str, *, min_size: int = 2, max_size: int = 10, timeout: float = 30.0
) -> AsyncConnectionPool:
    """Build a pool that is **not yet open**.

    Open it from the running event loop (``await pool.open()``) and close it on shutdown.
    Opening in the constructor is deprecated by psycopg_pool, and doing it at import time would
    bind connections to the wrong loop. ``timeout`` is how long a caller waits for a free
    connection before ``PoolTimeout``.
    """
    if min_size < 0 or max_size < max(min_size, 1):
        raise ValueError("Pool sizes must satisfy 0 <= min_size <= max_size and max_size >= 1.")
    if timeout <= 0:
        raise ValueError("Pool timeout must be positive.")
    return AsyncConnectionPool(
        conninfo=dsn, min_size=min_size, max_size=max_size, timeout=timeout, open=False
    )
