"""Read free-text Vietnamese addresses into street / ward / district / city.

Portals write the same place many ways ("Q.1", "Quận 01", "TP.HCM", "Sài Gòn"); everything is
canonicalised so the same district always gets the same string in Silver.
"""

from __future__ import annotations

import re

from real_estate_price_tracking_systems.domain.location.administrative_data import (
    DISTRICT_PREFIXES,
    KNOWN_HCM_DISTRICTS,
    STREET_PREFIXES,
    WARD_PREFIXES,
    is_province_token,
)

Location = tuple[str | None, str | None, str | None]  # (city, district, ward)

# Spelling variants (lower-case, dots/spaces removed) -> canonical city name
_CITY_ALIASES: dict[str, str] = {
    alias: canonical
    for canonical, aliases in {
        "Thành phố Hồ Chí Minh": (
            "hồchíminh",
            "tphcm",
            "tphồchíminh",
            "thànhphốhồchíminh",
            "hcm",
            "hcmc",
            "sàigòn",
            "saigon",
        ),
        "Thành phố Hà Nội": ("hànội", "tphànội", "thànhphốhànội", "hn"),
        "Thành phố Đà Nẵng": ("đànẵng", "tpđànẵng", "thànhphốđànẵng"),
        "Thành phố Hải Phòng": ("hảiphòng", "tphảiphòng", "thànhphốhảiphòng"),
        "Thành phố Cần Thơ": ("cầnthơ", "tpcầnthơ", "thànhphốcầnthơ"),
        "Bà Rịa - Vũng Tàu": ("bàrịa-vũngtàu", "bàrịavũngtàu", "vũngtàu", "tỉnhbàrịavũngtàu"),
        "Thừa Thiên Huế": ("thừathiênhuế", "huế", "tỉnhthừathiênhuế"),
    }.items()
    for alias in aliases
}
_DISTRICT_ABBREVIATIONS = (
    (r"^q\.?\s+", "Quận "),
    (r"^h\.?\s+", "Huyện "),
    (r"^tx\.?\s+", "Thị xã "),
    (r"^tp\.?\s+", "Thành phố "),
)
_WARD_ABBREVIATIONS = ((r"^p\.?\s+", "Phường "), (r"^x\.?\s+", "Xã "), (r"^tt\.?\s+", "Thị trấn "))
_DISTRICT_NUMBER = re.compile(r"^(?:quận|q\.?)\s*0?(\d+)$", re.IGNORECASE)
_WARD_NUMBER = re.compile(r"^(?:phường|p\.?)\s*0?(\d+)$", re.IGNORECASE)
_DISTRICT_START = re.compile(rf"^{DISTRICT_PREFIXES}\s+")
_WARD_START = re.compile(rf"^{WARD_PREFIXES}\s+")
_STREET_START = re.compile(rf"^{STREET_PREFIXES}\s+")
_SEPARATORS = re.compile(r"[,;]|\s+-\s+")
_DISTRICT_LEVEL = re.compile(r"^(?:quận|huyện|thị xã|thành phố)\s+", re.IGNORECASE)


def _expand(value: str, abbreviations: tuple[tuple[str, str], ...]) -> str:
    for pattern, replacement in abbreviations:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


def _canonical_city(city: str) -> str:
    return _CITY_ALIASES.get(re.sub(r"[.\s]", "", city.strip().lower()), city.strip())


def _canonical_district(district: str) -> str:
    d_str = district.strip()
    m_num = _DISTRICT_NUMBER.match(d_str)
    if m_num:
        return f"Quận {m_num.group(1)}"
    d_norm = _expand(d_str, _DISTRICT_ABBREVIATIONS)
    d_lower = d_norm.lower().strip()
    if d_lower in KNOWN_HCM_DISTRICTS and not _DISTRICT_LEVEL.match(d_norm):
        return KNOWN_HCM_DISTRICTS[d_lower]
    return d_norm


def _canonical_ward(ward: str) -> str:
    w_str = ward.strip()
    m_num = _WARD_NUMBER.match(w_str)
    if m_num:
        return f"Phường {m_num.group(1)}"
    return _expand(w_str, _WARD_ABBREVIATIONS)


def canonicalize_vietnamese_location(
    city: str | None = None,
    district: str | None = None,
    ward: str | None = None,
) -> Location:
    """Canonical (city, district, ward): "Q. 1" -> "Quận 1", "TP.HCM" -> "Thành phố Hồ Chí Minh"."""
    return (
        _canonical_city(city) if city else city,
        _canonical_district(district) if district else district,
        _canonical_ward(ward) if ward else ward,
    )


def _strip(value: str | None) -> str | None:
    return value.strip() if value else None


def _fold_composite_hints(
    raw_address: str | None, hints: list[str | None]
) -> tuple[str | None, list[str | None]]:
    """A hint like "Phường 1, Quận 3" is really a partial address: append it to the address."""
    kept: list[str | None] = []
    for hint in hints:
        if hint and ("," in hint or " - " in hint):
            raw_address = f"{raw_address}, {hint}" if raw_address else hint
            kept.append(None)
        else:
            kept.append(hint)
    return raw_address, kept


def _assign_parts(
    parts: list[str],
    street: str | None,
    ward: str | None,
    district: str | None,
    city: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Fill the still-missing levels from comma-separated parts (right = larger unit)."""
    if not city:  # the province is usually the right-most part
        for idx in range(len(parts) - 1, -1, -1):
            if is_province_token(parts[idx]):
                city = parts.pop(idx)
                break

    if len(parts) == 1:
        p_lower = parts[0].lower()
        if not city and is_province_token(parts[0]):
            city = parts.pop(0)
        elif not district and (_DISTRICT_START.match(p_lower) or not ward):
            district = parts.pop(0)
        elif not ward and _WARD_START.match(p_lower):
            ward = parts.pop(0)
        elif not street:
            street = parts.pop(0)
        else:
            district = district or parts.pop(0)
    elif len(parts) == 2:
        p0_lower = parts[0].lower()
        if not district:
            district = parts.pop(1)
        if not ward and not _STREET_START.match(p0_lower):
            ward = parts.pop(0)
        elif not street:
            street = parts.pop(0)
    elif len(parts) == 3:
        if not district:
            district = parts.pop(2)
        if not ward:
            ward = parts.pop(1)
        if not street and parts:
            street = parts.pop(0)
    elif len(parts) >= 4:
        if not district:
            district = parts.pop(-1)
        if not ward:
            ward = parts.pop(-1)
        if parts:
            street = ", ".join(parts).strip()
    return street, ward, district, city


def parse_vietnamese_address(
    raw_address: str | None = None,
    city_hint: str | None = None,
    district_hint: str | None = None,
    ward_hint: str | None = None,
    canonicalize: bool = True,
) -> dict[str, str | None]:
    """Parse a Vietnamese address string into street_name, ward_name, district_name, city_name.

    Explicit hints win over what is parsed from ``raw_address``.
    """
    raw_address, (city, district, ward) = _fold_composite_hints(
        raw_address, [_strip(city_hint), _strip(district_hint), _strip(ward_hint)]
    )
    street: str | None = None
    if raw_address:
        addr = re.sub(r"\s+", " ", raw_address.strip())
        parts = [p.strip() for p in _SEPARATORS.split(addr) if p.strip()]
        if parts:
            street, ward, district, city = _assign_parts(parts, street, ward, district, city)

    if canonicalize:
        city, district, ward = canonicalize_vietnamese_location(city, district, ward)
    return {"street_name": street, "ward_name": ward, "district_name": district, "city_name": city}
