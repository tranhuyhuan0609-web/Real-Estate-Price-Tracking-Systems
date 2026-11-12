"""Declarative configuration of one crawl source (one YAML file in ``configs/sites/``).

Everything a spider needs to crawl a site is data: where the list endpoint is, how to page
through it, where each field lives in the response and which detail-page selectors enrich it.
Adding a site means adding a file, not code. Validation is strict so a typo fails loudly when the
config is loaded instead of silently extracting nothing in production.
"""

from __future__ import annotations

import re
import string
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, HttpUrl, field_validator, model_validator

from real_estate_price_tracking_systems.domain.entities.base import NonBlank, StrictBaseModel
from real_estate_price_tracking_systems.domain.entities.crawl_run import RunMode

# listings.source and crawl_runs.site_id are VARCHAR(20).
SITE_ID_RE = re.compile(r"[a-z0-9_-]{1,20}")
SCHEDULE_TIME_RE = re.compile(r"(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)")
HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
# Dotted path with optional list indexes: "oldDistrict.translation[0].name".
JSON_PATH_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*")
URL_TEMPLATE_FIELDS = frozenset({"external_id", "external_code"})
ALLOWED_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})

# Every name a response mapping may fill. Anything else is a typo.
MAPPABLE_FIELDS = frozenset(
    {
        "external_id", "external_code", "url", "title", "description",
        "price_vnd", "area_m2", "facade_m", "depth_m", "road_width_m",
        "category", "property_type", "published_at", "legal_status",
        "project_id", "project_name",
        "city_code", "city_name", "district_code", "district_name", "ward_code", "ward_name",
        "address", "breadcrumb", "lng", "lat",
        "thumbnail_url", "media_list",
        "advertiser_id", "advertiser_name", "advertiser_phone", "advertiser_email",
        "advertiser_kind", "advertiser_is_verified",
    }
)  # fmt: skip
REQUIRED_MAPPED_FIELDS = frozenset({"url", "title"})

# Mirror the CHECK constraints of the listings / advertisers tables.
ENUM_VALUES: dict[str, frozenset[str]] = {
    "category": frozenset({"sale", "rent", "project"}),
    "property_type": frozenset(
        {"land", "house", "apartment", "villa", "shophouse", "commercial", "other"}
    ),
    "advertiser_kind": frozenset({"broker", "owner", "unknown"}),
}


def normalize_host(host: str | None) -> str:
    """Lower-case a hostname and drop the trailing dot, for domain comparison."""
    if not host:
        raise ValueError("URL must have a hostname.")
    return host.lower().rstrip(".")


