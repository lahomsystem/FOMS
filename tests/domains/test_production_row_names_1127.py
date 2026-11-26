"""날짜 탭 줄 — 가로 태블릿(공정 칸 아래 이름이 숨는 폭)에서도 이름 한 줄(사장님 2026-11-27 "줄 끝에 한 줄로 보이기").

글은 서버가 이미 만든 칸 아래 이름(h.name · h.tail)을 그대로 잇는다 — 새 낱말 없음. 이름은 모두 지어낸 값이다.
되돌리면 실패: 줄에 한 줄 요소가 없음 · 가로에서 다시 숨김 · 두 줄로 늘어남(말줄임 없음) · PC 에 새 요소가 번짐.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.domains.test_production_selfclaim_screens import HOME, _get, _login, _mark, _order, _user, cohort  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")


def _row(html: str, oid: int) -> str:
    return html.split(f'data-foms-home-dayrow="{oid}"', 1)[1].split("</a>", 1)[0]


def test_줄마다_이름_한_줄_작업중은_이름_없는_파트는_미정(client, cohort) -> None:
    kim, park = _user("김재단", "cut"), _user("박재단", "cut")
    order = _order("한줄집", 5)
    for j in range(3):
        _mark(order, j, "cut", "DONE", kim)
    _mark(order, 3, "cut", "NEED", park)
    idle = _order("미정집", 2)
    _login(client, _user("반장"))
    html = _get(client, HOME)
    line = re.search(r'<span class="fph-dr__hl" aria-hidden="true">(.*?)</span></span>', _row(html, order.id), re.S).group(0)
    assert "재단 <b>박재단</b>" in line and line.count(" · ") == 3
    assert line.count('class="fph-hl is-none">') == 3 and "엣지 <b>미정</b>" in line and "검수 <b>미정</b>" in line
    idle_line = re.search(r'<span class="fph-dr__hl".*?</span></span>', _row(html, idle.id), re.S).group(0)
    assert idle_line.count("<b>미정</b>") == 4 and "재단 <b>미정</b>" in idle_line
    # 한 줄 요소는 공정 칸이 있는 줄(has-hd)에만 — 공정 칸 없는 줄에는 없다
    assert html.count('class="fph-dr__hl"') == html.count('class="fph-dr__steps has-hd"') >= 2


def test_PC_는_지금_그대로(client, cohort) -> None:
    kim = _user("김재단", "cut")
    order = _order("피씨집", 2)
    _mark(order, 0, "cut", "NEED", kim)
    _login(client, _user("반장"), ptr="fine")
    html = _get(client, HOME)
    assert "fph-dr__hl" not in html and "fph-hl" not in html


def test_CSS_가로에서_숨기지_않고_한_줄_말줄임() -> None:
    assert ".fph-dr__hl { display: none; }" in CSS  # 기본 · 세로는 숨김
    hidden = CSS.split("@container fph-pane (max-width: calc(190px + 4 * 4.75rem + 26.75rem - 0.02px)) {", 1)[1].split("\n  }\n", 1)[0]
    shown = re.search(r"\.fph-dr__hl \{([^}]*)\}", hidden).group(1)
    assert "display: block" in shown and "white-space: nowrap" in shown and "text-overflow: ellipsis" in shown and "overflow: hidden" in shown
    assert "calc(15px * var(--foms-fs, 1))" in shown
    # 폰 · 세로 덩이에는 한 줄 요소를 켜는 규칙이 없다
    phone = CSS.split("@media (max-width: 991.98px) {", 1)[1]
    assert "fph-dr__hl" not in phone
    # 색은 칸 아래 이름과 같은 토큰
    for token in ("--fph-holder)", "--fph-holder-done)", "--fph-holder-none)", "--fph-old-700)"):
        assert re.search(r"\.fph-hl[^{]*\{[^}]*" + re.escape(token), CSS), token
