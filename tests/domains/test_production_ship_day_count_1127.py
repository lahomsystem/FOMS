"""상차 주문의 남은 날은 상차일 기준(사장님 2026-11-27 "상차일 기준으로 바꾸기" — '시공 11/30 (월) · 상차 11/27 내일').

- 상차 예정일로 놓인 주문(``ship_kind`` '상차'): 남은 날 글(오늘 · 내일 · D-n · n일 지남)과 그 색을 상차일로 세어 상차 표 뒤에,
  시공일 표는 날만. 작은 칸 · 바뀐 것(sub=False 자리)은 시공일 표처럼 오늘 · 내일만.
- 그대로(음성 대조군): 보통 주문 · 희망일 주문 · PC ① 칸.
- 뒷일(사장님 2026-11-27 "PC는 그대로" · "지방은 무조건 상차일 기준"): 상차 예정일이 시공일보다 뒤라 시공일 장에 선 지방 주문도
  태블릿 글은 상차일 기준(장 · 판정은 시공일 그대로), '남은 공정' 줄 시공 칸 · 곧 올 것 날 칸도 날짜 탭과 같은 글.

날짜는 ``get_today_kst()`` 에서 센다(CI 는 UTC — ``date.today()`` 금지).
"""
from __future__ import annotations

import datetime
import re

from app import app as flask_app
from db import db_session
from models import ProductionRun
from foms.services import production_home_read_model as home_read_model
from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_read_model import build_production_home
from tests.domains.test_production_home_ship_dates import (
    HOME,
    PC,
    _iso,
    _login,
    _md,
    _order,
    _pane,
    _partner,
    _row_html,
)


def _label(off: int) -> str:
    """시공일 표 글(production_home_day 그대로 — '내일 11/28 (토)' · '11/30 (월)')."""
    return home_read_model.production_home_day(get_today_kst() + datetime.timedelta(days=off), get_today_kst())["label"]


def _plain(off: int) -> str:
    """남은 날을 뺀 시공일 표 글 '11/30 (월)'."""
    day = get_today_kst() + datetime.timedelta(days=off)
    return f"{day.month}/{day.day} ({'월화수목금토일'[day.weekday()]})"


def _due(row: str) -> str:
    return re.search(r'<span class="fph-due[^"]*" data-foms-home-due>.*?</span>', row).group(0)


def _ship(row: str) -> str:
    return re.search(r'<span class="fph-due[^"]*" data-foms-home-ship>.*?</span>', row).group(0)


def test_태블릿_날짜_탭_상차_주문은_상차_표_뒤에_내일_시공일_표에는_D_n_없음(client) -> None:
    _login(client)
    load = _order("상차내일가짜", _iso(4), regional=True, loading=_iso(1))
    plain = _order("보통가짜", _iso(4))
    wish = _order("희망가짜", None, stage="DRAWING", partner=_partner(), wish=_iso(4))
    wrong = _order("상차뒤가짜", _iso(4), regional=True, loading=_iso(6))  # 상차가 시공보다 뒤 → 시공일에 놓임
    tomorrow = _pane(client.get(HOME + f"?day={_iso(1)}&view=day").get_data(as_text=True), _iso(1))
    row = _row_html(tomorrow, load.id)
    assert _due(row) == f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_plain(4)}</b></span>'
    assert _ship(row) == f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(1)}</b><small>내일</small></span>'
    assert "D-4" not in row and "D-1" not in row
    day4 = _pane(client.get(HOME + f"?day={_iso(4)}&view=day").get_data(as_text=True), _iso(4))
    # 음성 대조군: 보통 주문 — 시공일 표에 D-4, 상차 표 없음
    plain_row = _row_html(day4, plain.id)
    assert _due(plain_row) == (f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_label(4)}</b>'
                               '<small>D-4</small></span>') and "data-foms-home-ship" not in plain_row
    # 음성 대조군: 희망일 주문(기다림 칸) — 지금 그대로(남은 날 글 없음)
    wish_row = _row_html(day4, wish.id)
    assert _ship(wish_row) == f'<span class="fph-due" data-foms-home-ship><i>희망일</i><b>{_md(4)}</b></span>'
    assert _due(wish_row) == '<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span>'
    # 상차가 시공보다 뒤라 시공일(+4) 장에 선 지방 주문 — 장은 시공일 그대로, 남은 날은 상차일 기준("지방은 무조건")
    wrong_row = _row_html(day4, wrong.id)
    assert _due(wrong_row) == f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_plain(4)}</b></span>'
    assert _ship(wrong_row) == f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(6)}</b><small>D-6</small></span>'
    six = _pane(client.get(HOME + f"?day={_iso(6)}&view=day").get_data(as_text=True), _iso(6))
    assert f"/{wrong.id}\"" not in six  # 상차 예정일 장에는 여전히 안 선다


