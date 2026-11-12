"""태블릿 시공 탭 다듬기 계약(설계서 tablet-production-ui §13.10, 결정 D43 — 시안 4차 a51 · a52 · a53).

- a53 생산 진행: 공정 기록이 있으면 출고 칸 `생산 n/4`, 없으면 `생산중`(0/4 라고 말하지 않는다). 상세는 같은 말 한 번 —
  가운데 `아직 생산 중이에요 · 조립까지 끝남`, 오른쪽 안내 줄은 `완료 사진 n장` 만.
- a52 AS 방문 집: as_visit 날짜로만 든다(AS 상태 + 시공일만 = 지금처럼 뺌). 줄 `AS 방문` · 출고 `-`, 상세는 단추 대신 `AS 방문 집이에요`.
- a51 날짜 미정 집: 시공대기 · 시공중 + 시공 일정 줄 없음(생산 단계 · AS · 시공일 있는 집은 안 듦), 수는 쿼리 A 와 한 문장.
대조군은 모두 같은 자료 안에서 고른다(들지 말아야 할 집을 같이 만든다). 이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import datetime
import itertools
import re

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.common import dashboard_cache as dc
from foms.services.construction import tablet_first as tf
from foms.services.construction import tablet_view as tv
from foms.services.datetime_kst import get_today_kst
from models import Order, OrderScheduleDate, User

URL = "/erp/construction/dashboard"
SHELL = {"X-FOMS-ERP-SHELL": "1"}
_seq = itertools.count(1)
STEPS_3 = [{"key": "cut", "done": True}, {"key": "edge", "done": True},
           {"key": "assemble", "done": True}, {"key": "inspect", "done": False}]


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _d(n: int = 0) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(customer: str, *, kinds: dict[str, str] | None = None, stage: str = "CONSTRUCTION", status: str | None = None,
           workers: list[str] | None = None, steps: list | None = None) -> int:
    """kinds = {'construction': 날짜, 'as_visit': 날짜} — 일정 줄. status 없으면 단계와 같은 값."""
    sd = {
        "parties": {"manager": {"name": "가짜영업"}, "customer": {"name": customer}, "orderer": {"name": "가짜대리점"}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "1200", "quantity": 1}],
        "site": {"address_full": "가짜시 가짜구 시공로 1"},
        "shipment": {"construction_workers": workers or []},
    }
    if steps is not None:
        sd["production"] = {"steps": steps}
    order = Order(received_date=_d(), customer_name=customer, phone="010-0000-0000", address="가짜시 가짜구 시공로 1",
                  product="가짜장", status=status or stage, manager_name="가짜영업", is_erp_order=True,
                  structured_data=sd, erp_stage_code=stage)
    db_session.add(order)
    db_session.flush()
    for kind, day in (kinds or {}).items():
        db_session.add(OrderScheduleDate(order_id=order.id, kind=kind, date=day, source="beta_schedule"))
    db_session.commit()
    return order.id


def _login(client, monkeypatch, *, role: str = "ADMIN", team: str = "CS", name: str | None = None) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    n = next(_seq)
    user = User(username=f"cons_d43_{n}", password=generate_password_hash("x"), role=role, team=team,
                name=name or f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _get(client, query: str = "") -> str:
    resp = client.get(URL + query, headers=SHELL)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _cut(body: str, start: str, end: str) -> str:
    i = body.index(start)
    return body[i:body.index(end, i)]


def _first(body: str) -> str:
    return _cut(body, 'class="foms-cons-first"', "</section>")


def _row(first: str, oid: int) -> str:
    return _cut(first, f'data-order-id="{oid}"', "</a>")


def _own(body: str, marker: str, oid: int, end: str) -> str:
    """그 집 하나의 칸만(다음 집 칸이나 닫는 표 전까지) — 뒤 집의 단추를 잘못 세지 않게."""
    i = body.index(f'{marker}="{oid}"')
    nxt = body.find(f'{marker}="', i + 1)
    stop = body.index(end, i)
    return body[i:nxt if 0 < nxt < stop else stop]


def _panel(body: str, oid: int) -> str:
    return _own(body, "data-cwork-panel", oid, "</section>")


def _confirm(body: str, oid: int) -> str:
    return _own(body, "data-cwork-confirm", oid, "</aside>")


# ── a53 생산 진행 ────────────────────────────────────────────────────────────

def test_production_progress_shown_only_when_recorded(client, monkeypatch) -> None:
    rec = _order("가짜생산기록", kinds={"construction": _d(0)}, stage="PRODUCTION", steps=STEPS_3)
    bare = _order("가짜생산없음", kinds={"construction": _d(0)}, stage="PRODUCTION")
    paint = _order("가짜도장만", kinds={"construction": _d(0)}, stage="PRODUCTION",
                   steps=[{"key": "paint", "done": True}])
    _login(client, monkeypatch)
    first = _first(_get(client, f"?date={_d(0)}&worker="))
    assert "생산 3/4" in _row(first, rec)
    for oid in (bare, paint):  # 대조군: 기록이 없으면 0/4 라고 말하지 않는다
        assert "생산중" in _row(first, oid) and "/4" not in _row(first, oid)
    assert "0/4" not in first


def test_production_detail_says_it_once(client, monkeypatch) -> None:
    rec = _order("가짜생산상세", kinds={"construction": _d(1)}, stage="PRODUCTION", steps=STEPS_3)
    bare = _order("가짜생산상세없음", kinds={"construction": _d(1)}, stage="PRODUCTION")
    _login(client, monkeypatch)
    body = _get(client, f"?focus_order={rec}&date={_d(1)}&worker=")
    assert "아직 생산 중이에요 · 조립까지 끝남" in _panel(body, rec)
    assert 'data-action="startConstruction"' not in _panel(body, rec)
    right = _confirm(body, rec)
    assert "완료 사진 0장" in right and "아직 생산 중이에요" not in right  # 같은 말 한 번
    assert re.search(r'data-cwork-note>아직 생산 중이에요</p>', _panel(body, bare))  # 기록 없으면 앞말만


def test_view_only_account_right_note_is_photo_count_only(client, monkeypatch) -> None:
    oid = _order("가짜보기만", kinds={"construction": _d(0)})
    _login(client, monkeypatch, role="STAFF", team="SHIPMENT")
    body = _get(client, f"?focus_order={oid}&date={_d(0)}")
    assert "보기만 할 수 있어요" in _panel(body, oid)
    right = _confirm(body, oid)
    assert "완료 사진 0장" in right and "보기만 할 수 있어요" not in right


def test_production_progress_unit() -> None:
    assert tf.production_progress({}) is None
    assert tf.production_progress({"production": {"steps": []}}) is None
    assert tf.production_progress({"production": {"steps": STEPS_3}}) == {"done": 3, "total": 4, "last": "조립"}
    assert tf.production_note({"production": {"steps": [{"key": "cut", "done": False}]}}) == "아직 생산 중이에요"


# ── a52 AS 방문 집 ───────────────────────────────────────────────────────────

def test_as_visit_house_joins_first_screen_by_as_visit_date_only(client, monkeypatch) -> None:
    normal = _order("가짜시공집", kinds={"construction": _d(0)}, workers=["가짜기사"])
    as_in = _order("가짜에이에스", kinds={"as_visit": _d(0)}, stage="AS", status="AS_RECEIVED", workers=["가짜기사"])
    as_both = _order("가짜에이에스둘", kinds={"as_visit": _d(0), "construction": _d(0)}, stage="COMPLETED",
                     status="AS_RECEIVED")
    as_out = _order("가짜에이에스시공일만", kinds={"construction": _d(0)}, stage="COMPLETED", status="AS_RECEIVED")
    _login(client, monkeypatch)
    first = _first(_get(client, f"?date={_d(0)}&worker="))
    assert "3집" in _cut(first, "foms-cons-first__dayh", "</h2>")  # 시공 1 + AS 2(둘 다인 집은 한 집)
    row = _row(first, as_in)
    assert "<small>AS 방문</small>" in row and '<span class="is-none">-</span>' in row and "자</small>" not in row
    assert first.count(f'data-order-id="{as_both}"') == 1
    assert f'data-order-id="{as_out}"' not in first  # 대조군: AS 방문일 없는 AS 집은 지금처럼 뺀다
    assert "AS 방문" not in _row(first, normal)
    # 출고와 같은 묶음 규칙: 같은 시공자 묶음 안, 일반 줄 뒤에 AS 줄
    card = _cut(first, f'data-order-id="{normal}"', "</div>\n")
    assert card.index(f'data-order-id="{as_in}"') > 0


def test_as_visit_detail_draws_no_construction_buttons(client, monkeypatch) -> None:
    as_in = _order("가짜에이에스상세", kinds={"as_visit": _d(2)}, stage="COMPLETED", status="AS_RECEIVED")
    cons = _order("가짜같은날시공", kinds={"construction": _d(2)})
    _login(client, monkeypatch)
    body = _get(client, f"?focus_order={as_in}&date={_d(2)}&worker=")
    panel = _panel(body, as_in)
    assert "AS 방문 집이에요" in panel
    for action in ('data-action="startConstruction"', 'data-action="openCompleteGate"', "data-cwork-fail"):
        assert action not in panel and action not in _confirm(body, as_in)
    assert 'data-action="startConstruction"' in _panel(body, cons)  # 대조군: 같은 날 시공 집은 단추가 있다
    assert f'data-order-id="{as_in}"' in _cut(body, 'class="foms-cwork-timeline"', "</aside>")


# ── a51 날짜 미정 집 ─────────────────────────────────────────────────────────

def test_undated_scope_and_more_menu_line(client, monkeypatch) -> None:
    undated = _order("가짜날짜없음", workers=["가짜기사"])
    _order("가짜시공일있음", kinds={"construction": _d(30)})
    _order("가짜생산날짜없음", stage="PRODUCTION")
    _order("가짜에이에스날짜없음", stage="CONSTRUCTION", status="AS_RECEIVED")
    _order("가짜완료날짜없음", stage="COMPLETED")
    _login(client, monkeypatch)
    first = _first(_get(client, f"?date={_d(0)}&worker="))
    link = re.search(r'<a class="foms-cons-pop__item" href="([^"]+)" data-cons-undated>날짜 미정 (\d+)집 보기</a>', first)
    assert link and link.group(2) == "1" and "undated=1" in link.group(1) and f"date={_d(0)}" in link.group(1)
    body = _get(client, f"?undated=1&date={_d(0)}&worker=")
    assert "foms-cons-first" not in body
    left = _cut(body, 'class="foms-cwork-timeline"', "</aside>")
    assert "날짜 미정 · <span data-cwork-count>1</span>집" in left and "날짜 목록" in left
    assert re.findall(r'data-order-id="(\d+)"', left) == [str(undated)]


def test_undated_zero_has_no_line_and_worker_filter_applies(client, monkeypatch) -> None:
    _order("가짜날짜없음남", workers=["가짜남기사"])
    _login(client, monkeypatch)
    assert "data-cons-undated" in _first(_get(client, f"?date={_d(0)}&worker="))
    assert "data-cons-undated" not in _first(_get(client, f"?date={_d(0)}&worker=가짜다른기사"))


def test_undated_cap_reports_more(client, monkeypatch) -> None:
    for i in range(3):
        _order(f"가짜캡{i}")
    monkeypatch.setattr(tf, "DAY_ROWS_CAP", 2)
    monkeypatch.setattr(tv, "DAY_ROWS_CAP", 2)
    _login(client, monkeypatch)
    left = _cut(_get(client, "?undated=1"), 'class="foms-cwork-timeline"', "</aside>")
    assert len(re.findall(r'class="foms-cwork-card[ "]', left)) == 2 and "더 있는 집은 안 보여요" in left


def test_construction_team_undated_is_own_only(client, monkeypatch) -> None:
    mine = _order("가짜내날짜없음", workers=["가짜시공자"])
    _order("가짜남날짜없음", workers=["가짜남"])
    _login(client, monkeypatch, role="STAFF", team="CONSTRUCTION", name="가짜시공자")
    left = _cut(_get(client, "?undated=1&worker="), 'class="foms-cwork-timeline"', "</aside>")
    assert re.findall(r'data-order-id="(\d+)"', left) == [str(mine)]


# ── 쿼리 수 ─────────────────────────────────────────────────────────────────

def _count(fn) -> int:
    n = {"n": 0}

    def _on(*_a):
        n["n"] += 1

    event.listen(engine, "before_cursor_execute", _on)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _on)
    return n["n"]


@pytest.mark.parametrize("mode,cap", [("first", 10), ("detail", 8), ("undated", 7)])
def test_query_counts_with_as_and_undated(client, monkeypatch, mode, cap) -> None:
    """날짜 미정 수는 쿼리 A 와 한 문장이라 첫 화면 10 그대로 · AS 는 조건만 넓혀 그대로 · undated 는 그날 줄 쿼리 대신 목록 1."""
    ids = [_order(f"가짜측정{i}", kinds={"construction": _d(0)}, workers=["가짜기사"]) for i in range(4)]
    _order("가짜측정에이에스", kinds={"as_visit": _d(0)}, stage="AS", status="AS_RECEIVED")
    _order("가짜측정날짜없음")
    _login(client, monkeypatch)
    query = {"first": "", "detail": f"?focus_order={ids[0]}&date={_d(0)}", "undated": "?undated=1"}[mode]
    _get(client, query)
    dc.reset_dashboard_cache_runtime_for_tests()
    small = _count(lambda: client.get(URL + query, headers=SHELL))
    for i in range(8):
        _order(f"가짜측정추가{i}", kinds={"construction": _d(0)}, workers=["가짜기사"])
        _order(f"가짜측정날짜없음추가{i}")
    dc.reset_dashboard_cache_runtime_for_tests()
    big = _count(lambda: client.get(URL + query, headers=SHELL))
    assert big - small <= 2 and big <= cap, (mode, small, big)


def test_old_deeplink_as_house_picks_as_visit_day_not_construction_day() -> None:
    """AS 상태 집의 옛 딥링크는 AS 방문일로 연다 — 시공일로 열면 그날 첫 화면 범위 밖이라 왼쪽 수가 어긋났다(스테이징 11-12).

    시공일(오늘 +1)이 AS 방문일(오늘 +3)보다 가까워도 AS 방문일을 고른다. AS 아닌 집은 시공일.
    """
    oid = _order("가짜딥링크AS", kinds={"construction": _d(1), "as_visit": _d(3)}, status="AS_RECEIVED")
    assert tv.resolve_focus_day(db_session, oid, is_as=True) == _d(3)
    assert tv.resolve_focus_day(db_session, oid, is_as=False) == _d(1)
    only_c = _order("가짜딥링크AS시공일만", kinds={"construction": _d(2)}, status="AS_RECEIVED")
    assert tv.resolve_focus_day(db_session, only_c, is_as=True) == _d(2)  # AS 방문일이 없으면 다른 종류로


# ── D44 상세 왼쪽 목록 다듬기 ────────────────────────────────────────────────

def test_detail_left_list_puts_as_visit_houses_after_construction(client, monkeypatch) -> None:
    """시간상 먼저인 AS 방문 집도 시공 집 뒤(첫 화면 묶음 안 순서와 같은 규칙) — 되돌리면 실패."""
    as_early = _order("가짜이른에이에스", kinds={"as_visit": _d(1)}, stage="AS", status="AS_RECEIVED")
    cons_late = _order("가짜늦은시공", kinds={"construction": _d(1)})
    # 구조 자료를 다시 넣으면 일정 표가 다시 맞춰지므로(order_date_sync) 일정 날짜도 같이 적는다.
    for oid, t, kind in ((as_early, "오전 8시", "as_visit"), (cons_late, "오후 2시", "construction")):
        o = db_session.get(Order, oid)
        sd = dict(o.structured_data)
        sd["shipment"] = {**sd.get("shipment", {}), "construction_time": t}
        sd["schedule"] = {kind: {"date": _d(1)}}
        o.structured_data = sd
    db_session.commit()
    _login(client, monkeypatch)
    left = _cut(_get(client, f"?focus_order={as_early}&date={_d(1)}&worker="), 'class="foms-cwork-timeline"', "</aside>")
    assert re.findall(r'class="foms-cwork-card[^"]*"\s+data-order-id="(\d+)"', left) == [str(cons_late), str(as_early)]
    assert re.search(rf'foms-cwork-card is-active"\s+data-order-id="{as_early}"', left)  # 누른 집은 그대로 켜짐


def test_workmode_js_reveals_active_card_in_detail_list_only() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/foms/tablet-construction-workmode.js").read_text(encoding="utf-8")
    body = js[js.index("function revealActiveCard()"):js.index("function onReadyOrSwap()")]
    assert ".foms-construction-workmode[data-cwork-mode] .foms-cwork-timeline__list" in body
    assert ".foms-cwork-card.is-active" in body and "list.scrollTop" in body and "clientHeight" in body
    assert "scrollIntoView" not in js and "window.scroll" not in body
    ready = js[js.index("function onReadyOrSwap()"):]
    assert "revealActiveCard();" in ready[:ready.index("}")]
    page = (root / "templates/construction/dashboard.html").read_text(encoding="utf-8")
    pin = re.search(r"js/foms/tablet-construction-workmode\.js'\) \}\}\?v=(\d{8}[a-z])", page)
    assert pin and pin.group(1) >= "20261112e"