def _validate_json_path(value: str, name: str) -> str:
    """One or more comma-separated fallbacks, each a dotted path such as ``a.b[0].c``."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError(f"{name} must not be empty.")
    for part in parts:
        if not JSON_PATH_RE.fullmatch(part):
            raise ValueError(
                f"{name} {value!r} contains invalid path {part!r} (e.g. 'data.items' or 'a.b[0].c')."
            )
    return value


class RequestSettings(StrictBaseModel):
    """How to call the listing-search endpoint (or fetch the listing page)."""

    url: HttpUrl
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    body_template: dict[str, Any] | None = Field(
        default=None, description="Static JSON body merged with paging parameters (POST only)."
    )

    @model_validator(mode="after")
    def _body_needs_post(self) -> RequestSettings:
        if self.body_template is not None and self.method != "POST":
            raise ValueError("body_template is only allowed with method='POST'.")
        return self


class PaginationSettings(StrictBaseModel):
    """Page-number pagination with a separate page budget per run mode."""

    strategy: Literal["page_number", "offset_limit", "url_pattern"] = "page_number"
    param_location: Literal["query", "body"] = "query"
    page_param: NonBlank = "page"
    limit_param: NonBlank | None = "limit"
    start_page: int = Field(default=1, ge=0)
    page_size: int = Field(default=20, ge=1, le=500)
    max_pages_incremental: int = Field(default=10, ge=1)
    max_pages_full_sweep: int = Field(default=500, ge=1)
    stop_when_empty_path: NonBlank | None = Field(
        default=None,
        description="Path to the item list; stop when it is empty. "
        "Defaults to response_mapping.items_path.",
    )

    @model_validator(mode="after")
    def _sweep_covers_incremental(self) -> PaginationSettings:
        if self.max_pages_full_sweep < self.max_pages_incremental:
            raise ValueError("max_pages_full_sweep must be >= max_pages_incremental.")
        return self


class RateLimitSettings(StrictBaseModel):
    """Politeness and resilience of the HTTP client."""

    download_delay_sec: float = Field(default=1.0, gt=0.0)
    concurrent_requests: int = Field(default=1, ge=1, le=10)
    timeout_sec: float = Field(default=30.0, gt=0.0, le=300.0)
    retry_times: int = Field(default=3, ge=0, le=10)


class ResponseMapping(StrictBaseModel):
    """Where each listing field lives in the response.

    ``value_mappings[field]`` translates source values to stored values. A source value with no
    entry uses ``_default`` when present; otherwise the listing is rejected instead of being
    stored with a guessed value.
    """

    items_path: NonBlank
    fields: dict[str, str]
    value_mappings: dict[str, dict[str, str]] = Field(default_factory=dict)
    url_template: str | None = Field(
        default=None,
        description="Listing URL built when the item has no URL field, e.g. "
        "'https://www.nhatot.com/{external_id}.htm'. Placeholders: "
        + ", ".join(sorted(URL_TEMPLATE_FIELDS))
        + ".",
    )

    @field_validator("url_template")
    @classmethod
    def _check_url_template(cls, value: str | None) -> str | None:
        if value is None:
            return None
        names = {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
        if not names or not names <= URL_TEMPLATE_FIELDS:
            raise ValueError(
                f"url_template must use at least one of {sorted(URL_TEMPLATE_FIELDS)} "
                "and nothing else."
            )
        if urlsplit(value.format(**dict.fromkeys(names, "1"))).scheme not in {"http", "https"}:
            raise ValueError("url_template must be an absolute http(s) URL.")
        return value

    @model_validator(mode="after")
    def _check_mapping(self) -> ResponseMapping:
        unknown = self.fields.keys() - MAPPABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown mapped fields: {sorted(unknown)}.")
        missing = REQUIRED_MAPPED_FIELDS - self.fields.keys()
        if missing:
            raise ValueError(f"Missing required mapped fields: {sorted(missing)}.")
        if not ({"external_code", "external_id"} & self.fields.keys()):
            raise ValueError(
                "Map at least one of external_code or external_id (needed to build listing_key)."
            )
        for name, mapping in self.value_mappings.items():
            if name not in self.fields:
                raise ValueError(f"value_mappings[{name!r}] has no matching entry in fields.")
            allowed = ENUM_VALUES.get(name)
            invalid = {v for v in mapping.values() if allowed is not None and v not in allowed}
            if invalid:
                raise ValueError(
                    f"value_mappings[{name!r}] has values {sorted(invalid)}; "
                    f"allowed: {sorted(allowed or ())}."
                )
        return self


class ProxySettings(StrictBaseModel):
    """Outgoing proxies, optionally rotated. ``repr`` never shows the URLs (they hold passwords)."""

    enabled: bool = False
    rotation_enabled: bool = False
    proxies: list[str] = Field(default_factory=list)
    max_failures: int = Field(default=3, ge=1)
    cooldown_seconds: int = Field(default=60, ge=1)

    @field_validator("proxies")
    @classmethod
    def _check_proxies(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            value = raw.strip()
            try:
                parts = urlsplit(value)
                scheme, hostname, port = parts.scheme.lower(), parts.hostname, parts.port
            except ValueError:
                raise ValueError("Invalid proxy URL.") from None
            if scheme not in ALLOWED_PROXY_SCHEMES or not hostname or port is None:
                raise ValueError(
                    "Proxy URL must include an allowed scheme "
                    f"({', '.join(sorted(ALLOWED_PROXY_SCHEMES))}), a hostname and a port."
                )
            normalized.append(value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate proxy URLs are not allowed.")
        return normalized

    @model_validator(mode="after")
    def _check_consistency(self) -> ProxySettings:
        if self.rotation_enabled and not self.enabled:
            raise ValueError("Proxy rotation requires enabled=True.")
        if self.enabled and not self.proxies:
            raise ValueError("At least one proxy is required when proxy is enabled.")
        if self.rotation_enabled and len(self.proxies) < 2:
            raise ValueError("Proxy rotation requires at least two proxies.")
        if not self.enabled and self.proxies:
            raise ValueError("Proxy URLs must be empty when proxy is disabled.")
        return self

    def __repr__(self) -> str:
        return (
            f"ProxySettings(enabled={self.enabled}, rotation_enabled={self.rotation_enabled}, "
            f"proxy_count={len(self.proxies)})"
        )

    __str__ = __repr__


class DetailPageSettings(StrictBaseModel):
    """Selectors applied to each listing's own page to fill what the list page lacks."""

    enabled: bool = False
    url_field: str = "url"
    fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fields(self) -> DetailPageSettings:
        unknown = self.fields.keys() - MAPPABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown detail page mapped fields: {sorted(unknown)}.")
        return self


