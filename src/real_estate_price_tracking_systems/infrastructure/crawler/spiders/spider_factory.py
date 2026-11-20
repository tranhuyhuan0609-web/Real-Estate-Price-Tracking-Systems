"""Pick the spider implementation for a feed from its ``crawler_type``."""

from real_estate_price_tracking_systems.application.ports import Spider
from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.infrastructure.crawler.spiders.generic_api_spider import (
    GenericApiSpider,
)


def create_spider(config: CrawlerConfig) -> Spider:
    """The spider for ``config.crawler_type``.

    Raises ``ValueError`` for a type with no spider, so a feed that loaded but cannot be crawled
    fails loudly when the run starts instead of silently crawling nothing.
    """
    if config.crawler_type == "rest_api":
        return GenericApiSpider(config)
    raise ValueError(
        f"No spider for crawler_type {config.crawler_type!r} (feed {config.site_id!r})"
    )