def test_찾기_탭도_상차_주문은_상차일_기준(client) -> None:
    _login(client)
    load = _order("상차찾기가짜", _iso(4), regional=True, loading=_iso(1))
    plain = _order("보통찾기가짜", _iso(4))
    html = client.get(HOME + "?tab=all").get_data(as_text=True)
    row = html.split(f"<b>상차찾기가짜</b> <small>#{load.id}</small>", 1)[1].split("</a>", 1)[0]
    assert _due(row) == f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_plain(4)}</b></span>'
    assert _ship(row) == f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(1)}</b><small>내일</small></span>'
    prow = html.split(f"<b>보통찾기가짜</b> <small>#{plain.id}</small>", 1)[1].split("</a>", 1)[0]
    assert "<small>D-4</small>" in _due(prow) and "data-foms-home-ship" not in prow


def test_PC_시공일_칸은_그대로(client) -> None:
    _login(client, role="ADMIN", team="CS")
    load = _order("상차PC가짜", _iso(4), regional=True, loading=_iso(1))
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pane = client.get(HOME + f"?day={_iso(1)}&view=day").get_data(as_text=True)
    cell = pane.split(f'data-foms-home-dayrow="{load.id}"', 1)[1].split('<span class="fpc-st', 1)[0]
    assert f"<b>{_plain(4)}</b><span>D-4</span><span>상차 {_md(1)}</span>" in cell  # 시공일 기준 D-n · 상차 표 그대로
    assert "<small>내일</small>" not in cell and "data-foms-home-ship" not in cell


def test_상차일_오늘_지남_색과_읽기_모델(client) -> None:
    user = _login(client)
    today_load = _order("상차오늘가짜", _iso(3), regional=True, loading=_iso(0))
    past_load = _order("상차지남가짜", _iso(3), regional=True, loading=_iso(-2))
    far_load = _order("상차멀리가짜", _iso(9), regional=True, loading=_iso(5))
    no_build = _order("상차만가짜", None, regional=True, loading=_iso(2))
    wish = _order("희망모델가짜", None, stage="DRAWING", partner=_partner(), wish=_iso(4))
    rows, _stats = build_production_home(db_session, user)
    by = {r["id"]: r for r in rows}
    assert by[today_load.id]["ship_mark"] == {"k": "상차", "md": _md(0), "sub": "오늘", "state": "today", "build_md": _plain(3)}
    assert by[past_load.id]["ship_mark"] == {"k": "상차", "md": _md(-2), "sub": "2일 지남", "state": "past", "build_md": _plain(3)}
    assert by[far_load.id]["ship_mark"] == {"k": "상차", "md": _md(5), "sub": "D-5", "state": "", "build_md": _plain(9)}
    assert by[no_build.id]["ship_mark"]["build_md"] == "" and by[no_build.id]["day_label"] == "시공일 없음"
    assert by[wish.id]["ship_mark"] == {"k": "희망일", "md": _md(4)}  # 희망일은 그대로
    # 행의 시공일 표 값(PC · '내 공정' 줄이 쓴다)은 그대로 시공일 기준
    assert by[far_load.id]["day_label"] == _label(9) and by[far_load.id]["day_sub"] == "D-9"
    recent = _pane(client.get(HOME + "?day=recent&view=day").get_data(as_text=True), "recent")
    assert _ship(_row_html(recent, today_load.id)) == (
        f'<span class="fph-due is-today" data-foms-home-ship><i>상차</i><b>{_md(0)}</b><small>오늘</small></span>')
    assert _ship(_row_html(recent, past_load.id)) == (
        f'<span class="fph-due is-past" data-foms-home-ship><i>상차</i><b>{_md(-2)}</b><small>2일 지남</small></span>')
    assert _due(_row_html(recent, past_load.id)) == (
        f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_plain(3)}</b></span>')
    day2 = _pane(client.get(HOME + f"?day={_iso(2)}&view=day").get_data(as_text=True), _iso(2))
    nb = _row_html(day2, no_build.id)
    assert _due(nb) == '<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span>'
    assert "<small>D-2</small>" in _ship(nb)