class CrawlerConfig(StrictBaseModel):
    """Validated configuration for one crawl source."""

    site_id: NonBlank
    name: NonBlank = Field(max_length=100)
    enabled: bool = True
    crawler_type: Literal["rest_api", "html"] = "rest_api"
    schedule_times: list[str] = Field(
        default_factory=list,
        description="Fixed daily times 'HH:MM' in source_timezone; override interval_seconds.",
    )
    interval_seconds: int | None = Field(default=None, ge=60)

    request: RequestSettings
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    response_mapping: ResponseMapping
    detail_page: DetailPageSettings = Field(default_factory=DetailPageSettings)

    allowed_domains: list[str] = Field(
        default_factory=list,
        description="Hosts accepted for listing URLs. Empty means the request host and its "
        "parent domain (api.example.com -> example.com).",
    )
    parser_version: NonBlank = "2.0.0"
    proxy_settings: ProxySettings = Field(default_factory=ProxySettings)
    source_timezone: str = Field(default="UTC", description="Timezone of schedule_times.")

    @field_validator("site_id")
    @classmethod
    def _check_site_id(cls, value: str) -> str:
        value = value.lower()
        if not SITE_ID_RE.fullmatch(value):
            raise ValueError("site_id must be 1-20 characters of a-z, 0-9, '_' and '-'.")
        return value

    @field_validator("schedule_times")
    @classmethod
    def _normalize_schedule_times(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            match = SCHEDULE_TIME_RE.fullmatch(value.strip())
            if match is None:
                raise ValueError(f"Invalid schedule time {value!r}; use 'HH:MM' (00:00-23:59).")
            normalized.append(f"{int(match['h']):02d}:{match['m']}")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate schedule_times are not allowed.")
        return sorted(normalized)

    @field_validator("source_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError(f"Invalid timezone: {value!r}") from None
        return value

    @field_validator("allowed_domains")
    @classmethod
    def _normalize_allowed_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            domain = value.strip().lower().rstrip(".")
            if not domain or not all(HOST_LABEL_RE.fullmatch(label) for label in domain.split(".")):
                raise ValueError(
                    f"Invalid hostname: {value!r}. Use a plain ASCII hostname without scheme, "
                    "path or port; convert IDNs to punycode."
                )
            normalized.append(domain)
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate allowed domains are not allowed.")
        return normalized

    @model_validator(mode="after")
    def _needs_a_schedule(self) -> CrawlerConfig:
        if self.interval_seconds is None and not self.schedule_times:
            raise ValueError(
                "Crawler config must specify either interval_seconds (>= 60) "
                "or at least one entry in schedule_times."
            )
        return self

    @model_validator(mode="after")
    def _body_paging_needs_post(self) -> CrawlerConfig:
        if self.pagination.param_location == "body" and self.request.method != "POST":
            raise ValueError("pagination.param_location='body' requires method='POST'.")
        return self

    @model_validator(mode="after")
    def _api_paths_are_json_paths(self) -> CrawlerConfig:
        # HTML sites map CSS/XPath selectors instead; those are compiled by a contract test.
        if self.crawler_type == "rest_api":
            _validate_json_path(self.response_mapping.items_path, "items_path")
            for name, path in self.response_mapping.fields.items():
                _validate_json_path(path, f"fields[{name!r}]")
            if self.pagination.stop_when_empty_path:
                _validate_json_path(self.pagination.stop_when_empty_path, "stop_when_empty_path")
        return self

    @property
    def effective_allowed_domains(self) -> tuple[str, ...]:
        if self.allowed_domains:
            return tuple(self.allowed_domains)
        host = normalize_host(self.request.url.host)
        labels = host.split(".")
        return (host, ".".join(labels[1:])) if len(labels) >= 3 else (host,)

    def is_allowed_domain(self, domain: str) -> bool:
        """Whether a hostname is one of the allowed domains or a subdomain of one."""
        domain = normalize_host(domain)
        return any(
            domain == allowed or domain.endswith("." + allowed)
            for allowed in self.effective_allowed_domains
        )

    @property
    def items_stop_path(self) -> str:
        return self.pagination.stop_when_empty_path or self.response_mapping.items_path

    def max_pages(self, run_mode: RunMode | str) -> int:
        """Page budget for one crawl run of the given mode."""
        if run_mode == RunMode.INCREMENTAL:
            return self.pagination.max_pages_incremental
        if run_mode == RunMode.FULL_SWEEP:
            return self.pagination.max_pages_full_sweep
        raise ValueError(f"Unknown run_mode: {run_mode!r}")

    def source_zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.source_timezone)
