"""생산 첫 화면 — 모든 줄 · 칸 · 카드 · 판에 시공일이 늘 보인다(사용자 11-21 "시공일 표기 필요. 아주 중요한 정보야").

전에는 날짜 탭 고른 날 큰 줄에 날이 없었고, 바뀐 줄은 '바뀜' 이 날 자리를 차지했다(태블릿 실화면 "제작 대기 / 바뀜").
지금은 시공일 표(``home_date_macros.fph_due``) 하나를 날짜 탭 큰 줄 · 작은 칸 · 미리 보기 · 도면 카드 · 내 공정 판 · 찾기 · 받은함이
같이 쓰고, '바뀜' 은 단계 칸에 따로 남는다. 값은 첫 화면 행이 이미 가진 ``day_label`` · ``day_sub`` 그대로(새 읽기 없음).
"""
from __future__ import annotations

import datetime
import re

import pytest

from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_read_model import production_home_day
from tests.domains.test_production_home import _add_drawing_transfer
from tests.domains.test_production_home_tabs import HOME, _add_order, _make_user, _pane
from tests.domains.test_production_parts_screen import _files, _login, _order, _today_pane, _user
from tests.support.production_home_step_panel_seed import TABLET, add_order, get_html, login, set_cookies

_DUE = re.compile(r'<span class="fph-due([^"]*)" data-foms-home-due>(?:<i>시공</i>)?<b>([^<]+)</b>(?:<small>([^<]+)</small>)?</span>')


def _label(off: int | None) -> str:
    day = None if off is None else get_today_kst() + datetime.timedelta(days=off)
    return production_home_day(day, get_today_kst())["label"]


def _block(html: str, start: str, end: str = "</a>") -> str:
    return html.split(start, 1)[1].split(end, 1)[0]


def _dues(fragment: str) -> list[tuple[str, str, str]]:
    return [(cls.strip(), label, sub or "") for cls, label, sub in _DUE.findall(fragment)]


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def test_날짜_탭_고른_날_큰_줄과_작은_칸에_시공일이_늘_보이고_바뀜은_날을_안_가린다(client) -> None:
    _make_user(client, "sg_date", "PRODUCTION")
    today_row = _add_order("PRODUCTION", "오늘집", 0, with_run=True)
    changed = _add_order("PRODUCTION", "바뀐집", 0, with_run=True)
    _add_drawing_transfer(changed)
    wait = _add_order("DRAWING", "도면집", 0)
    done = _add_order("CONSTRUCTION", "완료집", 0)
    later = _add_order("PRODUCTION", "모레집", 3, with_run=True)
    key = get_today_kst().isoformat()
    pane = _pane(client.get(HOME + f"?day={key}").get_data(as_text=True), key)

    row = _block(pane, f'data-foms-home-dayrow="{today_row.id}">')
    assert _dues(row) == [("is-today", _label(0), "")] and _label(0).startswith("오늘 ")
    # 바뀐 줄: 단계 칸에 '바뀜' + 이름 칸에 시공일 — 둘 다
    row = _block(pane, f'data-foms-home-dayrow="{changed.id}">')
    assert re.search(r'<span class="fph-dr__sg">[^<]+<small>바뀜</small></span>', row)
    assert _dues(row) == [("is-today", _label(0), "")]
    assert row.index("<small>#%d</small>" % changed.id) < row.index("data-foms-home-due")  # 이름 · 번호 뒤
    # 작은 칸(도면·컨펌 기다림 · 제작 완료) — 날이 맨 앞
    for oid, name in ((wait.id, "도면집"), (done.id, "완료집")):
        chip = re.search(rf'<a class="fph-wi[^"]*" href="[^"]*/{oid}[^"]*">(.*?)</a>', pane).group(1)
        assert chip.startswith('<span class="fph-due is-today" data-foms-home-due>')
        assert f'<b class="fph-wi__nm">{name}</b>' in chip and _dues(chip) == [("is-today", _label(0), "")]
    # 미리 보기 줄(다음에 만들 것)도 같은 표 + D-n
    row = _block(pane, f'data-foms-home-dayrow="{later.id}">')
    assert _dues(row) == [("", _label(3), "D-3")]


def test_내일_지난_날_시공일_없음_장도_줄마다_날을_단다(client) -> None:
    _make_user(client, "sg_days", "PRODUCTION")
    tomorrow = _add_order("PRODUCTION", "내일집", 1, with_run=True)
    past = _add_order("PRODUCTION", "밀린집", -2, with_run=True)
    none = _add_order("PRODUCTION", "날없는집", None, with_run=True)
    none_wait = _add_order("DRAWING", "날없는도면", None)

    key = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    row = _block(_pane(client.get(HOME + f"?day={key}").get_data(as_text=True), key), f'data-foms-home-dayrow="{tomorrow.id}">')
    assert _dues(row) == [("", _label(1), "")] and _label(1).startswith("내일 ")
    pane = _pane(client.get(HOME + "?day=recent&view=day").get_data(as_text=True), "recent")
    assert _dues(_block(pane, f'data-foms-home-dayrow="{past.id}">')) == [("is-past", _label(-2), "2일 지남")]
    pane = _pane(client.get(HOME + "?day=none&view=day").get_data(as_text=True), "none")
    # 시공일 없음 = '시공' 머리말 없이 노란 점선 표(무채색 금지)
    row = _block(pane, f'data-foms-home-dayrow="{none.id}">')
    assert '<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span>' in row
    chip = re.search(rf'<a class="fph-wi[^"]*" href="[^"]*/{none_wait.id}[^"]*">(.*?)</a>', pane).group(1)
    assert _dues(chip) == [("is-none", "시공일 없음", "")]


