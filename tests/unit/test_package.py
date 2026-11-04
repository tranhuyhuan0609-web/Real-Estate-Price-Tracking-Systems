import re

import real_estate_price_tracking_systems as pkg


def test_package_exposes_a_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", pkg.__version__)
