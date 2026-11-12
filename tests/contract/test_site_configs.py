"""Every file in configs/sites/ must load, survive storage, and contain only valid selectors."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from parsel import Selector

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.infrastructure.config import (
    load_site_config,
    load_site_configs,
)
from tests.conftest import ROOT

SITES_DIR = ROOT / "configs" / "sites"
SITE_FILES = sorted([*SITES_DIR.glob("*.yaml"), *SITES_DIR.glob("*.yml")])

# Split "a::text, b::attr(href)" on commas that are not inside (...) or [...].
_TOP_LEVEL_COMMA = re.compile(r",(?![^(\[]*[)\]])")
_PROBE = Selector(text="<html><body></body></html>")


def test_sites_directory_is_not_empty() -> None:
    assert SITE_FILES, f"no site configs in {SITES_DIR}"


@pytest.mark.parametrize("path", SITE_FILES, ids=lambda p: p.stem)
def test_site_config_loads(path: Path) -> None:
    config = load_site_config(path)
    assert config.site_id == path.stem


@pytest.mark.parametrize("path", SITE_FILES, ids=lambda p: p.stem)
def test_site_config_survives_json_round_trip(path: Path) -> None:
    # Configs are stored as JSON in the database; a lossy round trip would make every sync
    # see a "changed" config.
    config = load_site_config(path)
    assert CrawlerConfig.model_validate_json(config.model_dump_json()) == config


def test_every_portal_is_a_configured_site() -> None:
    # A typo in `portal:` would silently fork the listing-id space of a site.
    configs = {c.site_id: c for c in load_site_configs(SITES_DIR)}
    for config in configs.values():
        owner = configs.get(config.portal_id)
        assert owner is not None, f"{config.site_id}: unknown portal {config.portal_id!r}"
        assert owner.portal_id == owner.site_id, (
            f"{config.site_id}: portal {config.portal!r} is itself a feed of another portal"
        )


def selector_errors(fields: dict[str, str]) -> list[str]:
    """Compile every selector part; return one message per part that does not compile."""
    errors: list[str] = []
    for field, value in fields.items():
        for part in (p.strip() for p in _TOP_LEVEL_COMMA.split(value) if p.strip()):
            if part.startswith(("json:", "::attr(", "@")):
                continue  # embedded-JSON paths and bare attribute shortcuts are not selectors
            try:
                _PROBE.xpath(part) if part.startswith(("/", "./", "(")) else _PROBE.css(part)
            except Exception as exc:  # parsel raises several types for bad CSS/XPath
                errors.append(f"{field}: {part!r}: {exc}")
    return errors


HTML_SITES = [p for p in SITE_FILES if load_site_config(p).crawler_type == "html"]


@pytest.mark.parametrize("path", HTML_SITES, ids=lambda p: p.stem)
def test_html_selectors_compile(path: Path) -> None:
    # A malformed XPath does not fail at runtime: it silently extracts nothing.
    config = load_site_config(path)
    mapping = config.response_mapping
    errors = selector_errors(
        {"items_path": mapping.items_path, **mapping.fields, **config.detail_page.fields}
    )
    assert not errors, "\n".join(errors)


def test_selector_check_catches_broken_xpath_and_css() -> None:
    errors = selector_errors(
        {
            "ok": "h2.title::text, //div[contains(@class, 'a, b')]/text()",
            "xpath": "span::text, //p[",
            "css": "div[",
        }
    )
    assert [e.split(":")[0] for e in errors] == ["xpath", "css"]
