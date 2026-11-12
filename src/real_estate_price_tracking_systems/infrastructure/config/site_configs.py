"""Load declarative site configs from ``configs/sites/*.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from real_estate_price_tracking_systems.domain.entities.crawler_config import CrawlerConfig
from real_estate_price_tracking_systems.domain.exceptions import ConfigCorruptedError
from real_estate_price_tracking_systems.infrastructure.config.base import BASE_DIR

DEFAULT_SITES_DIR = BASE_DIR / "configs" / "sites"


def load_site_config(path: Path) -> CrawlerConfig:
    """Parse and validate one file; its name must equal its ``site_id``.

    Every failure is a :class:`ConfigCorruptedError` naming the file, so one bad site is easy
    to find among many.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigCorruptedError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigCorruptedError(f"{path.name}: top level must be a mapping.")
    try:
        config = CrawlerConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigCorruptedError(f"{path.name}: {exc}") from exc
    if config.site_id != path.stem:
        raise ConfigCorruptedError(
            f"{path.name}: site_id '{config.site_id}' must match the file name '{path.stem}'."
        )
    return config


def load_site_configs(directory: Path = DEFAULT_SITES_DIR) -> list[CrawlerConfig]:
    """Load every ``*.yaml`` / ``*.yml`` file, sorted by file name.

    Because a file name must equal its ``site_id``, the only way to get a duplicate is the same
    stem with both extensions; that is rejected too.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Site config directory not found: {directory}")
    paths = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    stems = [p.stem for p in paths]
    duplicates = sorted({s for s in stems if stems.count(s) > 1})
    if duplicates:
        raise ConfigCorruptedError(f"Both .yaml and .yml exist for: {', '.join(duplicates)}.")
    return [load_site_config(p) for p in paths]
