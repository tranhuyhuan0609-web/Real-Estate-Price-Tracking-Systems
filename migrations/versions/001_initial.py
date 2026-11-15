"""Initial schema: Silver tables.

* ``crawler_configs``: one row per feed, synced from ``configs/sites/*.yaml``.
* ``crawl_runs``: one row per spider execution, at most one running per feed.
* ``advertisers``, ``listings``, ``listing_details``: the current state of every listing.
  ``listings.source`` is the *portal* (``CrawlerConfig.portal_id``), not necessarily a feed, so
  it has no foreign key to ``crawler_configs``.
* ``listing_feeds``: which feeds have seen a listing, so lifecycle runs per feed while several
  feeds of one portal share a listing.
* ``listing_price_history``: one row per observed price change (Gold).

CHECK constraints mirror the domain enums and ``crawler_config.ENUM_VALUES``.

Revision ID: 001_initial
Revises:
Create Date: 2026-11-15 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRAWLER_CONFIGS = """
CREATE TABLE crawler_configs (
    site_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    crawler_type TEXT NOT NULL DEFAULT 'rest_api',
    schedule_times TEXT[] NOT NULL DEFAULT '{}',
    interval_seconds INT,
    config_json JSONB NOT NULL,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crawler_type CHECK (crawler_type IN ('rest_api', 'html')),
    CONSTRAINT chk_interval_min CHECK (interval_seconds IS NULL OR interval_seconds >= 60),
    CONSTRAINT chk_has_schedule CHECK (interval_seconds IS NOT NULL OR cardinality(schedule_times) > 0),
    CONSTRAINT chk_config_is_object CHECK (jsonb_typeof(config_json) = 'object')
);
"""

CRAWL_RUNS = """
CREATE TABLE crawl_runs (
    crawl_run_id TEXT PRIMARY KEY,
    site_id VARCHAR(20) NOT NULL REFERENCES crawler_configs(site_id) ON DELETE CASCADE,
    run_mode VARCHAR(20) NOT NULL DEFAULT 'incremental',
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    pages_crawled INT NOT NULL DEFAULT 0,
    items_scraped INT NOT NULL DEFAULT 0,
    items_processed INT NOT NULL DEFAULT 0,
    new_listings_count INT NOT NULL DEFAULT 0,
    price_changes_detected INT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    lifecycle_applied_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT chk_run_mode CHECK (run_mode IN ('incremental', 'full_sweep')),
    CONSTRAINT chk_status CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT chk_time_order CHECK (finished_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX idx_crawl_runs_site_history ON crawl_runs(site_id, started_at DESC);
-- A second scheduler instance cannot start the same feed twice.
CREATE UNIQUE INDEX uq_crawl_runs_one_running_per_site ON crawl_runs(site_id) WHERE status = 'running';
"""

ADVERTISERS = """
CREATE TABLE advertisers (
    advertiser_id VARCHAR(64) PRIMARY KEY,
    phone VARCHAR(20),
    name VARCHAR(100),
    email VARCHAR(100),
    kind VARCHAR(15) NOT NULL DEFAULT 'unknown',
    is_verified BOOLEAN NOT NULL DEFAULT false,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_advertiser_kind CHECK (kind IN ('broker', 'owner', 'unknown'))
);
CREATE INDEX idx_advertisers_phone ON advertisers(phone) WHERE phone IS NOT NULL;
"""

LISTINGS = """
CREATE TABLE listings (
    listing_key TEXT PRIMARY KEY,
    property_fingerprint TEXT,
    source VARCHAR(20) NOT NULL,
    external_id TEXT,
    advertiser_id VARCHAR(64) REFERENCES advertisers(advertiser_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    missing_count INT NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    category VARCHAR(20) NOT NULL,
    property_type VARCHAR(20) NOT NULL DEFAULT 'other',
    area_m2 NUMERIC(10, 2),
    facade_m NUMERIC(6, 2),
    depth_m NUMERIC(6, 2),
    current_price_vnd NUMERIC(18, 0),
    current_price_per_m2 NUMERIC(14, 0),
    -- 'unchanged' is never stored: an unchanged price leaves the previous status in place.
    price_status VARCHAR(20) NOT NULL DEFAULT 'initial',
    price_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_listing_status CHECK (status IN ('active', 'expired', 'hidden')),
    CONSTRAINT chk_category CHECK (category IN ('sale', 'rent', 'project')),
    CONSTRAINT chk_property_type CHECK (property_type IN ('land', 'house', 'apartment', 'villa', 'shophouse', 'commercial', 'other')),
    CONSTRAINT chk_price_status CHECK (price_status IN ('initial', 'increased', 'decreased', 'contact')),
    CONSTRAINT chk_missing_count_non_negative CHECK (missing_count >= 0),
    CONSTRAINT chk_positive_dimensions CHECK (
        (area_m2 IS NULL OR area_m2 > 0) AND
        (facade_m IS NULL OR facade_m > 0) AND
        (depth_m IS NULL OR depth_m > 0)
    ),
    CONSTRAINT chk_non_negative_price CHECK (
        (current_price_vnd IS NULL OR current_price_vnd >= 0) AND
        (current_price_per_m2 IS NULL OR current_price_per_m2 >= 0)
    ),
    CONSTRAINT chk_listing_time_order CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX idx_listings_active_filter ON listings(category, property_type, current_price_per_m2) WHERE status = 'active';
CREATE INDEX idx_listings_price_changed ON listings(price_changed_at DESC);
CREATE INDEX idx_listings_source_last_seen ON listings(source, last_seen_at) WHERE status = 'active';
CREATE INDEX idx_listings_advertiser ON listings(advertiser_id);
CREATE INDEX idx_listings_fingerprint ON listings(property_fingerprint);
"""

LISTING_DETAILS = """
CREATE TABLE listing_details (
    listing_key TEXT PRIMARY KEY REFERENCES listings(listing_key) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    city_name TEXT,
    district_name TEXT,
    ward_name TEXT,
    lng DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    legal_status VARCHAR(50),
    thumbnail_url TEXT,
    media_list JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_listing_details_geom ON listing_details USING GIST(geom);
CREATE INDEX idx_listing_details_location ON listing_details(city_name, district_name, ward_name);
"""

LISTING_FEEDS = """
CREATE TABLE listing_feeds (
    listing_key TEXT NOT NULL REFERENCES listings(listing_key) ON DELETE CASCADE,
    site_id VARCHAR(20) NOT NULL REFERENCES crawler_configs(site_id) ON DELETE CASCADE,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (listing_key, site_id),
    CONSTRAINT chk_feed_time_order CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX idx_listing_feeds_site ON listing_feeds(site_id, listing_key);
"""

PRICE_HISTORY = """
CREATE TABLE listing_price_history (
    history_id BIGSERIAL PRIMARY KEY,
    listing_key TEXT NOT NULL REFERENCES listings(listing_key) ON DELETE CASCADE,
    crawl_run_id TEXT REFERENCES crawl_runs(crawl_run_id) ON DELETE SET NULL,
    price_vnd NUMERIC(18, 0) NOT NULL,
    price_per_m2 NUMERIC(14, 0),
    price_diff_vnd NUMERIC(18, 0) NOT NULL DEFAULT 0,
    price_diff_percent NUMERIC(12, 2) NOT NULL DEFAULT 0,
    price_status VARCHAR(20) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_history_price_positive CHECK (price_vnd > 0 AND (price_per_m2 IS NULL OR price_per_m2 > 0)),
    CONSTRAINT chk_history_status CHECK (price_status IN ('initial', 'increased', 'decreased')),
    CONSTRAINT chk_price_diff_logic CHECK (
        (price_status = 'initial' AND price_diff_vnd = 0) OR
        (price_status = 'increased' AND price_diff_vnd > 0) OR
        (price_status = 'decreased' AND price_diff_vnd < 0)
    )
);
CREATE INDEX idx_price_history_listing_timeline ON listing_price_history(listing_key, recorded_at DESC);
CREATE INDEX idx_price_history_recorded_at ON listing_price_history(recorded_at DESC);
"""

TABLES = ("listing_price_history", "listing_feeds", "listing_details", "listings", "advertisers", "crawl_runs", "crawler_configs")  # fmt: skip


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    for ddl in (CRAWLER_CONFIGS, CRAWL_RUNS, ADVERTISERS, LISTINGS, LISTING_DETAILS, LISTING_FEEDS, PRICE_HISTORY):  # fmt: skip
        op.execute(ddl)


def downgrade() -> None:
    for table in TABLES:  # dependents first
        op.execute(f"DROP TABLE IF EXISTS {table};")
