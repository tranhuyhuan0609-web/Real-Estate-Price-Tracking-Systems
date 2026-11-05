import pytest

from real_estate_price_tracking_systems.domain.services import (
    evaluate_price_change,
    generate_fingerprint,
)
from real_estate_price_tracking_systems.domain.value_objects import PriceStatus

# --- price change ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "status", "diff", "pct"),
    [
        (2_000_000_000, 2_200_000_000, PriceStatus.INCREASED, 200_000_000.0, 10.0),
        (4_000_000_000, 3_600_000_000, PriceStatus.DECREASED, -400_000_000.0, -10.0),
        (5_000_000_000, 5_000_000_000, PriceStatus.UNCHANGED, 0.0, 0.0),
        (3_000_000_000, 3_100_000_000, PriceStatus.INCREASED, 100_000_000.0, 3.33),
    ],
)
def test_price_moves(old: float, new: float, status: PriceStatus, diff: float, pct: float) -> None:
    res = evaluate_price_change(old, new)
    assert (res.price_status, res.price_diff_vnd, res.price_diff_percent) == (status, diff, pct)


@pytest.mark.parametrize("old", [None, 0, -1])
def test_first_real_price_is_initial(old: float | None) -> None:
    res = evaluate_price_change(old, 3_000_000_000)
    assert (res.price_status, res.price_diff_vnd, res.price_diff_percent) == (
        PriceStatus.INITIAL,
        0.0,
        0.0,
    )


@pytest.mark.parametrize("new", [None, 0, -1])
def test_missing_new_price_is_contact_even_without_old(new: float | None) -> None:
    assert evaluate_price_change(3_000_000_000, new).price_status is PriceStatus.CONTACT
    assert evaluate_price_change(None, new).price_status is PriceStatus.CONTACT


def test_evaluation_is_immutable() -> None:
    res = evaluate_price_change(1, 2)
    with pytest.raises(ValueError):
        res.price_status = PriceStatus.DECREASED  # type: ignore[misc]


# --- fingerprint ----------------------------------------------------------------------------

BASE = {
    "title": "Bán nhà mặt phố Cầu Giấy 50m2 cực đẹp!!!",
    "area_m2": 50.0,
    "city_name": "Hà Nội",
    "district_name": "Cầu Giấy",
    "ward_name": "Dịch Vọng",
}


def fp(**changes: object) -> str:
    return generate_fingerprint(**{**BASE, **changes})  # type: ignore[arg-type]


def test_fingerprint_is_sha256_hex_and_deterministic() -> None:
    assert fp() == fp()
    assert len(fp()) == 64 and int(fp(), 16) >= 0


def test_fingerprint_ignores_case_punctuation_and_whitespace() -> None:
    same = fp(
        title="  bán nhà mặt phố   CẦU GIẤY 50m2 cực đẹp ",
        city_name=" hà nội ",
        district_name="CẦU GIẤY",
        ward_name="dịch  vọng",
    )
    assert same == fp()


def test_fingerprint_rounds_area_to_a_tenth() -> None:
    assert fp(area_m2=50.04) == fp()
    assert fp(area_m2=50.2) != fp()


def test_missing_and_non_positive_area_are_the_same() -> None:
    assert fp(area_m2=None) == fp(area_m2=0) == fp(area_m2=-3)


@pytest.mark.parametrize(
    "field",
    ["title", "city_name", "district_name", "ward_name"],
)
def test_fingerprint_changes_with_each_input(field: str) -> None:
    assert fp(**{field: "khác"}) != fp()


def test_fields_cannot_shift_into_each_other() -> None:
    # The separator keeps "district=A, ward=None" apart from "district=None, ward=A".
    assert fp(district_name="Cầu Giấy", ward_name=None) != fp(
        district_name=None, ward_name="Cầu Giấy"
    )


def test_vietnamese_diacritics_are_significant() -> None:
    # "Bán" (sell) and "Ban" are different words; only punctuation is stripped.
    assert fp(title="Bán nhà") != fp(title="Ban nha")