def test_작은_칸_자리는_오늘_내일만_D_n_은_뺀다() -> None:
    """sub=False 자리(제작 완료 · 기다림 칸 · 바뀐 것) — 시공일 표가 D-n 을 빼는 것과 같게 상차 표도 오늘 · 내일만."""
    with flask_app.app_context():
        mod = flask_app.jinja_env.get_template("production/partials/home_date_macros.html").module

        def mark(sub: str, state: str = "") -> dict:
            return {"day_label": "내일 11/28 (토)", "day_sub": "", "day_is_today": False,
                    "ship_mark": {"k": "상차", "md": "11/27", "sub": sub, "state": state, "build_md": "11/28 (토)"}}

        assert str(mod.fph_due(mark("D-3"), False)) == (
            '<span class="fph-due" data-foms-home-due><i>시공</i><b>11/28 (토)</b></span>'
            '<span class="fph-due" data-foms-home-ship><i>상차</i><b>11/27</b></span>')
        assert str(mod.fph_due(mark("내일"), False)).endswith('<b>11/27</b><small>내일</small></span>')
        assert str(mod.fph_due(mark("D-3"))).endswith('<b>11/27</b><small>D-3</small></span>')
        # 음성 대조군: 희망일 · 보통 주문은 지금 글 그대로
        wish = {"day_label": "시공일 없음", "day_sub": "", "ship_mark": {"k": "희망일", "md": "12/3"}}
        assert str(mod.fph_due(wish)) == ('<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span>'
                                          '<span class="fph-due" data-foms-home-ship><i>희망일</i><b>12/3</b></span>')
        plain = {"day_label": "11/30 (월)", "day_sub": "D-3", "ship_mark": None}
        assert str(mod.fph_due(plain)) == '<span class="fph-due" data-foms-home-due><i>시공</i><b>11/30 (월)</b><small>D-3</small></span>'


# --------------------------------------------------------------------------- #
# 뒷일 — '남은 공정' 탭 · 상차가 시공보다 늦은 지방 주문 · PC 그대로
# --------------------------------------------------------------------------- #
def _run(order) -> None:
    """제작 중(회차 있음) — 재단이 첫 미완 공정이라 '남은 공정' 재단 줄에 선다."""
    db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()


def _qrow(html: str, oid: int) -> str:
    return html.split(f'data-foms-home-qrow="{oid}"', 1)[1].split('data-foms-home-qrow=', 1)[0]


def _qdue(row: str) -> str:
    return re.search(r'<span class="fph-qr__due[^"]*">.*?</span>(?:</span>)?', row).group(0)


