"""생산 태블릿 첫 화면 작은 고침 다섯(사장님 2026-11-26) — 빼기 넷 + 찾던 글 남기기.

1 '남은 공정' 맨 위 안내 줄 빼기(태블릿만) · 2 날짜 띠 막대 빼기(태블릿만) · 3 제목 옆 날짜 · 건수 빼기(태블릿 누구든)
4 세운 화면 안내 한 줄(파트 계정 날짜 탭) · 5 찾던 글을 주소에 남기기. PC(foms_ptr=fine)는 모두 그대로.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.domains.test_production_multi_parts import _files, _get, _order, _tablet, _user, cohort  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
PARTIALS = ROOT / "templates" / "production" / "partials"
NOTE = "제작 대기 <b>"


def _pc(client) -> None:
    client.set_cookie("foms_ptr", "fine", domain="localhost")


def test_1_steps_tab_drops_the_note_line_on_tablet_but_pc_keeps_it(client, cohort):  # noqa: F811
    _order("한빛", _files("n1", 1))
    _tablet(client, _user("최보기"))
    tablet = _get(client, HOME + "?tab=steps")
    assert "fph-stepnote" not in tablet and NOTE not in tablet and "시작과 제작 완료는 작업 시트에서" not in tablet
    assert 'data-foms-home-steptab="' in tablet  # 대조군: 공정 탭은 그대로
    _pc(client)
    pc = _get(client, HOME + "?tab=steps")
    assert 'class="fph-stepnote"' in pc and NOTE in pc


def test_2_date_strip_on_tablet_is_bar_and_number_and_pc_keeps_bar(client, cohort):  # noqa: F811
    """11-26 은 태블릿 띠에서 막대를 뺐다 → 2026-11-28 흐름(사장님 답 20 · 21 · 25)부터 태블릿(새 흐름 문 안)은 거꾸로 도면 글을 빼고 막대 +
    맨 아래 색 설명(자세한 시험은 test_production_flow_c2_screen). 가운데 칸 · 숫자 칸 · 머리 글은 그대로."""
    _order("한빛", _files("n2", 1))
    _tablet(client, _user("최보기"))
    tablet = _get(client, HOME)
    strip = tablet.split('<aside class="fph-strip"', 1)[1].split("</aside>", 1)[0]
    assert "fph-sd__dw" not in strip and "<rect" in strip and 'class="fph-lg"' in strip
    rows = re.findall(r'<a class="fph-sd[ "].*?</a>', strip, re.S)
    assert len(rows) == 13
    # 줄마다 가운데 칸이 있어(비어도) 숫자 칸이 가운데로 밀리지 않는다 — 막대는 그 칸 안
    assert all('<span class="fph-sd__mid">' in r and '<span class="fph-sd__n">' in r for r in rows)
    assert all("fph-sd__bar" not in r.split('<span class="fph-sd__mid">', 1)[0] for r in rows)
    assert "만들 것 / 전체" in strip
    _pc(client)
    pc_strip = _get(client, HOME).split('<aside class="fph-strip"', 1)[1].split("</aside>", 1)[0]
    assert pc_strip.count('class="fph-sd__bar"') == 13 and "<rect" in pc_strip


@pytest.mark.parametrize("who", ["admin", "lead", "plain", "part"])
def test_3_tablet_title_has_no_date_or_total_for_anyone_and_pc_keeps_it(client, cohort, who):  # noqa: F811
    _order("한빛", _files("n3", 1))
    person = {"admin": lambda: _user("박관리", role="ADMIN", team=None), "lead": lambda: _user("박반장", lead=True),
              "plain": lambda: _user("최보기"), "part": lambda: _user("박재단", parts=["cut"])}[who]()
    _tablet(client, person)

    def bar(html: str) -> str:
        return html.split('<header class="foms-prod-home__bar">', 1)[1].split("<nav", 1)[0]

    head = bar(_get(client, HOME))
    assert "전체 " not in head and "건</span>" not in head and "· 20" not in head
    if who != "part" and who != "lead":
        assert 'class="foms-prod-home__date"' not in head  # 공장 표도 없으면 그 칸 자체가 없다
    _pc(client)
    assert re.search(r" · 전체 \d+건</span>", bar(_get(client, HOME)))


def test_4_part_account_date_tab_shows_rotate_line_like_cards_tab_but_not_other_screens(client, cohort):  # noqa: F811
    _order("한빛", _files("n4", 1))
    _tablet(client, _user("박재단", parts=["cut"]))
    line = '<p class="pp-rotate">도면은 태블릿을 가로로 두면 보여요.</p>'
    for tab in ("", "?tab=parts"):
        assert _get(client, HOME + tab).count(line) >= 1, tab
    # 도면 칸 판이 없는 화면에는 안 넣는다: 관리자 · 반장 날짜 탭(줄 목록) · 파트 계정의 다른 탭
    assert "pp-rotate" not in _get(client, HOME + "?tab=all")
    for who in (_user("박반장", lead=True), _user("박관리", role="ADMIN", team=None), _user("최보기")):
        _tablet(client, who)
        assert "pp-rotate" not in _get(client, HOME), who
    css = (ROOT / "static" / "css" / "contexts" / "production" / "parts.css").read_text(encoding="utf-8")
    # 가로(터치 · 넓은 창)에서는 안내를 감추고 도면 칸 판을 보인다 — 세로에서만 안내가 남는다
    block = css.split("@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {", 1)[1].split("\n}", 1)[0]
    assert ".pp-rotate { display: none; }" in block and ".fph-parts { display: flex;" in block


def test_5_search_text_is_kept_in_the_url_and_restored_on_open():
    js = (ROOT / "static" / "js" / "production" / "foms-production-home.js").read_text(encoding="utf-8")
    assert "searchParams.set('q', raw)" in js and "searchParams.delete('q')" in js and "replaceState" in js
    assert "searchParams.get('q')" in js and "search.value = saved" in js and "syncRenderedUrl" in js
    assert js.count("\n") <= 300  # 이 파일 300줄 상한
    # 글을 칠 때마다 주소를 갱신하고, 열 때 주소 글로 같은 거르기(apply)를 다시 돈다
    assert js.index("keepSearchUrl((search.value") < js.index("searchParams.get('q')")
    scripts = (PARTIALS / "home_scripts.html").read_text(encoding="utf-8")
    assert "foms-production-home.js') }}?v=20261127x" in scripts


def test_5_tab_links_do_not_carry_the_search_text(client, cohort):  # noqa: F811
    _order("한빛", _files("n5", 1))
    _tablet(client, _user("최보기"))
    html = _get(client, HOME + "?tab=all&q=김")
    nav = html.split('<nav class="foms-prod-home__nav"', 1)[1].split("</nav>", 1)[0]
    assert "q=" not in nav and "data-foms-home-q" in html  # 서버는 q 를 읽지 않는다 — 칸 채우기는 JS 몫
    assert _get(client, HOME + "?tab=all&q=김").count("data-foms-home-job") == html.count("data-foms-home-job")
