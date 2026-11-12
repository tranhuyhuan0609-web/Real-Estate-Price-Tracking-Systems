"""Validation rules of CrawlerConfig, starting from a valid JSON-API config and breaking one thing."""

import copy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from real_estate_price_tracking_systems.domain.entities import (
    CrawlerConfig,
    ProxySettings,
    RunMode,
)

Data = dict[str, Any]


@pytest.fixture
def data() -> Data:
    return {
        "site_id": "meeyland",
        "name": "Meeyland",
        "schedule_times": ["05:00", "17:00"],
        "request": {
            "url": "https://api5.meeyland.com/v1/articles/search",
            "method": "POST",
            "body_template": {"sort": 2},
        },
        "pagination": {
            "param_location": "body",
            "max_pages_incremental": 10,
            "max_pages_full_sweep": 1000,
            "stop_when_empty_path": "data.results",
        },
        "response_mapping": {
            "items_path": "data.results",
            "fields": {
                "external_id": "_id",
                "external_code": "code",
                "url": "url",
                "title": "title",
                "category": "category.value",
                "district_name": "oldDistrict.translation[0].name",
            },
            "value_mappings": {"category": {"mua_ban": "sale", "_default": "sale"}},
        },
    }


def make(data: Data, **changes: Any) -> CrawlerConfig:
    return CrawlerConfig.model_validate({**copy.deepcopy(data), **changes})


def broken(data: Data, match: str, **changes: Any) -> None:
    with pytest.raises(ValidationError, match=match):
        make(data, **changes)


def test_valid_config_and_defaults(data: Data) -> None:
    config = make(data)
    assert config.portal_id == "meeyland"
    assert config.rate_limit.download_delay_sec == 1.0
    assert (config.source_timezone, config.content_timezone) == ("UTC", "Asia/Ho_Chi_Minh")
    assert config.response_mapping.fields["district_name"] == "oldDistrict.translation[0].name"


# --- identity -------------------------------------------------------------------------------


@pytest.mark.parametrize("site_id", ["", "Mee yland", "a" * 21, "mee.yland"])
def test_bad_site_id(data: Data, site_id: str) -> None:
    broken(data, "site_id", site_id=site_id)


def test_site_id_is_lowercased(data: Data) -> None:
    assert make(data, site_id=" MeeyLand ").site_id == "meeyland"


def test_portal_shares_the_listing_id_space(data: Data) -> None:
    config = make(data, site_id="meeyland_rent", portal="MeeyLand")
    assert (config.site_id, config.portal, config.portal_id) == (
        "meeyland_rent",
        "meeyland",
        "meeyland",
    )


def test_portal_follows_site_id_format(data: Data) -> None:
    broken(data, "portal", portal="mee yland")


def test_name_limited_to_100_chars(data: Data) -> None:
    broken(data, "name", name="x" * 101)


def test_unknown_top_level_key_rejected(data: Data) -> None:
    broken(data, "selectors", selectors={"item": "div"})


# --- schedule and timezones -----------------------------------------------------------------


def test_needs_schedule_or_interval(data: Data) -> None:
    broken(data, "interval_seconds", schedule_times=[])
    assert make(data, schedule_times=[], interval_seconds=300).interval_seconds == 300


def test_interval_at_least_a_minute(data: Data) -> None:
    broken(data, "interval_seconds", interval_seconds=59)


def test_schedule_times_normalized_and_sorted(data: Data) -> None:
    assert make(data, schedule_times=["8:05", "07:00"]).schedule_times == ["07:00", "08:05"]


@pytest.mark.parametrize("times", [["24:00"], ["7"], ["07:60"], ["07:00", "7:00"]])
def test_bad_schedule_times(data: Data, times: list[str]) -> None:
    broken(data, "schedule", schedule_times=times)


@pytest.mark.parametrize("field", ["source_timezone", "content_timezone"])
def test_bad_timezone(data: Data, field: str) -> None:
    broken(data, "Invalid timezone", **{field: "Mars/Olympus"})


def test_latest_scheduled_slot_uses_source_timezone(data: Data) -> None:
    config = make(data, schedule_times=["08:00"], source_timezone="Asia/Ho_Chi_Minh")
    ten_am_vn = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
    assert config.latest_scheduled_slot(ten_am_vn) == datetime(2026, 10, 30, 1, 0, tzinfo=UTC)
    seven_am_vn = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)  # before today's slot: yesterday's
    assert config.latest_scheduled_slot(seven_am_vn) == datetime(2026, 10, 29, 1, 0, tzinfo=UTC)


def test_content_timezone_does_not_move_schedule(data: Data) -> None:
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert make(data, content_timezone="UTC").latest_scheduled_slot(now) == make(
        data, content_timezone="Asia/Tokyo"
    ).latest_scheduled_slot(now)


def test_latest_scheduled_slot_needs_aware_now_and_schedule(data: Data) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make(data).latest_scheduled_slot(datetime(2026, 10, 30, 3, 0))
    interval_only = make(data, schedule_times=[], interval_seconds=300)
    assert interval_only.latest_scheduled_slot(datetime.now(UTC)) is None


# --- request and pagination -----------------------------------------------------------------


def test_page_budget_per_run_mode(data: Data) -> None:
    config = make(data)
    assert config.max_pages(RunMode.INCREMENTAL) == config.max_pages("incremental") == 10
    assert config.max_pages(RunMode.FULL_SWEEP) == 1000
    with pytest.raises(ValueError, match="run_mode"):
        config.max_pages("weekly")


