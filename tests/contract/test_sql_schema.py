"""sql/init.sql is generated from migrations/, and docker compose must actually use it."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = ROOT / "sql" / "init.sql"
COMPOSE = ROOT / "docker" / "docker-compose.yml"


def test_init_sql_is_generated_from_migrations() -> None:
    """Migrations are the only schema source; init.sql must be their rendered output."""
    result = subprocess.run(
        [sys.executable, "scripts/generate_init_sql.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_init_sql_creates_the_expected_schema() -> None:
    sql = INIT_SQL.read_text(encoding="utf-8").lower()
    tables = set(re.findall(r"create table (\w+)", sql))
    assert {
        "crawler_configs",
        "crawl_runs",
        "advertisers",
        "listings",
        "listing_details",
        "listing_feeds",
        "listing_price_history",
    } <= tables
    assert "partition by range (recorded_at)" in sql
    assert "function ensure_price_history_partitions" in sql
    assert "create materialized view mv_ward_avg_price_per_m2" in sql
    assert "create materialized view mv_steep_price_drops_7d" in sql


def test_schema_needs_postgis_image() -> None:
    """init.sql enables PostGIS, so compose must run an image that ships it."""
    assert "create extension if not exists postgis" in INIT_SQL.read_text(encoding="utf-8").lower()
    assert re.search(r"image:\s*postgis/postgis", COMPOSE.read_text(encoding="utf-8"))


def test_compose_mounts_init_sql() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "../sql/init.sql:/docker-entrypoint-initdb.d/01_init.sql:ro" in compose
