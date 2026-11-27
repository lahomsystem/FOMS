"""날짜 띠 셋째 판 — 사장님 답 넷(2026-11-25). :mod:`tests.domains.test_production_home_ship_dates` 에서 나눴다(파일 500줄 래칫).

1. 날짜 묶음을 말하는 글은 모두 '출고'로(주문 줄의 진짜 시공일 표 · '시공 대기' · '시공일 없음' 표는 그대로).
2. PC 늦음 줄 · 마우스 글의 날 이름 = 놓인 날의 종류(상차 · 희망일 · 시공).
3. 상차 예정일이 가장 이른 시공일보다 뒤면 잘못 적힌 것 — 시공일에 놓고 줄에는 '상차 …' 표를 그대로 보인다.
(4. 도면 마감 자동 알림은 ``test_drawing_deadline_alert_ship_dates.py``.)

날짜 단위 시험은 고정 날(2026-11-25 수), 화면 시험은 ``get_today_kst()`` 에서 센 날.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from types import SimpleNamespace

from db import db_session
from models import Order
from foms.services.datetime_kst import get_today_kst
from foms.services.production.late_rule import production_late_view
from sqlalchemy.dialects import postgresql, sqlite

from foms.services.production.ship_dates import (
    SHIP_BUILD,
    SHIP_LOAD,
    live_condition,
    loading_day,
    order_ship_dates,
    ship_fields,
)
from foms.services.production_home_read_model import build_production_home, production_home_day_plain, production_home_groups
from tests.domains.test_production_home_ship_dates import (
    HOME,
    PC,
    TODAY,
    _cell,
    _iso,
    _login,
    _md,
    _order,
    _pane,
    _row_html,
    _sd,
    _ship,
)

D = datetime.date


# --------------------------------------------------------------------------- #
# 3 — 상차 예정일이 시공일보다 뒤면 시공일에
# --------------------------------------------------------------------------- #
def test_3_상차가_가장_이른_시공일보다_뒤면_시공일_같거나_앞이면_상차() -> None:
    sd = _sd("2026-12-03, 2026-12-10")
    assert _ship(sd, regional=True, loading="2026-12-01") == [(D(2026, 12, 1), SHIP_LOAD)]   # 앞 → 상차
    assert _ship(sd, regional=True, loading="2026-12-03") == [(D(2026, 12, 3), SHIP_LOAD)]   # 같음 → 상차
    assert _ship(sd, regional=True, loading="2026-12-05") == [(D(2026, 12, 3), SHIP_BUILD), (D(2026, 12, 10), SHIP_BUILD)]
    assert _ship(_sd(items=[{"construction_date": "2026-12-04"}]), regional=True, loading="2026-12-05") == \
        [(D(2026, 12, 4), SHIP_BUILD)]  # 제품 칸 시공일도 '가장 이른 시공일'
    assert _ship(_sd(), regional=True, loading="2026-12-05") == [(D(2026, 12, 5), SHIP_LOAD)]  # 시공일 없음 → 상차
    # 시공일에 놓여도 줄 표는 적힌 상차 예정일(어긋난 것을 알게) — 판정 날 · 종류는 시공
    order = SimpleNamespace(structured_data=sd, is_regional=True, shipping_scheduled_date="2026-12-05",
                            partner_org_id=None, erp_stage_code="PRODUCTION")
    got = ship_fields(order, TODAY)
    assert got["ship_kind"] == SHIP_BUILD and got["ship_due"] == D(2026, 12, 3) and got["ship_mark"] == {"k": "상차", "md": "12/5"}
    plain = SimpleNamespace(structured_data=sd, is_regional=False, shipping_scheduled_date="2026-12-05",
                            partner_org_id=None, erp_stage_code="PRODUCTION")
    assert ship_fields(plain, TODAY)["ship_mark"] is None  # 대조군: 지방이 아니면 표 없음


def test_3_화면_상차가_시공보다_뒤인_주문은_시공일_장에_상차_표와(client) -> None:
    _login(client)
    wrong = _order("상차뒤가짜", _iso(3), regional=True, loading=_iso(6))
    pane = _pane(client.get(HOME + f"?day={_iso(3)}&view=day").get_data(as_text=True), _iso(3))
    row = _row_html(pane, wrong.id)
    # 남은 날은 상차일 기준(사장님 2026-11-27 "지방은 무조건 상차일 기준") — 시공일 표는 날만, 장 · 판정은 시공일 그대로
    plain3 = production_home_day_plain(get_today_kst() + datetime.timedelta(days=3), get_today_kst())
    assert (f'<span class="fph-due" data-foms-home-due><i>시공</i><b>{plain3}</b></span></span>'
            f'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(6)}</b><small>D-6</small></span>') in row
    later = _pane(client.get(HOME + f"?day={_iso(6)}&view=day").get_data(as_text=True), _iso(6))
    assert f"/{wrong.id}\"" not in later  # 상차 예정일 장에는 안 선다


# --------------------------------------------------------------------------- #
# 2 — PC 늦음 줄 · 마우스 글은 놓인 날의 이름으로
# --------------------------------------------------------------------------- #
def _late_row(kind: str | None, day: D) -> dict:
    row = {"id": 1, "home_view": "prod", "home_stage": "제작 대기", "home_steps": [], "ship_due": day}
    if kind is not None:
        row["ship_kind"] = kind
    return row


def test_2_늦음_줄과_마우스_글의_날_이름() -> None:
    fri = D(2026, 11, 27)  # 수 → 금 = 일하는 날 2일(제작 대기 늦음)
    assert production_late_view(_late_row("상차", fri), TODAY) == {
        "level": "late", "line": "늦음 — 상차 D-2, 아직 시작 전", "tip": "상차까지 일하는 날 2일"}
    assert production_late_view(_late_row("희망일", fri), TODAY)["line"] == "늦음 — 희망일 D-2, 아직 시작 전"
    assert production_late_view(_late_row("희망일", fri), TODAY)["tip"] == "희망일까지 일하는 날 2일"
    assert production_late_view(_late_row("상차", D(2026, 11, 26)), TODAY)["line"] == "늦음 — 내일 상차, 아직 시작 전"
    assert production_late_view(_late_row("상차", TODAY), TODAY)["line"] == "늦음 — 오늘 상차, 아직 시작 전"
    past = production_late_view(_late_row("상차", D(2026, 11, 22)), TODAY)
    assert past["line"] == "늦음 — 상차 3일 지남, 아직 시작 전" and past["tip"] == "상차일 3일 지남"
    # 대조군: 시공일로 놓인 주문 · 종류를 싣지 않은 행은 지금 글 그대로
    for kind in ("시공", None):
        view = production_late_view(_late_row(kind, fri), TODAY)
        assert view == {"level": "late", "line": "늦음 — 시공 D-2, 아직 시작 전", "tip": "시공까지 일하는 날 2일"}, kind
    assert production_late_view(_late_row(None, D(2026, 11, 22)), TODAY)["tip"] == "시공일 3일 지남"


def test_2_PC_지방_주문_늦음_줄은_상차(client) -> None:
    _login(client, role="ADMIN", team="CS")
    load = _order("상차늦음가짜", _iso(6), regional=True, loading=_iso(2))
    plain = _order("보통늦음가짜", _iso(2))
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pc = _pane(client.get(HOME + f"?day={_iso(2)}&view=day").get_data(as_text=True), _iso(2))
    cell = _cell(pc, load.id)
    assert "<small>늦음 — 상차 D-2, 아직 시작 전</small>" in cell and 'data-tip="상차까지 일하는 날 ' in cell
    assert re.search(r'aria-label="시공 [^"]*· 상차까지 일하는 날 \d일"', cell)  # 큰 날(진짜 시공일) 이름은 그대로 '시공'
    assert "<small>늦음 — 시공 D-2, 아직 시작 전</small>" in _cell(pc, plain.id)  # 대조군


# --------------------------------------------------------------------------- #
# 1 — 날짜 묶음을 말하는 글은 '출고'
# --------------------------------------------------------------------------- #
def test_1_장_제목_작은_글_마감_없음_글은_출고(client) -> None:
    _login(client)
    _order("옛날가짜", _iso(-20))
    _order("날없음가짜", None, stage="DRAWING")
    past = _pane(client.get(HOME + "?day=past&view=day").get_data(as_text=True), "past")
    assert '<h2 class="fph-pane__h">지난 출고일 (7일 넘음) <small>출고 1건 · 만들 것 1 · ' in past
    none = _pane(client.get(HOME + "?day=none&view=day").get_data(as_text=True), "none")
    assert '<h2 class="fph-pane__h">출고일 없음 <small>출고 1건 · 만들 것 0' in none
    assert '<span>출고일이 없어 마감이 없어요</span> · 도면이 오면 아래로 내려가요' in none
    # 그대로 두는 글: 줄의 시공일 표 '시공일 없음'(진짜 시공일이 없다는 뜻)
    assert '<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span>' in none
    empty = _pane(client.get(HOME + f"?day={_iso(4)}&view=day").get_data(as_text=True), _iso(4))
    assert '<p class="fph-pane__none">이 날은 출고가 없어요.</p>' in empty


def test_1_찾기_묶음_이름과_PC_내_공정_머리는_출고(client) -> None:
    user = _login(client)
    _order("옛날가짜", _iso(-20))
    _order("날없음가짜", None, stage="DRAWING")
    _order("앞날가짜", _iso(3))
    rows, stats = build_production_home(db_session, user)
    labels = [g["label"] for g in production_home_groups(rows, get_today_kst(), past_hidden=stats["past_hidden"])]
    assert labels[-2:] == ["출고일 없음", "지난 출고일 (7일 넘음)"]
    found = client.get(HOME + "?tab=all").get_data(as_text=True)
    heads = re.findall(r'data-foms-home-tog[^>]*>\s*<b>([^<]+)</b>', found)
    assert heads[-2:] == ["출고일 없음", "지난 출고일 (7일 넘음)"]
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    steps = client.get(HOME + "?tab=steps").get_data(as_text=True)
    cut = steps.split('data-foms-home-stepq="cut"', 1)[1].split("</h3>", 1)[0]
    assert cut.endswith("에 와 있는 것 0건 <small>출고일 빠른 순</small>")  # 그린 화면의 그 칸


# --------------------------------------------------------------------------- #
# 경계 SQL — 날짜 꼴이 아닌 상차 예정일은 파이썬과 같이 버린다(SQLite · PostgreSQL 같은 식)
# --------------------------------------------------------------------------- #
def test_날짜_꼴이_아닌_상차_예정일은_SQL_도_버린다(client) -> None:
    _login(client)
    today = get_today_kst()
    cutoff = (today - datetime.timedelta(days=7)).isoformat()
    cases = {
        "월일꼴_시공없음": _order("월일가짜", None, regional=True, loading=_md(1)),         # '11/26' — 파이썬: 출고일 없음
        "미정_시공없음": _order("미정가짜", None, regional=True, loading="미정"),
        "없는달_시공없음": _order("없는달가짜", None, regional=True, loading="2026-13-01"),
        "월일꼴_시공지남": _order("월일지남가짜", _iso(-20), regional=True, loading=_md(1)),  # 시공 -20 → 지난 출고일
        "시각붙음_지남": _order("시각지남가짜", _iso(3), regional=True, loading=_iso(-10) + " 09:00"),  # 앞 10자 = 상차 -10
        "시각붙음_같은날": _order("시각같은가짜", _iso(3), regional=True, loading=_iso(3) + " 09:00"),
        "앞뒤빈칸": _order("빈칸가짜", _iso(-20), regional=True, loading=f"  {_iso(2)} "),     # 상차 +2
    }
    live = {oid for (oid,) in db_session.query(Order.id).filter(live_condition(cutoff)).all()}
    for name, order in cases.items():
        db_session.refresh(order)
        days = [day for day, _kind in order_ship_dates(order)]
        python_live = not days or max(days) >= D.fromisoformat(cutoff)
        assert (order.id in live) == python_live, name
    assert [k for _d, k in order_ship_dates(cases["시각붙음_같은날"])] == [SHIP_LOAD]  # 앞 10자 = 시공일 → 상차
    assert loading_day(" 2026-11-28 09:00") == D(2026, 11, 28) and loading_day("2026-11-31") is None
    for bad in ("미정", "11/26", "2026-13-01", "２０２６-11-28", ""):
        assert loading_day(bad) is None, bad
    # 운영 PostgreSQL 에서도 같은 식(정규식 · GLOB · 글자 크기 견주기 없이 substr · trim · IN)
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        sql = str(live_condition(cutoff).compile(dialect=dialect)).lower()
        assert "substr(" in sql and "trim(" in sql and " glob " not in sql and " ~ " not in sql and "regexp" not in sql


def test_도면_크게_보기_아래_글은_하루_장만_출고() -> None:
    js = (Path(__file__).resolve().parents[2] / "static/js/production/foms-production-parts-viewer.js").read_text(
        encoding="utf-8")
    assert "var dated = /^\\d{4}-\\d{2}-\\d{2}$/.test(pane.getAttribute('data-pp-pane') || '');" in js
    assert "(day ? ' · ' + day + (dated ? ' 출고' : '') : '')" in js