def test_full_sweep_budget_not_below_incremental(data: Data) -> None:
    data["pagination"]["max_pages_full_sweep"] = 5
    broken(data, "max_pages_full_sweep")


def test_body_paging_requires_post(data: Data) -> None:
    data["request"] = {"url": data["request"]["url"], "method": "GET"}
    broken(data, "requires method='POST'")


def test_body_template_requires_post(data: Data) -> None:
    data["request"]["method"] = "GET"
    data["pagination"]["param_location"] = "query"
    broken(data, "body_template")


def test_stop_path_defaults_to_items_path(data: Data) -> None:
    del data["pagination"]["stop_when_empty_path"]
    assert make(data).items_stop_path == "data.results"


# --- response mapping -----------------------------------------------------------------------


def test_unknown_mapped_field_rejected(data: Data) -> None:
    data["response_mapping"]["fields"]["pricevnd"] = "totalPrice"  # typo of price_vnd
    broken(data, "Unknown mapped fields")


@pytest.mark.parametrize("missing", ["url", "title"])
def test_required_mapped_fields(data: Data, missing: str) -> None:
    del data["response_mapping"]["fields"][missing]
    broken(data, "required mapped fields")


def test_needs_code_or_id_and_one_is_enough(data: Data) -> None:
    del data["response_mapping"]["fields"]["external_code"]
    make(data)
    del data["response_mapping"]["fields"]["external_id"]
    broken(data, "external_code or external_id")


@pytest.mark.parametrize("path", ["a..b", "a[x]", "1abc", "a.b[0", ","])
def test_bad_json_path(data: Data, path: str) -> None:
    data["response_mapping"]["fields"]["title"] = path
    broken(data, "title|must not be empty")


def test_comma_separated_json_paths_are_fallbacks(data: Data) -> None:
    data["response_mapping"]["fields"]["title"] = "title, name.vi"
    make(data)


def test_html_sites_map_selectors_not_json_paths(data: Data) -> None:
    data["pagination"] = {}
    data["request"] = {"url": "https://mogi.vn/mua-nha-dat"}
    data["response_mapping"]["items_path"] = "ul.props > li"
    data["response_mapping"]["fields"]["title"] = "h2.prop-title::text"
    make(data, crawler_type="html")
    broken(data, "invalid path", crawler_type="rest_api")


def test_enum_value_mapping_checked_against_db_constraints(data: Data) -> None:
    data["response_mapping"]["value_mappings"]["category"]["mua_ban"] = "buy"
    broken(data, "allowed")


def test_value_mapping_needs_matching_field(data: Data) -> None:
    data["response_mapping"]["value_mappings"]["road_width_m"] = {"x": "y"}
    broken(data, "no matching entry")


def test_url_template(data: Data) -> None:
    data["response_mapping"]["url_template"] = "https://x.vn/{external_id}.htm"
    assert make(data).response_mapping.url_template == "https://x.vn/{external_id}.htm"
    for bad in ("https://x.vn/{title}", "https://x.vn/static", "/{external_id}.htm"):
        data["response_mapping"]["url_template"] = bad
        broken(data, "url_template")


def test_unknown_detail_page_field_rejected(data: Data) -> None:
    broken(data, "detail page", detail_page={"enabled": True, "fields": {"phone": "a::text"}})


# --- domains --------------------------------------------------------------------------------


def test_allowed_domains_derived_from_request_host(data: Data) -> None:
    config = make(data)
    assert config.effective_allowed_domains == ("api5.meeyland.com", "meeyland.com")
    assert config.is_allowed_domain("meeyland.com")
    assert config.is_allowed_domain("WWW.meeyland.com.")
    assert not config.is_allowed_domain("evil.example.com")
    assert not config.is_allowed_domain("notmeeyland.com")


def test_explicit_allowed_domains_win(data: Data) -> None:
    config = make(data, allowed_domains=["Example.COM."])
    assert config.effective_allowed_domains == ("example.com",)


@pytest.mark.parametrize("domains", [["https://x.com"], ["x.com/path"], ["x.com", "X.com"]])
def test_bad_allowed_domains(data: Data, domains: list[str]) -> None:
    broken(data, "allowed|hostname", allowed_domains=domains)


# --- proxies --------------------------------------------------------------------------------

PROXIES = ["http://user:secret@10.0.0.1:8080", "socks5://10.0.0.2:1080"]


def test_proxy_repr_hides_credentials() -> None:
    proxy = ProxySettings(enabled=True, rotation_enabled=True, proxies=PROXIES)
    assert "secret" not in repr(proxy) and "secret" not in str(proxy)
    assert "proxy_count=2" in repr(proxy)


@pytest.mark.parametrize(
    ("settings", "match"),
    [
        ({"rotation_enabled": True}, "requires enabled"),
        ({"enabled": True}, "At least one proxy"),
        ({"enabled": True, "rotation_enabled": True, "proxies": PROXIES[:1]}, "two proxies"),
        ({"proxies": PROXIES}, "must be empty"),
        ({"enabled": True, "proxies": ["ftp://10.0.0.1:21"]}, "allowed scheme"),
        ({"enabled": True, "proxies": ["http://10.0.0.1"]}, "port"),
        ({"enabled": True, "proxies": ["http://10.0.0.1:99999"]}, "Invalid proxy"),
        ({"enabled": True, "proxies": PROXIES[:1] * 2}, "Duplicate"),
    ],
)
def test_invalid_proxy_settings(settings: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        ProxySettings(**settings)
