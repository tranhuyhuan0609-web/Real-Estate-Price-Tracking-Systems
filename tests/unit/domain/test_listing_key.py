import pytest

from real_estate_price_tracking_systems.domain.value_objects import (
    ListingKeyError,
    build_listing_key,
)


def test_prefers_external_code_over_id() -> None:
    key = build_listing_key("meeyland", external_code=307624752, external_id="6a86b1")
    assert key == "meeyland_307624752"


def test_code_may_be_a_padded_string() -> None:
    assert build_listing_key("meeyland", external_code=" 123 ") == "meeyland_123"


@pytest.mark.parametrize("code", [None, "", "  ", 0, -5, True, "a b"])
def test_falls_back_to_id_when_code_unusable(code: int | str | None) -> None:
    key = build_listing_key("meeyland", external_code=code, external_id="6a86b17834e5de3cc593accf")
    assert key == "meeyland_6a86b17834e5de3cc593accf"


def test_site_id_is_stripped_and_lowercased() -> None:
    assert build_listing_key(" MeeyLand ", external_code=1) == "meeyland_1"


def test_site_id_may_contain_underscores() -> None:
    assert build_listing_key("bds_com_vn", external_id="A1") == "bds_com_vn_A1"


def test_same_listing_gets_same_key_whatever_the_url() -> None:
    # The URL is not an input at all: editing the slug cannot change the identity.
    first = build_listing_key("mogi", external_code=22751689)
    again = build_listing_key("mogi", external_code="22751689")
    assert first == again


def test_requires_a_usable_code_or_id() -> None:
    with pytest.raises(ListingKeyError, match="external_code or external_id"):
        build_listing_key("meeyland")
    with pytest.raises(ListingKeyError):
        build_listing_key("meeyland", external_code=0, external_id=" ")


@pytest.mark.parametrize("site_id", ["", "   "])
def test_blank_site_id_rejected(site_id: str) -> None:
    with pytest.raises(ListingKeyError, match="site_id"):
        build_listing_key(site_id, external_code=1)


def test_error_is_a_value_error() -> None:
    # Callers that only know ValueError (pydantic validators) still catch it.
    assert issubclass(ListingKeyError, ValueError)
