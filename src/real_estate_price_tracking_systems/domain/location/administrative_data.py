"""Vietnamese administrative names used to read free-text addresses.

Spelling variants are what portals actually write ("tp.hcm", "Sài Gòn", "hn"); names are the
pre-2025 provinces, which is what listings still use.
"""

from __future__ import annotations

import re

PROVINCE_KEYWORDS: tuple[str, ...] = (
    "hồ chí minh",
    "tp.hcm",
    "tphcm",
    "tp hcm",
    "tp. hcm",
    "hcm",
    "hcmc",
    "sài gòn",
    "saigon",
    "hà nội",
    "tp.hn",
    "tphn",
    "tp hn",
    "hn",
    "đà nẵng",
    "hải phòng",
    "cần thơ",
    "an giang",
    "bà rịa - vũng tàu",
    "bà rịa vũng tàu",
    "vũng tàu",
    "bắc giang",
    "bắc kạn",
    "bạc liêu",
    "bắc ninh",
    "bến tre",
    "bình định",
    "bình dương",
    "bình phước",
    "bình thuận",
    "cà mau",
    "cao bằng",
    "đắk lắk",
    "đắk nông",
    "điện biên",
    "đồng nai",
    "đồng tháp",
    "gia lai",
    "hà giang",
    "hà nam",
    "hà tĩnh",
    "hải dương",
    "hậu giang",
    "hòa bình",
    "hưng yên",
    "khánh hòa",
    "kiên giang",
    "kon tum",
    "lai châu",
    "lâm đồng",
    "lạng sơn",
    "lào cai",
    "long an",
    "nam định",
    "nghệ an",
    "ninh bình",
    "ninh thuận",
    "phú thọ",
    "phú yên",
    "quảng bình",
    "quảng nam",
    "quảng ngãi",
    "quảng ninh",
    "quảng trị",
    "sóc trăng",
    "sơn la",
    "tây ninh",
    "thái bình",
    "thái nguyên",
    "thanh hóa",
    "thừa thiên huế",
    "huế",
    "tiền giang",
    "trà vinh",
    "tuyên quang",
    "vĩnh long",
    "vĩnh phúc",
    "yên bái",
)

# Regex alternations for the administrative level written before a name
DISTRICT_PREFIXES = r"(?:quận|huyện|thị xã|thành phố|tp\.?|tx\.?|q\.?|h\.?)"
WARD_PREFIXES = r"(?:phường|xã|thị trấn|tt\.?|p\.?|x\.?)"
STREET_PREFIXES = r"(?:đường|phố|ngõ|ngách|hẻm|số|kdc|kđt|khu đô thị|khu dân cư)"

KNOWN_HCM_DISTRICT_NAMES: frozenset[str] = frozenset(
    {
        "quận 1",
        "quận 2",
        "quận 3",
        "quận 4",
        "quận 5",
        "quận 6",
        "quận 7",
        "quận 8",
        "quận 9",
        "quận 10",
        "quận 11",
        "quận 12",
        "bình thạnh",
        "gò vấp",
        "tân bình",
        "tân phú",
        "phú nhuận",
        "bình tân",
        "thủ đức",
        "hóc môn",
        "củ chi",
        "bình chánh",
        "nhà bè",
        "cần giờ",
    }
)

KNOWN_HANOI_DISTRICT_NAMES: frozenset[str] = frozenset(
    {
        "ba đình",
        "hoàn kiếm",
        "tây hồ",
        "long biên",
        "cầu giấy",
        "đống đa",
        "hai bà trưng",
        "hoàng mai",
        "thanh xuân",
        "nam từ liêm",
        "bắc từ liêm",
        "hà đông",
        "sơn tây",
        "ba vì",
        "phúc thọ",
        "đan phượng",
        "hoài đức",
        "quốc oai",
        "thạch thất",
        "chương mỹ",
        "thanh oai",
        "thường tín",
        "phú xuyên",
        "ứng hòa",
        "mê linh",
        "đông anh",
        "gia lâm",
        "sóc sơn",
        "thanh trì",
    }
)

# Bare HCM district names -> full official name
KNOWN_HCM_DISTRICTS: dict[str, str] = {
    "bình thạnh": "Quận Bình Thạnh",
    "gò vấp": "Quận Gò Vấp",
    "tân bình": "Quận Tân Bình",
    "tân phú": "Quận Tân Phú",
    "phú nhuận": "Quận Phú Nhuận",
    "bình tân": "Quận Bình Tân",
    "thủ đức": "Thành phố Thủ Đức",
    "nhà bè": "Huyện Nhà Bè",
    "hóc môn": "Huyện Hóc Môn",
    "củ chi": "Huyện Củ Chi",
    "bình chánh": "Huyện Bình Chánh",
    "cần giờ": "Huyện Cần Giờ",
}


def _squash(text: str) -> str:
    """Lower-case and drop dots and whitespace: "TP. HCM" -> "tphcm"."""
    return re.sub(r"[.\s]", "", text.strip().lower())


# Forms written with their own prefix glued on, e.g. "tp.hồ chí minh" (no space after the dot).
_PREFIXED_CITY_FORMS = frozenset(
    {
        "tphcm", "hcm", "hcmc", "tphồchíminh", "thànhphốhồchíminh", "hồchíminh",
        "saigon", "sàigòn",
        "tphànội", "thànhphốhànội", "hànội", "hn",
        "tpđànẵng", "thànhphốđànẵng", "đànẵng",
        "tphảiphòng", "thànhphốhảiphòng", "hảiphòng",
        "tpcầnthơ", "thànhphốcầnthơ", "cầnthơ",
    }
)  # fmt: skip
_PROVINCE_FORMS = frozenset(map(_squash, PROVINCE_KEYWORDS))

# A token starting with a lower administrative level or a street word is never a province,
# even when the rest is a province name ("phường Long An", "đường Hà Nội").
_NOT_A_PROVINCE = re.compile(
    r"^(?:phường|p[\s.]|xã|x[\s.]|thị trấn|tt[\s.]|quận|q[\s.]|huyện|h[\s.]|đường|ngõ|ngách|hẻm|phố|số)"
)
_PROVINCE_PREFIX = re.compile(r"^(?:tỉnh|thành phố|tp\.?)\s+")


def is_province_token(part: str) -> bool:
    """Whether one comma-separated address part names a province or centrally-run city."""
    if not part:
        return False
    lower = part.strip().lower()
    if _NOT_A_PROVINCE.match(lower):
        return False
    if _squash(lower) in _PREFIXED_CITY_FORMS:
        return True
    return _squash(_PROVINCE_PREFIX.sub("", lower)) in _PROVINCE_FORMS
