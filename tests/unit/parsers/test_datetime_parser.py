"""Vietnamese date and time parsing. Results are UTC; naive input is Asia/Ho_Chi_Minh (UTC+7)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.datetime_parser import (
    parse_vietnamese_datetime,
)

NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)  # 17:00 in Vietnam


def parse(raw: object) -> datetime | None:
    return parse_vietnamese_datetime(raw, now=NOW)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5 giây trước", utc(2026, 11, 4, 9, 59, 55)),
        ("30 phút trước", utc(2026, 11, 4, 9, 30)),
        ("2 giờ trước", utc(2026, 11, 4, 8, 0)),
        ("3 ngày trước", utc(2026, 11, 1, 10, 0)),
        ("hôm nay", utc(2026, 11, 4, 10, 0)),
        ("hôm qua 14:30", utc(2026, 11, 3, 7, 30)),  # 14:30 in Vietnam
        ("Hôm Nay 08:00", utc(2026, 11, 4, 1, 0)),
    ],
)
def test_relative_dates(raw: str, expected: datetime) -> None:
    assert parse(raw) == expected


def test_bogus_clock_keeps_the_day() -> None:
    assert parse("hôm nay 25:99") == utc(2026, 11, 4, 10, 0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("04/11/2026", utc(2026, 11, 3, 17, 0)),  # midnight in Vietnam
        ("04-11-2026", utc(2026, 11, 3, 17, 0)),
        ("04/11/2026 08:30", utc(2026, 11, 4, 1, 30)),
        ("04/11/2026 08:30:15", utc(2026, 11, 4, 1, 30, 15)),
        ("2026-11-04T10:00:00Z", utc(2026, 11, 4, 10, 0)),
        ("2026-11-04T10:00:00+07:00", utc(2026, 11, 4, 3, 0)),
        ("2026-11-04 10:00", utc(2026, 11, 4, 3, 0)),
    ],
)
def test_absolute_dates(raw: str, expected: datetime) -> None:
    assert parse(raw) == expected


@pytest.mark.parametrize(
    "raw", ["1762250000", "1762250000000", 1762250000, 1762250000000, 1762250000.0]
)
def test_epoch_seconds_and_milliseconds_agree(raw: object) -> None:
    assert parse(raw) == utc(2025, 11, 4, 9, 53, 20)


def test_datetime_objects_are_converted_to_utc() -> None:
    assert parse(datetime(2026, 11, 4, 17, 0)) == utc(2026, 11, 4, 10, 0)  # naive: Vietnam time
    aware = datetime(2026, 11, 4, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert parse(aware) == utc(2026, 11, 4, 1, 0)


def test_default_timezone_is_configurable() -> None:
    assert parse_vietnamese_datetime("04/11/2026", default_tz=UTC) == utc(2026, 11, 4, 0, 0)


@pytest.mark.parametrize("raw", ["abc", "", None, "31/02/2026", "99/99/2026", 0])
def test_unparseable_is_none(raw: object) -> None:
    assert parse(raw) is None


def test_result_is_always_timezone_aware_utc() -> None:
    for raw in ("2 giờ trước", "04/11/2026", "2026-11-04 10:00", 1762250000):
        result = parse(raw)
        assert result is not None and result.utcoffset() == UTC.utcoffset(None)
