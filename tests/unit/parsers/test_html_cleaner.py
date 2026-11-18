"""HTML cleanup and e-mail unmasking."""

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.area import (
    parse_vietnamese_area,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.html_cleaner import (
    clean_email,
    clean_html,
    decode_cloudflare_email,
    extract_email_from_text,
)


def cloudflare_encode(email: str, key: int = 0x41) -> str:
    """Cloudflare's data-cfemail: one hex byte of key, then each character XOR-ed with it."""
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


def test_clean_html_strips_tags_and_keeps_line_breaks() -> None:
    assert clean_html("<p>Bán nhà đẹp</p><div>Giá <b>3 tỷ</b></div>") == "Bán nhà đẹp\nGiá 3 tỷ"


def test_clean_html_unescapes_entities() -> None:
    assert clean_html("Nhà &amp; đất&nbsp;rộng") == "Nhà & đất\xa0rộng"


@pytest.mark.parametrize("raw", ["", None, "<br>", "<p> </p>"])
def test_clean_html_of_nothing(raw: str | None) -> None:
    assert clean_html(raw) is None


def test_superscript_area_survives_cleaning() -> None:
    """'250 m<sup>2</sup>' must still parse as an area once the tags are stripped."""
    cleaned = clean_html("Diện tích 250 m<sup>2</sup>")
    assert cleaned is not None
    assert parse_vietnamese_area(cleaned.removeprefix("Diện tích ")) == 250.0


def test_cloudflare_email_round_trip() -> None:
    assert decode_cloudflare_email(cloudflare_encode("a@b.com")) == "a@b.com"
    assert decode_cloudflare_email(cloudflare_encode("Nguyen@Gmail.com")) == "nguyen@gmail.com"


@pytest.mark.parametrize("raw", ["zz", "41", "", None, "4120"])
def test_cloudflare_garbage_is_none(raw: str | None) -> None:
    assert decode_cloudflare_email(raw) is None


@pytest.mark.parametrize(
    ("raw", "email"),
    [
        ("Nguyen.A@gmail.com", "nguyen.a@gmail.com"),
        ("mailto:Foo@Gmail.com?subject=hi", "foo@gmail.com"),
        ("chatpostinfo_x@gmail.com", "x@gmail.com"),
        ("/avatar/name@gmail.com-1700000000.jpg", "name@gmail.com"),
        (cloudflare_encode("a@b.com"), "a@b.com"),
        ("foo@mogi.vn", "foo@mogi.vn"),  # a portal domain alone is fine; only support names are not
    ],
)
def test_clean_email(raw: str, email: str) -> None:
    assert clean_email(raw) == email


@pytest.mark.parametrize(
    "raw",
    [
        "abc***@gmail.com",  # masked: storing it would corrupt the advertiser
        "abc...@gmail.com",
        "lienhe@mogi.vn",  # the portal's own support address, not the seller's
        "hotro@meeyland.com",
        "a@b",
        "not an email",
        "",
        None,
    ],
)
def test_clean_email_rejects(raw: str | None) -> None:
    assert clean_email(raw) is None


def test_email_found_in_text_skips_support_addresses() -> None:
    text = "Liên hệ lienhe@mogi.vn hoặc nguyenvan@gmail.com"
    assert extract_email_from_text(text) == "nguyenvan@gmail.com"
    assert extract_email_from_text("không có email") is None
    assert extract_email_from_text(None) is None
