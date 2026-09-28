"""전역 상단 헤더(layout_nav.html) 좁은 폭 겹침 회귀 가드.

2026-09-28 스테이징 390 폭 관리자 화면(/admin/naver-ingest/triage): 헤더 오른쪽 버튼들이
서로 겹쳤다. 원인 두 가지(로컬 렌더 실측, 390 폭):

1. 브리핑 체브론(#personal-briefing-toggle)이 헤더 정중앙에 절대 배치(position-absolute
   start-50 translate-middle-x)라, 좁은 폭에서 중앙(x=195)이 오른쪽 버튼 묶음 위에 떨어졌다
   (내 할 일 버튼 146~186 · 체브론 175~215 · 벨 192~232).
2. 알림 배지(#global-notification-badge)가 벨 오른쪽 위 모서리를 **중심**으로 놓여
   (top-0 start-100 translate-middle) 절반이 버튼 밖으로 나가 옆 계정 버튼을 덮었다
   (배지 212~253 · 계정 버튼 238~).

고친 뒤 320/360/390/430/576/600/768/991 모두 겹침 0, 문서 가로 폭 = 화면 폭.
데스크톱(≥993)은 손대지 않는다 — 규칙은 모두 ``@media (max-width: 992px)`` 안에 있다.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HEAD = _ROOT / "templates/partials/shared/layout_head.html"
_NAV = _ROOT / "templates/partials/shared/layout_nav.html"


def _media_block(src: str, query: str) -> str:
    """``@media <query> {`` 블록 본문을 중괄호 짝 맞춰 잘라 돌려준다(첫 번째 것)."""
    head = f"@media {query} {{"
    assert head in src, query
    start = src.index(head) + len(head)
    depth = 1
    i = start
    while depth:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return src[start : i - 1]


def _rule(block: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", block)
    assert m, selector
    return m.group(1)


def test_nav_markup_keeps_absolute_center_chevron_and_corner_badge():
    """고침은 CSS 쪽이다 — 데스크톱 배치를 만드는 마크업(유틸 클래스)은 그대로 둔다."""
    nav = _NAV.read_text(encoding="utf-8")
    assert "position-absolute start-50 translate-middle-x" in nav
    assert "layout-header__center" in nav
    assert 'id="global-notification-badge"' in nav
    assert "position-absolute top-0 start-100 translate-middle badge" in nav


def test_mobile_header_chevron_joins_flow_instead_of_absolute_center():
    block = _media_block(_HEAD.read_text(encoding="utf-8"), "(max-width: 992px)")
    body = _rule(block, ".layout-header .layout-header__center")
    # 유틸 클래스(.position-absolute/.start-50/.translate-middle-x)가 !important 라 같이 이겨야 한다.
    assert "position: static !important;" in body
    assert "transform: none !important;" in body


def test_mobile_header_badge_stays_inside_bell_button_box():
    block = _media_block(_HEAD.read_text(encoding="utf-8"), "(max-width: 992px)")
    body = _rule(block, ".layout-header #global-notification-badge")
    assert "top: 0 !important;" in body
    assert "right: 0;" in body
    assert "left: auto !important;" in body  # .start-100(left:100%) 무력화
    assert "transform: none !important;" in body  # .translate-middle(-50%,-50%) 무력화


def test_mobile_header_icon_buttons_are_44px_targets():
    src = _HEAD.read_text(encoding="utf-8")
    tablet = _rule(_media_block(src, "(max-width: 992px)"), ".layout-header .d-flex.align-items-center.gap-3 .btn-link")
    assert "min-width: 44px;" in tablet
    assert "min-height: 44px;" in tablet
    phone = _media_block(src, "(max-width: 576px)")
    assert "min-width: 44px;" in phone
    assert "min-width: 40px;" not in phone
    # 체브론이 흐름 안으로 들어왔으니 헤더 칸 사이 간격이 0 이면 제목·체브론이 붙는다.
    assert "gap: 0;" not in _rule(phone, ".layout-header")


def test_desktop_bell_has_room_for_overhanging_badge():
    """993px 이상에서는 배지가 벨 버튼 모서리를 중심으로 놓여 절반이 밖으로 나간다 —
    묶음 간격(16px)만으로는 옆 계정 버튼을 약 5px 덮었다(2026-09-28, 1280px 측정).
    벨 버튼 오른쪽에 여백을 더 둔다."""
    from pathlib import Path

    head = (Path(__file__).resolve().parents[2]
            / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    block = head.split("@media (min-width: 993px) {", 1)[1].split("}", 2)
    rule = block[0] + "}" + block[1]
    assert "#global-notification-btn" in rule and "margin-right: 0.625rem" in rule
