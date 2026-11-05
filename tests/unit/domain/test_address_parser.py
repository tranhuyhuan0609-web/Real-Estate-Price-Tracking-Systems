import pytest

from real_estate_price_tracking_systems.domain.location import (
    canonicalize_vietnamese_location,
    is_province_token,
    parse_vietnamese_address,
)

HCM = "Thành phố Hồ Chí Minh"
HN = "Thành phố Hà Nội"


def parsed(raw: str | None, **hints: str | None) -> tuple[str | None, ...]:
    r = parse_vietnamese_address(raw, **hints)  # type: ignore[arg-type]
    return r["street_name"], r["ward_name"], r["district_name"], r["city_name"]


# --- canonicalisation -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("city", "want"),
    [
        ("TP.HCM", HCM),
        ("TP. HCM", HCM),
        ("TP Hồ Chí Minh", HCM),
        ("Sài Gòn", HCM),
        ("hcmc", HCM),
        ("Hà Nội", HN),
        ("TP. Hà Nội", HN),
        ("HN", HN),
        ("Đà Nẵng", "Thành phố Đà Nẵng"),
        ("Vũng Tàu", "Bà Rịa - Vũng Tàu"),
        ("Huế", "Thừa Thiên Huế"),
        ("  Long An ", "Long An"),  # unknown spelling: kept, only stripped
    ],
)
def test_city_aliases(city: str, want: str) -> None:
    assert canonicalize_vietnamese_location(city)[0] == want


@pytest.mark.parametrize(
    ("district", "want"),
    [
        ("Q. 1", "Quận 1"),
        ("Q1", "Quận 1"),
        ("Quận 01", "Quận 1"),
        ("Q. Bình Thạnh", "Quận Bình Thạnh"),
        ("Bình Thạnh", "Quận Bình Thạnh"),  # bare HCM district gets its level
        ("H. Củ Chi", "Huyện Củ Chi"),
        ("tx. Dĩ An", "Thị xã Dĩ An"),
        ("Thủ Đức", "Thành phố Thủ Đức"),
        ("tp. Thủ Đức", "Thành phố Thủ Đức"),
    ],
)
def test_district_abbreviations(district: str, want: str) -> None:
    assert canonicalize_vietnamese_location(district=district)[1] == want


@pytest.mark.parametrize(
    ("ward", "want"),
    [
        ("P. 7", "Phường 7"),
        ("P.07", "Phường 7"),
        ("P7", "Phường 7"),
        ("P. Bến Nghé", "Phường Bến Nghé"),
        ("X. Vĩnh Lộc A", "Xã Vĩnh Lộc A"),
        ("tt. Đông Anh", "Thị trấn Đông Anh"),
    ],
)
def test_ward_abbreviations(ward: str, want: str) -> None:
    assert canonicalize_vietnamese_location(ward=ward)[2] == want


def test_missing_levels_stay_missing() -> None:
    assert canonicalize_vietnamese_location() == (None, None, None)


# --- parsing --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        (
            "218/3 Nguyễn Văn Nghi, Phường 7, Quận Gò Vấp, TP.HCM",
            ("218/3 Nguyễn Văn Nghi", "Phường 7", "Quận Gò Vấp", HCM),
        ),
        ("Huyện Ba Vì, Hà Nội", (None, None, "Huyện Ba Vì", HN)),
        ("Bến Cát, TP. Hồ Chí Minh", (None, None, "Bến Cát", HCM)),
        ("Phường An Phú, Quận 2, TP Hồ Chí Minh", (None, "Phường An Phú", "Quận 2", HCM)),
        ("Minh Quang, Ba Vì, Hà Nội", (None, "Minh Quang", "Ba Vì", HN)),
        ("P.7 - Q.3 - TP.HCM", (None, "Phường 7", "Quận 3", HCM)),  # dash separators
        ("12 ngõ 5; Cầu Giấy; Hà Nội", (None, "12 ngõ 5", "Cầu Giấy", HN)),
    ],
)
def test_parses_right_to_left(raw: str, want: tuple[str | None, ...]) -> None:
    assert parsed(raw) == want


def test_street_prefix_keeps_part_out_of_ward() -> None:
    street, ward, district, city = parsed(
        "80/..., Đường Hoàng Hoa Thám, Phường 7, Quận Bình Thạnh, TP.HCM"
    )
    assert street is not None and "Hoàng Hoa Thám" in street
    assert (ward, district, city) == ("Phường 7", "Quận Bình Thạnh", HCM)


def test_extra_leading_parts_join_into_the_street() -> None:
    street, ward, district, city = parsed(
        "Chung cư Mỹ Phước, 280 Bùi Hữu Nghĩa, Phường 2, Bình Thạnh, Hồ Chí Minh"
    )
    assert street == "Chung cư Mỹ Phước, 280 Bùi Hữu Nghĩa"
    assert (ward, district, city) == ("Phường 2", "Quận Bình Thạnh", HCM)


def test_province_named_ward_or_street_is_not_the_city() -> None:
    # "Phường Long An" and "Đường Hà Nội" contain province names but are not provinces.
    assert parsed("Đường Hà Nội, Phường Long An, Tân An, Long An")[3] == "Long An"


def test_hints_win_over_parsing() -> None:
    assert parsed(
        "218/3 Nguyễn Văn Nghi",
        ward_hint="Phường 7",
        district_hint="Quận Gò Vấp",
        city_hint="TP.HCM",
    ) == ("218/3 Nguyễn Văn Nghi", "Phường 7", "Quận Gò Vấp", HCM)


def test_composite_hint_is_folded_into_the_address() -> None:
    # Some portals put "Phường 1, Quận 3" into the district field.
    assert parsed(None, district_hint="Phường 1, Quận 3", city_hint="TP.HCM") == (
        None,
        "Phường 1",
        "Quận 3",
        HCM,
    )


def test_canonicalisation_can_be_turned_off() -> None:
    r = parse_vietnamese_address(
        "218/3 Nguyễn Văn Nghi, Phường 7, Quận Gò Vấp, TP.HCM", canonicalize=False
    )
    assert (r["district_name"], r["city_name"]) == ("Quận Gò Vấp", "TP.HCM")


@pytest.mark.parametrize("raw", [None, "", "   ", ", ;"])
def test_empty_address(raw: str | None) -> None:
    assert parsed(raw) == (None, None, None, None)


# --- province tokens ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["TP.HCM", "tp.hồ chí minh", "Thành phố Hà Nội", "Tỉnh Long An", "Bình Dương "]
)
def test_province_tokens(token: str) -> None:
    assert is_province_token(token)


@pytest.mark.parametrize(
    "token", ["", "Phường Long An", "đường Hà Nội", "Quận 1", "h. Củ Chi", "Cầu Giấy", "số 5"]
)
def test_not_province_tokens(token: str) -> None:
    assert not is_province_token(token)
