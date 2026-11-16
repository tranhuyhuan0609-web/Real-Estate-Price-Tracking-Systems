import copy
import json
from typing import Any

import pytest

from real_estate_price_tracking_systems.domain.exceptions import ConfigCorruptedError
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
    COLUMN_FIELDS,
    config_to_row,
    row_to_config,
)

Row = dict[str, Any]


def test_row_to_config(seed_row: Row) -> None:
    config = row_to_config(seed_row)
    assert config.site_id == "meeyland"
    assert config.crawler_type == "rest_api"


def test_null_schedule_times_become_empty_list(seed_row: Row) -> None:
    seed_row["schedule_times"] = None
    seed_row["interval_seconds"] = 300  # a config still needs a schedule or an interval
    assert row_to_config(seed_row).schedule_times == []


def test_round_trip_keeps_columns_out_of_json(seed_row: Row) -> None:
    config = row_to_config(seed_row)
    row = config_to_row(config)
    assert set(COLUMN_FIELDS) <= row.keys()
    assert not set(COLUMN_FIELDS) & row["config_json"].keys()
    json.dumps(row["config_json"])  # must be JSON-serializable
    assert row_to_config(row) == config


def test_json_repeating_a_column_must_agree(seed_row: Row) -> None:
    seed_row["config_json"]["name"] = seed_row["name"]
    row_to_config(seed_row)

    seed_row["config_json"]["name"] = "Something else"
    with pytest.raises(ConfigCorruptedError, match="'name'"):
        row_to_config(seed_row)


def test_invalid_config_json_is_corrupted(seed_row: Row) -> None:
    row = copy.deepcopy(seed_row)
    del row["config_json"]["response_mapping"]
    with pytest.raises(ConfigCorruptedError, match="meeyland"):
        row_to_config(row)


def test_non_object_config_json_is_corrupted(seed_row: Row) -> None:
    seed_row["config_json"] = []
    with pytest.raises(ConfigCorruptedError, match="must be an object"):
        row_to_config(seed_row)
