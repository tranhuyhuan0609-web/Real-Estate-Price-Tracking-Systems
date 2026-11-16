from typing import Protocol

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig


class ConfigRepository(Protocol):
    """Crawler configurations, one per feed."""

    async def get_config(self, site_id: str) -> CrawlerConfig:
        """Raises ``ConfigNotFoundError`` when the feed does not exist."""
        ...

    async def get_enabled_configs(self) -> list[CrawlerConfig]: ...

    async def create_config(self, config: CrawlerConfig) -> None:
        """Raises ``ConfigAlreadyExistsError`` when the feed already exists."""
        ...

    async def update_config(self, site_id: str, config: CrawlerConfig) -> None:
        """Raises ``ConfigNotFoundError`` when the feed does not exist."""
        ...

    async def delete_config(self, site_id: str) -> None:
        """Raises ``ConfigNotFoundError`` when the feed does not exist."""
        ...

    async def update_last_run(self, site_id: str) -> None:
        """Raises ``ConfigNotFoundError`` when the feed does not exist."""
        ...
