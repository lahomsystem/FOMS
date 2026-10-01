# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 PC 다듬기(2026-09-29 · 사용자 결정: 확인 단계 + 흐린 글자) 계약.

* 확인 단계: `지금 수집`·`과거 긁어오기` 가 PC 에서도 확인 창(wb-ask)을 거친다 — 동작 계약은
  `test_naver_workbench_mobile_p0.test_admin_card_buttons_ask_first_on_phone_and_pc`, 여기는 PC 창 모양.
* 흐린 글자: 1280 에서 4.5:1 미만이던 14곳을 `@media (min-width: 768px)` 안에서 색만 올린다. 폰 규칙은 그대로.

음성 대조군: 폰 미디어 블록 하나 · 파이프 단계 색은 건드리지 않음 · 폰 블록에는 이 규칙이 없음.
HEAD(4be09e32d 위 396859458) 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

import re

from tests.services.integrations.test_naver_workbench_mobile import CSS, TEMPLATE, _media_block, _rule
from tests.services.integrations.test_naver_workbench_mobile_p1 import _css

PC_MEDIA = "@media (min-width: 768px)"


def _pc() -> str:
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert css.count(PC_MEDIA) == 1, "PC 다듬기 블록은 하나"
    return _media_block(css, PC_MEDIA)


def _lum(hex_color: str) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(fg: str, bg: str) -> float:
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_pc_confirm_dialog_is_a_centered_card_with_stop_then_go():
    pc = _pc()
    card = _rule(pc, "    .wb-ask[open]")
    assert "width: min(440px, calc(100vw - 32px));" in card and "border-radius: 12px;" in card
    assert "background: rgba(20, 23, 28, .45);" in _rule(pc, "    .wb-ask::backdrop")
    foot = _rule(pc, "    .wb-ask .wb-hsheet__foot")
    assert "flex-direction: row-reverse;" in foot, "[그만두기][실행] — 실행이 오른쪽 끝"
    assert "display: none;" in _rule(pc, "    .wb-ask .wb-hsheet__grip")
    phone, _ = _css()
    assert ".wb-ask[open]" not in phone, "폰 아래 시트 모양은 그대로(대조군)"


def test_pc_faint_text_reaches_aa_contrast():
    pc = _pc()
    checks = [
        ("    .wb-row__when", "#ffffff"), ("    .wb-row__when", "#eaf1ff"),
        ("    .wb-st__k", "#ffffff"),
        ("    .wb-hist--muted td,\n    .wb-hist--muted a:not(.btn)", "#fafbfc"),
        ("    .wb-ingest__k", "#eef0f3"), ("    .wb-backfill__tilde", "#eef0f3"),
    ]
    for selector, bg in checks:
        body = _rule(pc, selector)
        color = re.search(r"color: (#[0-9a-f]{6})", body).group(1)
        assert _ratio(color, bg) >= 4.5, (selector, color, bg)
    assert "opacity: 1;" in _rule(pc, "    .wb-ingest__k")
    assert "opacity: 1;" in _rule(pc, "    .wb-row--stop .wb-row__body,\n    .wb-row--locked .wb-row__body")
    warn = re.search(r"\.naver-workbench \.text-warning \{ color: (#[0-9a-f]{6}) !important; \}", pc).group(1)
    assert _ratio(warn, "#ffffff") >= 4.5 and _ratio(warn, "#eef0f3") >= 4.5, "`미등록`·`구성 미상`"
    assert _ratio("#b91c1c", "#fafbfc") >= 4.5 and "#b91c1c !important" in pc
    # 스테이징 실데이터에서 찾은 것: 초록 글자(`발송처리 완료`·`주문 만듦`) 4.49:1 → 토큰을 PC 에서만 진하게.
    green = re.search(r"\.naver-workbench \{ --wb-green: (#[0-9a-f]{6}); \}", pc).group(1)
    assert _ratio(green, "#e7f6ec") >= 4.5 and _ratio("#15803d", "#e7f6ec") < 4.5, "예전 값은 미달(대조군)"


def test_pc_pipe_grey_only_touches_the_not_yet_step():
    pc = _pc()
    rule = ("    .wb-pipe__s:not(.wb-pipe__s--done):not(.wb-pipe__s--now):not(.wb-pipe__s--skip)"
            ":not(.wb-pipe__s--bad)")
    assert "color: #555e6b;" in _rule(pc, rule)
    assert "\n    .wb-pipe__s {" not in pc, "단계 색(완료 초록·지금 주황·실패 빨강)을 덮지 않는다"
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert css.count("@media (max-width: 767.98px)") == 1, "폰 블록은 하나(대조군)"
    page = TEMPLATE.read_text(encoding="utf-8")
    assert page.count("?v=20261001a") == 2 and "?v=20260930f" not in page