def test_남은_공정_줄과_곧_올_것도_지방_상차는_상차일_기준(client) -> None:
    _login(client)
    load = _order("상차줄가짜", _iso(4), regional=True, loading=_iso(1))
    wrong = _order("늦은상차줄가짜", _iso(3), regional=True, loading=_iso(5))
    past = _order("지난상차줄가짜", _iso(3), regional=True, loading=_iso(-2))
    plain = _order("보통줄가짜", _iso(4))
    plain_past = _order("지난보통줄가짜", _iso(-1))
    for o in (load, wrong, past, plain, plain_past):
        _run(o)
    soon = _order("상차곧가짜", _iso(4), regional=True, loading=_iso(1))   # 회차 없음 = 제작 대기 → 재단 '곧 올 것'
    soon_plain = _order("보통곧가짜", _iso(4))
    html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    cut = html.split('data-foms-home-stepq="cut"', 1)[1].split('data-foms-home-stepq=', 1)[0]
    ship1 = f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(1)}</b><small>내일</small></span>'
    assert _qdue(_qrow(cut, load.id)) == f'<span class="fph-qr__due">시공<b>{_plain(4)}</b>{ship1}</span>'
    assert _qdue(_qrow(cut, wrong.id)) == (
        f'<span class="fph-qr__due">시공<b>{_plain(3)}</b><span class="fph-due" data-foms-home-ship><i>상차</i>'
        f'<b>{_md(5)}</b><small>D-5</small></span></span>')
    # 상차일이 지났으면 상차 표가 빨강(is-past) — 시공 칸은 색 없이 날만
    assert _qdue(_qrow(cut, past.id)) == (
        f'<span class="fph-qr__due">시공<b>{_plain(3)}</b><span class="fph-due is-past" data-foms-home-ship><i>상차</i>'
        f'<b>{_md(-2)}</b><small>2일 지남</small></span></span>')
    # 음성 대조군: 보통 주문은 지금 글 그대로(시공 칸에 날짜 탭 표 없음 · 지난 집은 빨강 + 'n일 지남')
    assert _qdue(_qrow(cut, plain.id)) == f'<span class="fph-qr__due">시공<b>{_label(4)}</b></span>'
    assert _qdue(_qrow(cut, plain_past.id)) == (
        f'<span class="fph-qr__due is-past">시공<b>{_label(-1)}</b><small>1일 지남</small></span>')
    # 줄 순서는 그대로 출고일 순(지난 상차 -2 · 보통 지남 -1 · 상차 +1 · 늦은 상차는 시공 +3 · 보통 +4)
    order = [int(m) for m in re.findall(r'data-foms-home-qrow="(\d+)"', cut)]
    assert order == [past.id, plain_past.id, load.id, wrong.id, plain.id]
    # 곧 올 것(제작 대기 → 재단): 날 칸 = 시공일 날 + 상차 표, 보통 주문은 그대로
    nx = cut.split('class="fph-q__nextlist"', 1)[1]
    soon_card = nx.split(f"/{soon.id}\"", 1)[1].split("</a>", 1)[0]
    assert f"<em>{_plain(4)}{ship1}</em>" in soon_card
    plain_card = nx.split(f"/{soon_plain.id}\"", 1)[1].split("</a>", 1)[0]
    assert f"<em>{_label(4)}</em>" in plain_card


def test_시공일이_여럿인_늦은_상차_주문은_장마다_그_장의_시공일_글(client) -> None:
    """상차(+5)가 가장 이른 시공일(+3)보다 뒤 → 시공 +3 · +8 장에 선다. 상차 표 남은 날은 둘 다 상차일, 시공일 글은 그 장의 날."""
    _login(client)
    two = _order("두날상차가짜", f"{_iso(3)}, {_iso(8)}", regional=True, loading=_iso(5))
    ship5 = f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(5)}</b><small>D-5</small></span>'
    for off in (3, 8):
        row = _row_html(_pane(client.get(HOME + f"?day={_iso(off)}&view=day").get_data(as_text=True), _iso(off)), two.id)
        assert _due(row) == f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{_plain(off)}</b></span>', off
        assert _ship(row) == ship5, off


def test_PC_는_늦은_상차_주문도_남은_공정도_그대로(client) -> None:
    _login(client, role="ADMIN", team="CS")
    wrong = _order("늦은상차PC가짜", _iso(3), regional=True, loading=_iso(5))
    load = _order("상차공정PC가짜", _iso(4), regional=True, loading=_iso(1))
    _run(load)
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pane = client.get(HOME + f"?day={_iso(3)}&view=day").get_data(as_text=True)
    cell = pane.split(f'data-foms-home-dayrow="{wrong.id}"', 1)[1].split('<span class="fpc-st', 1)[0]
    assert f"<b>{_plain(3)}</b><span>D-3</span><span>상차 {_md(5)}</span>" in cell  # 시공일 기준 D-n · 상차 표 그대로
    assert "data-foms-home-ship" not in cell and "D-5" not in cell
    steps = client.get(HOME + "?tab=steps").get_data(as_text=True)
    assert "data-foms-home-ship" not in steps and 'class="fph-qr__due' not in steps  # PC 는 PC 줄(home_pc_steps.html)
    sheet = client.get(f"/erp/production/sheet/{load.id}").get_data(as_text=True)
    head = re.search(r'<span class="foms-prod-page__due[^>]*data-foms-pc-due>(.*?)</span>', sheet).group(1)
    assert head == f"시공 {_plain(4)} · <b>D-4</b> · 상차 {_md(1)}"  # PC 작업 시트 머리 그대로(시공일 기준)
