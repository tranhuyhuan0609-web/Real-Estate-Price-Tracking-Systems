"""Spiders: config-driven crawlers that yield parsed listings."""

from real_estate_price_tracking_systems.infrastructure.crawler.spiders.generic_api_spider import (
    GenericApiSpider,
)
from real_estate_price_tracking_systems.infrastructure.crawler.spiders.generic_html_spider import (
    GenericHtmlSpider,
)
from real_estate_price_tracking_systems.infrastructure.crawler.spiders.spider_factory import (
    create_spider,
)

__all__ = ["GenericApiSpider", "GenericHtmlSpider", "create_spider"]
