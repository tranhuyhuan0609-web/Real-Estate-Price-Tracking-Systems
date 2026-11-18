import json
from pathlib import Path
from typing import Any

import pytest

from real_estate_price_tracking_systems.infrastructure.config import load_site_config
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
    config_to_row,
)

ROOT = Path(__file__).resolve().parents[3]
SITES_DIR = ROOT / "configs" / "sites"
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON (``*.json``) or text sample from tests/fixtures."""
    path = FIXTURES_DIR / name
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else text


@pytest.fixture
def seed_row() -> dict[str, Any]:
    """A crawler_configs row built from configs/sites/meeyland.yaml, with a pinned schedule."""
    row = config_to_row(load_site_config(SITES_DIR / "meeyland.yaml"))
    row["schedule_times"] = []
    row["interval_seconds"] = 300
    return row
