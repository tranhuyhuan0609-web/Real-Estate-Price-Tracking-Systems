import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.spiders import (
    GenericApiSpider,
    create_spider,
)
from tests.unit.spiders.test_generic_api_spider import make_config


def test_rest_api_feeds_get_the_api_spider() -> None:
    assert isinstance(create_spider(make_config()), GenericApiSpider)


def test_a_crawler_type_without_a_spider_fails_loudly() -> None:
    config = make_config().model_copy(update={"crawler_type": "ftp"})
    with pytest.raises(ValueError, match="No spider for crawler_type 'ftp'"):
        create_spider(config)
