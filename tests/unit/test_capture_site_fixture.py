"""scripts/capture_site_fixture.py is the only thing standing between a captured real page and the
repository, so its anonymisation is tested: no real phone, e-mail or name may survive."""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def capture() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "capture_site_fixture", ROOT / "scripts" / "capture_site_fixture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LIST_PAGE = """
<html><head><script>var secret = "0987654321";</script></head><body>
<header>Site header 0911111111</header>
<ul class="props">
  <li class="card" data-id="1"><h2>Nhà A</h2><a class="agent">Trần Thị Bình</a>
      <span>Gọi 0987 654 321 hoặc binh.tran@gmail.com</span></li>
  <li class="card" data-id="2"><h2>Nhà B</h2><a class="agent">Trần Thị Bình</a></li>
  <li class="card" data-id="3"><h2>Nhà C</h2></li>
  <li class="card" data-id="4"><h2>Nhà D</h2></li>
</ul>
<footer>Hotline 0933333333</footer>
</body></html>
"""

DETAIL_PAGE = """
<html><body>
<div class="seller"><b>Trần Thị Bình</b>
  <a href="tel:+84987654321">+84 987 654 321</a>
  <a class="__cf_email__" data-cfemail="0f6d6e7b5f68627c6b616b216c6062">[email protected]</a>
  <p>Liên hệ chị Bình, SĐT 098.765.4321, zalo 0912 345 678.</p>
  <span class="masked">0987 65****</span>
  <!-- internal note: 0944444444 -->
</div>
<script>track("0955555555")</script>
</body></html>
"""

REAL_PHONES = ("0987654321", "987654321", "098.765.4321", "0912345678", "0911111111", "0933333333")


def assert_anonymous(text: str) -> None:
    digits = re.sub(r"[^\d]", "", text)
    for phone in REAL_PHONES:
        assert re.sub(r"[^\d]", "", phone) not in digits, f"real phone {phone} survived"
    assert "binh.tran@gmail.com" not in text
    assert "Trần Thị Bình" not in text
    assert "Bình" not in text, "the given name after an honorific survived"
    assert "0944444444" not in text and "0955555555" not in text


def test_list_page_keeps_n_cards_and_scrubs_everything(capture: ModuleType) -> None:
    names = capture.collect_names(LIST_PAGE, "a.agent")
    assert names == {"Trần Thị Bình"}

    out = capture.build_list(LIST_PAGE, "li.card", 2, [0], "a.agent", names)

    assert out.count('class="card"') == 2  # only the first two cards
    assert "<script" not in out and "<header" not in out and "<footer" not in out
    assert "ul" in out  # the cards stay inside a copy of their parent, so items_path still matches
    assert_anonymous(out)
    assert capture.FAKE_NAME in out and capture.FAKE_EMAIL in out


def test_detail_page_is_scrubbed(capture: ModuleType) -> None:
    names = capture.collect_names(DETAIL_PAGE, "div.seller b")
    out = capture.build_detail(DETAIL_PAGE, "div.seller b", [0], names)

    assert_anonymous(out)
    assert "<script" not in out and "<!--" not in out
    assert "0900000" in out  # replaced by the reserved fake range
    assert "data-cfemail" not in out or capture._cf_encode(capture.FAKE_EMAIL) in out


def test_cloudflare_email_is_replaced_by_the_fake_one(capture: ModuleType) -> None:
    from real_estate_price_tracking_systems.infrastructure.crawler.parsing.html_cleaner import (
        decode_cloudflare_email,
    )

    out = capture.build_detail(DETAIL_PAGE, None, [0], set())
    match = re.search(r'data-cfemail="([0-9a-f]+)"', out)
    assert match and decode_cloudflare_email(match.group(1)) == capture.FAKE_EMAIL


def test_fake_phones_are_distinct_and_in_the_reserved_range(capture: ModuleType) -> None:
    counter = [0]
    out = capture._scrub_text("A 0987654321, B 0912345678, C +84 933 333 333", counter)
    fakes = re.findall(r"09000000\d\d", out)
    assert fakes == ["0900000001", "0900000002", "0900000003"]


def test_a_missing_items_path_fails_loudly(capture: ModuleType) -> None:
    with pytest.raises(SystemExit, match="matched nothing"):
        capture.build_list(LIST_PAGE, "div.nope", 2, [0], None, set())
