"""Smoke tests: the throwaway containers start and the Postgres schema is what init.sql promises."""

from psycopg_pool import AsyncConnectionPool
from pymongo import MongoClient


async def test_postgis_has_the_schema(pg_pool: AsyncConnectionPool) -> None:
    async with pg_pool.connection() as conn:
        cur = await conn.execute("SELECT version_num FROM alembic_version")
        assert await cur.fetchone() == ("001_initial",)
        cur = await conn.execute("SELECT PostGIS_Version()")
        assert await cur.fetchone() is not None
        cur = await conn.execute("SELECT count(*) FROM pg_matviews")
        assert await cur.fetchone() == (2,)


def test_mongo_answers_ping(mongo_uri: str) -> None:
    with MongoClient(mongo_uri, serverSelectionTimeoutMS=10_000) as client:
        assert client.admin.command("ping")["ok"] == 1
