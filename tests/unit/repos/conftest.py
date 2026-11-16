from pathlib import Path
from typing import Any

import pytest

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.infrastructure.config import load_site_config
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
    config_to_row,
)

SITES = Path(__file__).resolve().parents[3] / "configs" / "sites"


@pytest.fixture
def config() -> CrawlerConfig:
    return load_site_config(SITES / "meeyland.yaml")


@pytest.fixture
def seed_row(config: CrawlerConfig) -> dict[str, Any]:
    """A crawler_configs row as psycopg's dict_row returns it."""
    return config_to_row(config)
