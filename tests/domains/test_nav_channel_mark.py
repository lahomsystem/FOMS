"""nav '네이버 수집' 채널 표식 (2026-08-25).

사내 화면들 사이에서 **바깥 채널에서 들어온 일감**만 눈으로 갈라져야 한다.
표식은 인라인 SVG 다 — 외부 이미지면 네트워크 왕복이 늘고 CSP·자산 핀(?v) 관리 대상이
하나 더 생긴다. 여기서 못박는 것:

1. 표식이 **네이버 수집 항목에만** 붙는다(다른 메뉴에 번지면 표식의 뜻이 사라진다).
2. 외부 이미지(``<img src>``)가 아니라 인라인 SVG 다.
3. 뱃지(확인 대기 건수)와 **함께** 뜬다 — 표식이 뱃지를 밀어내면 안 된다.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAYOUT_NAV = ROOT / "templates/partials/shared/layout_nav.html"
BRIDGE_CSS = ROOT / "static/css/foundation/erp-pro/13-foms-shell-bridge.css"


def _nav() -> str:
    return LAYOUT_NAV.read_text(encoding="utf-8")


def test_mark_is_inline_svg_not_an_external_image():
    """인라인 SVG 다 — 외부 이미지가 아니다."""
    markup = _nav()

    assert "foms-nav-mark--naver" in markup
    assert "<svg class=\"foms-nav-mark" in markup
    # 네이버 브랜드 초록. 색을 잃으면 표식이 그냥 회색 사각형이 된다.
    assert "#03C75A" in markup
    naver_img = re.search(r"<img[^>]+naver[^>]*>", markup, re.IGNORECASE)
    assert naver_img is None, f"외부 이미지로 바뀌었다: {naver_img.group(0) if naver_img else ''}"


def test_mark_is_scoped_to_the_naver_item_only():
    """표식은 `naver_orders` 항목에만 붙는다 — 조건 없이 달면 전 메뉴에 번진다."""
    markup = _nav()

    assert "{% if item.id == 'naver_orders' %}" in markup


def test_badge_still_renders_next_to_the_mark():
    """확인 대기 뱃지는 그대로다 — 표식이 뱃지를 밀어내면 건수를 못 본다."""
    markup = _nav()

    assert "item.id == 'naver_orders' and naver_triage_pending" in markup
    assert "{{ naver_triage_pending }}" in markup


def test_dropdown_entry_uses_the_same_mark():
    """관리자 드롭다운도 같은 표식을 쓴다 — 한 기능이 두 생김새를 가지면 안 된다."""
    markup = _nav()

    assert markup.count("foms-nav-mark--naver") >= 2
    assert "fa-clipboard-check" not in markup, "옛 아이콘이 남아 있다(생김새 두 벌)"


def test_mark_alignment_rule_lives_in_css_not_inline_style():
    """정렬은 CSS 클래스가 한다 — 인라인 style 금지 규칙."""
    css = BRIDGE_CSS.read_text(encoding="utf-8")

    assert ".foms-nav-mark {" in css
    assert "vertical-align" in css
    assert 'style="vertical-align' not in _nav()