def test_찾기_줄마다_시공일_지난_시공일_묶음_안에서도(client) -> None:
    """찾기 탭 묶음 머리줄이 화면 밖으로 굴러가도, '지난 시공일(7일 넘음)' 묶음 안에서도 줄마다 날이 보인다."""
    _make_user(client, "sg_all", "PRODUCTION")
    a = _add_order("PRODUCTION", "앞날찾기", 4, with_run=True)
    old = _add_order("PRODUCTION", "옛찾기", -20, with_run=True)
    n = _add_order("DRAWING", "없음찾기", None)
    _add_drawing_transfer(a)
    html = client.get(HOME + "?tab=all").get_data(as_text=True)
    for order, want in ((a, ("", _label(4), "D-4")), (old, ("is-past", _label(-20), "20일 지남")), (n, ("is-none", "시공일 없음", ""))):
        name = _block(html, f'<span class="foms-prod-home__name"><b>{order.customer_name}</b> <small>#{order.id}</small>', "</span></span>")
        assert _dues(name + "</span>") == [want], order.customer_name
    # 바뀐 줄은 바뀐 글 줄도 그대로
    assert "도면 재전달" in _block(html, f'<b>앞날찾기</b> <small>#{a.id}</small>', "</a>")


def test_바뀐_것_받은함_장에_시공일_표(client) -> None:
    _make_user(client, "sg_chg", "PRODUCTION")
    a = _add_order("PRODUCTION", "받은함집", 2, with_run=True)
    _add_drawing_transfer(a)
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    card = _block(html, f'data-foms-home-inbox="{a.id}"', "확인했어요")
    name = _block(card, 'class="fph-al__name">', "</div>")
    assert name.startswith(f"받은함집 <small>#{a.id}</small>") and _dues(name) == [("", _label(2), "")]
    # 날은 이름 줄 표로 옮겼다 — 아래 작은 글에 두 번 쓰지 않는다
    assert _label(2) not in _block(card, 'class="fph-al__meta">', "</div>")


def test_내_공정_줄과_오른쪽_판에_시공일(client, cohort) -> None:
    login(client, "공정사람")
    a = add_order("판첫집", 1)
    b = add_order("판둘집", 4)
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    cut = html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0]
    for order, off, sub in ((a, 1, ""), (b, 4, "D-4")):
        row = _block(cut, f'data-foms-home-qrow="{order.id}"', "</div>\n  ")
        assert f'<span class="fph-qr__due">시공<b>{_label(off)}</b></span>' in row
        pane = _block(cut, f'data-foms-step-pane="{order.id}"', "</h2>")
        assert _dues(pane) == [("", _label(off), sub)]


def test_도면_카드와_카드_판_작은_칸에_시공일(client, cohort) -> None:
    me = _user("김재단", part="cut")
    a = _order("카드집", _files("sga", 2))
    wait = _order("카드도면집", [], stage="DRAWING")
    nodraw = _order("카드빈집", [])
    _login(client, me)
    pane = _today_pane(get_html(client, HOME))
    block = pane.split('class="fph-parts"')[1].split('class="fph-pane__now"')[0]
    cards = re.findall(rf'data-pp-card data-order-id="{a.id}".*?</article>', block, re.S)
    assert len(cards) == 2
    for card in cards:
        # 이름 줄(pp-ln) 바로 아래 제 줄 — 품목 줄 폭을 안 뺏는다
        between = _block(card, '<span class="pp-no">', '<span class="fph-dr__pr pp-item">')
        assert _dues(between) == [("is-today", _label(0), "")]
    for oid, tail in ((wait.id, "붙박이장"), (nodraw.id, "도면 없음")):
        chip = re.search(rf'<a class="fph-wi pp-wait" href="[^"]*/{oid}[^"]*">(.*?)</a>', block).group(1)
        assert _dues(chip) == [("is-today", _label(0), "")] and chip.endswith(f"<small>#{oid} · {tail}</small>")


def test_시공일_표_CSS_는_줄지_않고_글자_손잡이를_따른다() -> None:
    from tests.domains.test_production_home_tabs import ROOT

    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    rule = css.split("\n.fph-due {", 1)[1].split("}", 1)[0]
    assert "flex-shrink: 0;" in rule and "white-space: nowrap;" in rule and "calc(15px * var(--foms-fs, 1))" in rule
    # 오늘 · 지난 날 · 없음은 색이 다르다(무채색 금지)
    for state in (".fph-due.is-today {", ".fph-due.is-past {", ".fph-due.is-none {"):
        assert state in css
    # 이름 칸 안 b · small 규칙은 바로 아래 자식만 — 시공일 표 안 b 가 말줄임으로 줄지 않게
    for sel in (".fph-dr__nm > b {", ".fph-dr__nm > small {", ".foms-prod-home__name > b {", ".fph-wi > small {"):
        assert sel in css
    assert ".fph-dr__nm b {" not in css and ".fph-wi small {" not in css
