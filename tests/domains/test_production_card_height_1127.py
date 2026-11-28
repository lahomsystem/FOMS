"""도면 카드 키 일괄(사장님 2026-11-27 "도면 카드 높이 일괄로 맞춰") — parts.css 원문 계약 · 판 표시 · 핀.

한 판(전체 도면 · 작업 중 · 완료 칸)의 카드는 모두 같은 키: 판 줄 키 1fr(판 전체 = 가장 큰 카드), 화면 밖 카드 자리표시는 auto 없이
(기억 키가 1fr 로 판을 붙잡지 않게), 그 판에서 나올 수 있는 가장 큰 꼴만큼 단추 칸 빈 몫(반장 재단 판 = 단추 두 줄, 그 밖 = 한 줄 +
"내 작업" 꼬리 한 줄). 가로 터치 덩이 안에만 — PC · 세로 · 남의 공장 묶음은 그대로. 실화면 잰 값은 커밋 글.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8").replace("\r\n", "\n")
TPL = (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
STYLES = (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"
PIN = "20261128h"  # 11-27 [<파트> 같이 작업] 짝 폭으로 한 번 더 · 11-28 g: "누구에게 줄까요?" 사람 칸 굴림


def _block() -> str:
    """'도면 카드 키 일괄' 머리글 바로 뒤 가로 터치 덩이 본문."""
    head = CSS.index("도면 카드 키 일괄")
    start = CSS.index(TABLET, head) + len(TABLET)
    return CSS[start:CSS.index("\n}\n", start)]


def test_판_줄_키는_1fr_이고_가로_터치_덩이_안에만() -> None:
    body = _block()
    assert ".pp-grid[data-pp-grid] { grid-auto-rows: 1fr; }" in body
    # 덩이 밖(PC · 세로)에는 1fr · 빈 몫 규칙이 없다
    outside = CSS.replace(body, "")
    assert "grid-auto-rows" not in outside and "--pp-act-min" not in outside


def test_자리표시는_auto_없이_실제_카드보다_작게() -> None:
    body = _block()
    assert ".pp-grid[data-pp-grid] .pp-card { contain-intrinsic-size: 344px; }" in body
    assert ".pp-grid[data-pp-grid].is-need .pp-card { contain-intrinsic-size: 300px; }" in body
    assert "auto" not in re.findall(r"contain-intrinsic-size:[^;]*;", body)[0]
    # 기본 규칙(덩이 밖 · 남의 공장 묶음)은 그대로 기억 키
    assert ".pp-card { content-visibility: auto; contain-intrinsic-size: auto 344px; }" in CSS


def test_가장_큰_꼴_빈_몫() -> None:
    body = _block()
    assert "--pp-tagline: calc(19.5px * var(--foms-fs, 1) + 2px); --pp-act-min: calc(60px + var(--pp-tagline));" in body
    assert ".pp-grid[data-pp-grid]:not(.is-need) .pp-card:has([data-pp-tag]) { --pp-act-min: 60px; }" in body
    assert ".pp-finrow .pp-grid[data-pp-grid]:not(.is-need) .pp-card { --pp-act-min: 122px; }" in body
    assert ".pp-finrow .pp-grid[data-pp-grid]:not(.is-need) .pp-card:has([data-pp-tag]) { --pp-act-min: calc(122px - var(--pp-tagline)); }" in body
    assert ".pp-grid[data-pp-grid]:not(.is-need) .pp-actbox { min-height: var(--pp-act-min); justify-content: flex-end; }" in body


def test_수정_요청은_단추_칸_바로_위_말풍선은_막힌_칸_바로_위() -> None:
    body = _block()
    assert ".pp-grid[data-pp-grid]:not(.is-need) .pp-card > .pp-req { margin-top: auto; }" in body
    assert ".pp-grid[data-pp-grid]:not(.is-need) .pp-card > .pp-req:not([hidden]) + .pp-actbox { margin-top: 0; }" in body
    assert ".pp-grid[data-pp-grid]:not(.is-need) .pp-why { bottom: 62px; }" in body
    # [도면 수정 요청] 바로 뒤가 단추 칸(형제 선택자가 기댄다)
    assert re.search(r"data-pp-req-opts=[^\n]*\s*\{%- endif %\}\s*<div class=\"pp-actbox\" data-pp-actbox>", TPL)


def test_반장_재단_판_표시와_새_글_없음() -> None:
    assert '<div class="fph-parts{% if pb.writable and is_cut and not pb.mine %} pp-finrow{% endif %}" data-pp-pane="{{ d.key }}">' in TPL
    body = _block()
    assert "font-size" not in body and "::before" not in body and "::after" not in body


def test_핀() -> None:
    assert f"css/contexts/production/parts.css') }}}}?v={PIN}" in STYLES
