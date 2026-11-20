"""AS 가 본 흐름을 가리지 않게 — 줄 종류 판정과 화면별 계약(설계서 2026-11-20-multi-item-split-schedule §4.1 · §4.2).

견본 = 생산(또는 시공) 단계 + AS 접수 상태 + 시공일. 고친 뒤에는 그 주문의 시공일 줄이 시공 줄로 든다.
대조군은 같은 자료 안에서 고른다: ① 본 흐름이 끝난(완료) AS 주문의 시공일 줄은 지금처럼 AS 줄(또는 빠짐),
② AS 아닌 주문은 그대로, ③ 같은 날 시공 + AS 방문은 한 줄 + "AS 방문도". 이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import datetime
import itertools
import re
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.construction import tablet_first as tf
from foms.services.construction import tablet_view as tv
from foms.services.construction_read_model import CONSTRUCTION_ACTIVE_STAGE_CODES
from foms.services.datetime_kst import get_today_kst
from foms.services.orders import schedule_row_kind as rk
from foms.services.partners.shipment_board import partner_shipment_board
from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet
from foms.services.shipment_dashboard_display import (
    attach_shipment_row_kinds,
    build_shipment_mobile_queue_rows,
    sort_shipment_rows,
)
from foms.services.shipment_dashboard_helpers import AS_SHIPMENT_STATUSES
from foms.services.shipment_read_model import compute_shipment_panel_aggregates
from models import Order, OrderScheduleDate, PartnerOrg, User

CONS_URL = "/erp/construction/dashboard"
SHELL = {"X-FOMS-ERP-SHELL": "1"}
_seq = itertools.count(1)
WORKERS = [{"name": "가짜기사", "capacity": 40, "off_dates": []}]


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _d(n: int = 0) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(customer: str, *, stage: str, status: str | None = None, cons: str | None = None,
           as_visit: str | None = None, workers: list[str] | None = None, partner_org_id: int | None = None) -> int:
    """일정 줄은 실제처럼 구조 자료에서 동기화된다(없으면 직접 넣는다) — 시공일 = ``cons``, AS 방문일 = ``as_visit``."""
    schedule: dict = {}
    if cons:
        schedule["construction"] = {"date": cons, "time": "오전"}
    if as_visit:
        schedule["as_visit"] = {"date": as_visit, "type": "AS"}
    sd = {
        "parties": {"manager": {"name": "가짜영업"}, "customer": {"name": customer}, "orderer": {"name": "가짜대리점"}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "3000", "quantity": 1}],
        "site": {"address_full": "가짜시 가짜구 줄종류로 1"},
        "schedule": schedule,
        "shipment": {"construction_workers": workers or [], "as_content": "<p>가짜 문짝 처짐</p>"},
    }
    order = Order(received_date=_d(), customer_name=customer, phone="010-0000-0000", address="가짜시 가짜구 줄종류로 1",
                  product="가짜장", status=status or stage, manager_name="가짜영업", is_erp_order=True,
                  structured_data=sd, erp_stage_code=stage, partner_org_id=partner_org_id)
    db_session.add(order)
    db_session.flush()
    have = {(k, str(d)) for k, d in db_session.query(OrderScheduleDate.kind, OrderScheduleDate.date)
            .filter(OrderScheduleDate.order_id == order.id)}
    for kind, day in (("construction", cons), ("as_visit", as_visit)):
        if day and (kind, day) not in have:
            db_session.add(OrderScheduleDate(order_id=order.id, kind=kind, date=day, source="beta_schedule"))
    db_session.commit()
    return order.id


def _login(client, monkeypatch, *, role: str = "ADMIN", team: str = "CS", tablet: bool = False) -> User:
    n = next(_seq)
    user = User(username=f"rowkind_{n}", password=generate_password_hash("x"), role=role, team=team,
                name=f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    if tablet:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _cut(body: str, start: str, end: str) -> str:
    i = body.index(start)
    return body[i:body.index(end, i)]


def _admin_ns() -> SimpleNamespace:
    return SimpleNamespace(id=1, username="u", name="u", role="ADMIN", team="CS")


# ── 판정 하나 ────────────────────────────────────────────────────────────────

def test_constants_match_the_read_models_they_restate() -> None:
    """잎 모듈이 다시 적은 값은 출고 · 시공 읽기 모델의 값과 같다(한쪽만 바뀌면 화면끼리 어긋난다)."""
    assert rk.AS_ORDER_STATUSES == tuple(AS_SHIPMENT_STATUSES)
    assert set(rk.MAIN_FLOW_OPEN_STAGE_CODES) == set(tf.PRODUCTION_STAGE_CODES) | set(CONSTRUCTION_ACTIVE_STAGE_CODES)
    assert "CS" not in rk.MAIN_FLOW_OPEN_STAGE_CODES and "COMPLETED" not in rk.MAIN_FLOW_OPEN_STAGE_CODES  # M2


@pytest.mark.parametrize("status,stage,cons,visit,expected", [
    ("PRODUCTION", "PRODUCTION", True, False, (False, False)),    # AS 아님 = 시공 줄(그대로)
    ("AS_RECEIVED", "PRODUCTION", True, False, (False, False)),   # 생산 + AS 접수 + 시공일 = 시공 줄
    ("AS_COMPLETED", "시공", True, True, (False, True)),           # 같은 날 둘 다 = 시공 줄 + AS 방문도
    ("AS", "CONSTRUCTION", False, True, (True, False)),           # 본 흐름 열림이어도 AS 방문일만 걸린 날 = AS 줄
    ("AS_RECEIVED", "COMPLETED", True, False, (True, False)),     # 대조군: 완료 + AS = 시공일 줄도 AS 줄
    ("AS_RECEIVED", "CS", True, True, (True, False)),             # 대조군: CS 는 본 흐름 열림이 아니다(M2)
    ("AS_RECEIVED", "AS_RECEIVED", True, False, (True, False)),   # 대조군: 단계 글이 AS 로 굳은 옛 주문
])
def test_row_kind_table(status, stage, cons, visit, expected) -> None:
    order = SimpleNamespace(status=status, erp_stage_code=stage)
    assert tuple(rk.row_kind(order, on_construction_date=cons, on_as_visit_date=visit)) == expected


def test_row_is_as_reads_attached_kind_then_falls_back_to_order_only() -> None:
    plain_as = SimpleNamespace(status="AS_RECEIVED")  # 줄 종류 칸도 단계 칸도 없는 가짜 줄(옛 시험 견본 꼴)
    assert rk.row_is_as(plain_as) is True and rk.row_as_visit_too(plain_as) is False
    open_as = SimpleNamespace(status="AS_RECEIVED", erp_stage_code="PRODUCTION")
    assert rk.row_is_as(open_as) is False  # 날짜를 모르면 본 흐름을 따른다
    attached = SimpleNamespace(status="AS_RECEIVED", erp_stage_code="PRODUCTION",
                               schedule_row_is_as=True, schedule_as_visit_too=False)
    assert rk.row_is_as(attached) is True  # 붙은 값이 이긴다(그날은 AS 방문일뿐)


# ── 태블릿 시공 탭 ───────────────────────────────────────────────────────────

def _first(**kw) -> dict:
    return tf.build_tablet_first(db_session, user=_admin_ns(), mine_only=False, worker_settings=WORKERS, worker="", **kw)


def _rows(result: dict, day: str | None = None) -> dict[int, dict]:
    """고른 날(기본) 묶음의 줄만 — 미리 볼 날 묶음에 같은 집이 또 있어도 섞지 않는다."""
    day = day or result["selected"]
    return {r["id"]: r for s in result["sections"] if s["date"] == day for g in s["groups"] for r in g["rows"]}


def test_tablet_first_counts_and_draws_open_main_flow_as_order_as_construction_row(app) -> None:
    prod_as = _order("가짜생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(0), workers=["가짜기사"])
    cons_as = _order("가짜시공AS완료", stage="CONSTRUCTION", status="AS_COMPLETED", cons=_d(0), workers=["가짜기사"])
    done_as = _order("가짜완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(0))   # 대조군: 지금처럼 빠진다
    cs_as = _order("가짜CS단계AS", stage="CS", status="AS_RECEIVED", cons=_d(0))           # 대조군(M2)
    plain = _order("가짜일반시공", stage="CONSTRUCTION", cons=_d(0), workers=["가짜기사"])  # 대조군: 그대로
    result = _first(selected=_d(0))
    assert result["selected_count"] == 3
    rows = _rows(result)
    assert set(rows) == {prod_as, cons_as, plain} and done_as not in rows and cs_as not in rows
    assert rows[prod_as]["stage"] == "생산중" and rows[prod_as]["as_visit"] is False
    assert rows[prod_as]["packing_text"] == "생산중" and rows[prod_as]["units"] == 10.0
    assert rows[cons_as]["stage"] == "시공대기" and rows[cons_as]["packing_text"] == "포장 전"
    assert rows[plain]["stage"] == "시공대기" and rows[plain]["as_visit_too"] is False


def test_tablet_first_same_day_construction_and_as_visit_is_one_construction_row_with_note(app, client, monkeypatch) -> None:
    both = _order("가짜같은날둘", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(0), as_visit=_d(0))
    visit_only = _order("가짜방문만", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(5), as_visit=_d(0))
    done_both = _order("가짜완료둘", stage="COMPLETED", status="AS_RECEIVED", cons=_d(0), as_visit=_d(0))  # 대조군: AS 줄
    result = _first(selected=_d(0))
    assert result["selected_count"] == 3  # 날짜 수는 집 수(같은 날 둘이어도 1)
    rows = _rows(result)
    assert rows[both]["as_visit"] is False and rows[both]["as_visit_too"] is True and rows[both]["stage"] == "생산중"
    assert rows[visit_only]["as_visit"] is True and rows[visit_only]["as_visit_too"] is False
    assert rows[done_both]["as_visit"] is True and rows[done_both]["as_visit_too"] is False
    assert _rows(_first(selected=_d(5)))[visit_only]["as_visit"] is False  # 그 집의 시공일에는 시공 줄

    _login(client, monkeypatch, tablet=True)
    resp = client.get(f"{CONS_URL}?date={_d(0)}&worker=", headers=SHELL)
    first = _cut(resp.get_data(as_text=True), 'class="foms-cons-first"', "</section>")
    assert first.count(f'data-order-id="{both}"') == 1
    row = _cut(first, f'data-order-id="{both}"', "</a>")
    assert "<small data-cons-as-too>AS 방문도</small>" in row and "<small>AS 방문</small>" not in row
    assert "AS 방문도" not in _cut(first, f'data-order-id="{done_both}"', "</a>")
    assert "<small>AS 방문</small>" in _cut(first, f'data-order-id="{visit_only}"', "</a>")


def test_tablet_detail_draws_construction_buttons_while_main_flow_is_open(app, client, monkeypatch) -> None:
    """M4 — 시공 단계 + AS 접수 집은 본 흐름 글 + [시공 시작]. 대조군: 완료 + AS 집은 단추 없이 'AS 방문 집이에요'."""
    cons_as = _order("가짜시공AS상세", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(2))
    done_as = _order("가짜완료AS상세", stage="COMPLETED", status="AS_RECEIVED", as_visit=_d(2))
    _login(client, monkeypatch, tablet=True)
    body = client.get(f"{CONS_URL}?focus_order={cons_as}&date={_d(2)}&worker=", headers=SHELL).get_data(as_text=True)

    def _panel(oid: int) -> str:
        i = body.index(f'data-cwork-panel="{oid}"')
        nxt = body.find('data-cwork-panel="', i + 1)
        stop = body.index("</section>", i)
        return body[i:nxt if 0 < nxt < stop else stop]

    assert 'data-action="startConstruction"' in _panel(cons_as) and "AS 방문 집이에요" not in _panel(cons_as)
    assert "AS 방문 집이에요" in _panel(done_as) and 'data-action="startConstruction"' not in _panel(done_as)
    left = _cut(body, 'class="foms-cwork-timeline"', "</aside>")
    assert re.findall(r'class="foms-cwork-card[^"]*"\s+data-order-id="(\d+)"', left) == [str(cons_as), str(done_as)]


def _detail_panel(body: str, oid: int) -> str:
    i = body.index(f'data-cwork-panel="{oid}"')
    nxt = body.find('data-cwork-panel="', i + 1)
    stop = body.index("</section>", i)
    return body[i:nxt if 0 < nxt < stop else stop]


def test_tablet_detail_follows_the_day_row_kind_and_first_screen_order(app, client, monkeypatch) -> None:
    """상세는 그날 줄 종류를 따른다 — AS 방문일(시공일과 다른 날)의 줄로 열면 'AS 방문 집이에요' · 단추 없음,
    같은 집을 시공일의 줄로 열면 본 흐름 글 + 단추. 왼쪽 목록 순서는 첫 화면 묶음 순서와 같다."""
    two_days = _order("가짜방문날다른AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(5), as_visit=_d(2))
    plain = _order("가짜같은날일반", stage="CONSTRUCTION", cons=_d(2))
    both = _order("가짜같은날둘상세", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(2), as_visit=_d(2))
    # 방문만 걸린 집이 시간으로는 맨 앞이다 — 그래도 AS 방문 줄은 시공 줄 뒤다.
    early = db_session.get(Order, two_days)
    early.structured_data = {**early.structured_data,
                             "shipment": {**early.structured_data["shipment"], "construction_time": "오전 7시"}}
    db_session.commit()
    _login(client, monkeypatch, tablet=True)

    visit_day = client.get(f"{CONS_URL}?focus_order={two_days}&date={_d(2)}&worker=", headers=SHELL).get_data(as_text=True)
    assert "AS 방문 집이에요" in _detail_panel(visit_day, two_days)
    assert 'data-action="startConstruction"' not in _detail_panel(visit_day, two_days)
    assert 'data-action="startConstruction"' in _detail_panel(visit_day, both)   # 같은 날 둘 다 = 시공 줄
    assert 'data-action="startConstruction"' in _detail_panel(visit_day, plain)
    left = _cut(visit_day, 'class="foms-cwork-timeline"', "</aside>")
    left_ids = [int(x) for x in re.findall(r'class="foms-cwork-card[^"]*"\s+data-order-id="(\d+)"', left)]
    first = _first(selected=_d(2))
    first_ids = [r["id"] for s in first["sections"] if s["date"] == _d(2) for g in s["groups"] for r in g["rows"]]
    assert left_ids == first_ids == [plain, both, two_days]

    cons_day = client.get(f"{CONS_URL}?focus_order={two_days}&date={_d(5)}&worker=", headers=SHELL).get_data(as_text=True)
    assert 'data-action="startConstruction"' in _detail_panel(cons_day, two_days)
    assert "AS 방문 집이에요" not in _detail_panel(cons_day, two_days)


def test_old_deeplink_of_open_main_flow_as_order_opens_its_construction_day(app) -> None:
    oid = _order("가짜딥링크열린AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(1), as_visit=_d(3))
    closed = _order("가짜딥링크닫힌AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1), as_visit=_d(3))
    args = dict(user=_admin_ns(), mine_only=False, partner_org="", date_arg=None, worker_arg="")
    assert tv.build_detail(db_session, focus=db_session.get(Order, oid), **args)["date"] == _d(1)
    assert tv.build_detail(db_session, focus=db_session.get(Order, closed), **args)["date"] == _d(3)  # 대조군


def test_old_deeplink_prefers_upcoming_as_visit_when_construction_days_are_past(app) -> None:
    """시공일이 모두 지났고 AS 방문일이 오늘 이후면 본 흐름이 열린 AS 집도 AS 방문일로 연다."""
    past_cons = _order("가짜지난시공AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(-3), as_visit=_d(2))
    plain_past = _order("가짜지난시공일반", stage="CONSTRUCTION", cons=_d(-3), as_visit=_d(2))  # 대조군: AS 아님
    both_past = _order("가짜둘다지남AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(-3), as_visit=_d(-1))
    args = dict(user=_admin_ns(), mine_only=False, partner_org="", date_arg=None, worker_arg="")
    assert tv.build_detail(db_session, focus=db_session.get(Order, past_cons), **args)["date"] == _d(2)
    assert tv.build_detail(db_session, focus=db_session.get(Order, plain_past), **args)["date"] == _d(-3)
    assert tv.build_detail(db_session, focus=db_session.get(Order, both_past), **args)["date"] == _d(-3)


def test_undated_list_includes_construction_stage_as_order(app) -> None:
    as_undated = _order("가짜날짜없는AS", stage="CONSTRUCTION", status="AS_RECEIVED")
    plain = _order("가짜날짜없음", stage="CONSTRUCTION")
    _order("가짜생산날짜없는AS", stage="PRODUCTION", status="AS_RECEIVED")   # 대조군: 생산 단계는 날짜 미정에 안 든다
    _order("가짜완료날짜없는AS", stage="COMPLETED", status="AS_RECEIVED")    # 대조군
    conds = tf.scope_conditions(user=_admin_ns(), mine_only=False, partner_org="", worker="")
    assert [o.id for o in tf.fetch_undated_orders(db_session, conds)] == [as_undated, plain]
    assert _first()["undated_count"] == 2


# ── 출고 ────────────────────────────────────────────────────────────────────

def _loaded(*ids: int) -> list[Order]:
    by_id = {o.id: o for o in db_session.query(Order).filter(Order.id.in_(ids))}
    return [by_id[i] for i in ids]


def test_panel_aggregates_count_open_main_flow_as_order(app) -> None:
    prod_as = _order("가짜띠생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), workers=["가짜기사"])
    done_as = _order("가짜띠완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1), workers=["가짜기사"])
    plain = _order("가짜띠일반", stage="CONSTRUCTION", cons=_d(1), workers=["가짜기사"])
    today = get_today_kst()
    agg = compute_shipment_panel_aggregates(_loaded(prod_as, done_as, plain), today,
                                            today + datetime.timedelta(days=14), {"가짜기사": WORKERS[0]})
    assert agg["construction_counts"] == {_d(1): 2}       # 생산 + AS 는 센다, 완료 + AS 는 지금처럼 안 센다
    assert agg["spec_units_by_date"] == {_d(1): 20.0}
    assert agg["assigned_workers_by_date"] == {_d(1): ["가짜기사"]}


def test_shipment_rows_kind_sort_day_sheet_and_phone_cards(app) -> None:
    prod_as = _order("가짜출고생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), as_visit=_d(1),
                     workers=["가짜기사"])
    done_as = _order("가짜출고완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1), workers=["가짜기사"])
    plain = _order("가짜출고일반", stage="CONSTRUCTION", cons=_d(1), workers=["가짜기사"])
    rows = _loaded(done_as, prod_as, plain)
    attach_shipment_row_kinds(rows, target_date=_d(1))
    sort_shipment_rows(rows)
    assert [r.id for r in rows] == [prod_as, plain, done_as]  # AS 줄만 맨 뒤
    kinds = {r.id: (r.schedule_row_is_as, r.schedule_as_visit_too) for r in rows}
    assert kinds == {prod_as: (False, True), done_as: (True, False), plain: (False, False)}

    sheet = build_tablet_day_sheet(rows, WORKERS, _d(1))
    sheet_rows = {r["order"].id: r for g in sheet["groups"] for r in g["rows"]}
    assert sheet_rows[prod_as]["is_as"] is False and sheet_rows[prod_as]["units"] == 10.0
    assert sheet_rows[prod_as]["as_visit_too"] is True
    assert sheet_rows[done_as]["is_as"] is True and sheet_rows[done_as]["units"] == 0.0
    assert sheet["people"][0]["units"] == 20.0  # 사람별 자수에도 든다

    cards = {c["id"]: c["shipment_meta"] for c in
             build_shipment_mobile_queue_rows(db_session, rows, _admin_ns(), mobile_v2_active=True)}
    assert cards[prod_as]["is_as"] is False and cards[prod_as]["primary_date"] == _d(1)
    assert cards[prod_as]["as_visit_too"] is True
    assert cards[done_as]["is_as"] is True and cards[done_as]["primary_date"] == ""  # 대조군: AS 카드(방문일 머리)
    assert cards[plain]["is_as"] is False and cards[plain]["as_visit_too"] is False


def test_range_view_and_as_visit_only_day_kinds(app) -> None:
    oid = _order("가짜기간AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(3), as_visit=_d(1))
    (row,) = _loaded(oid)
    attach_shipment_row_kinds([row], target_date=_d(1))
    assert (row.schedule_row_is_as, row.schedule_as_visit_too) == (True, False)   # AS 방문일만 걸린 날 = AS 줄
    attach_shipment_row_kinds([row], target_date=_d(3))
    assert (row.schedule_row_is_as, row.schedule_as_visit_too) == (False, False)  # 시공일 = 시공 줄
    attach_shipment_row_kinds([row], date_from=_d(0), date_to=_d(4))
    assert (row.schedule_row_is_as, row.schedule_as_visit_too) == (False, False)  # 기간에 둘 다 있어도 다른 날이면 안 붙인다
    same = _order("가짜기간같은날AS", stage="CONSTRUCTION", status="AS_RECEIVED", cons=_d(3), as_visit=_d(3))
    (same_row,) = _loaded(same)
    attach_shipment_row_kinds([same_row], date_from=_d(0), date_to=_d(4))
    assert (same_row.schedule_row_is_as, same_row.schedule_as_visit_too) == (False, True)  # 같은 날일 때만 "AS 방문도"


def test_tablet_ship_grid_puts_as_visit_note_in_the_customer_cell(app) -> None:
    from flask import render_template

    both = _order("가짜출고표둘", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), as_visit=_d(1), workers=["가짜기사"])
    plain = _order("가짜출고표일반", stage="CONSTRUCTION", cons=_d(1), workers=["가짜기사"])
    rows = _loaded(both, plain)
    attach_shipment_row_kinds(rows, target_date=_d(1))
    sheet = build_tablet_day_sheet(rows, WORKERS, _d(1))
    with app.test_request_context(f"/erp/shipment?date={_d(1)}"):
        html = render_template("shipment/partials/tablet_ship_grid.html", tablet_day_sheet=sheet,
                               can_edit_shipment=False, shipment_freelancer_view=False, can_edit_order_here=False)
    row = _cut(html, f'id="shipment-tgrid-row-{both}"', "</tr>")
    customer = _cut(row, 'class="foms-tablet-shipgrid__customer"', "</td>")
    assert '<span class="foms-tablet-shipgrid__flag" data-ship-as-too>AS 방문도</span>' in customer
    assert "AS 방문도" not in _cut(row, 'class="foms-tablet-shipgrid__time"', "</td>")  # 좁은 시공시간 칸에는 두지 않는다
    assert "AS 방문도" not in _cut(html, f'id="shipment-tgrid-row-{plain}"', "</tr>")


def _query_count(fn) -> int:
    from sqlalchemy import event

    from db import engine

    n = {"n": 0}

    def _on(*_a) -> None:
        n["n"] += 1

    event.listen(engine, "before_cursor_execute", _on)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _on)
    return n["n"]


def test_row_kind_date_lookup_does_not_grow_queries_per_order(app) -> None:
    """본 흐름이 열린 AS 주문이 늘어도 일정 줄 읽기 쿼리는 늘지 않는다(협력사 출고 탭 · PC 출고 협력사 희망일 줄)."""
    from foms.web.shipment.dashboard import _preload_schedule_dates

    org = PartnerOrg(name=f"가짜협력사{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    ids = [_order("가짜쿼리AS0", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), partner_org_id=org.id)]
    today = get_today_kst()
    partner_shipment_board(db_session, org.id, _d(1), today)  # 한 번 돌려 설정 캐시를 데운다(첫 호출만 드는 쿼리를 빼려고)
    db_session.expire_all()
    small = _query_count(lambda: partner_shipment_board(db_session, org.id, _d(1), today))
    ids += [_order(f"가짜쿼리AS{i}", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), as_visit=_d(1),
                   partner_org_id=org.id) for i in range(1, 5)]
    db_session.expire_all()
    big = _query_count(lambda: partner_shipment_board(db_session, org.id, _d(1), today))
    assert big == small, (small, big)

    # PC 출고: 일정 줄 없이 읽어 온 줄(협력사 희망일 줄 꼴)은 한 번에 싣는다.
    db_session.expire_all()
    rows = _loaded(*ids)

    def _kinds() -> None:
        _preload_schedule_dates(db_session, rows)
        attach_shipment_row_kinds(rows, target_date=_d(1))

    assert _query_count(_kinds) == 1
    assert [r.schedule_as_visit_too for r in rows] == [False, True, True, True, True]


def test_pc_shipment_table_draws_construction_row_and_note(app, client, monkeypatch) -> None:
    prod_as = _order("가짜표생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), as_visit=_d(1))
    done_as = _order("가짜표완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1))
    plain = _order("가짜표일반", stage="CONSTRUCTION", cons=_d(1))
    _login(client, monkeypatch)
    resp = client.get(f"/erp/shipment?date={_d(1)}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    def _tr(oid: int) -> str:
        return _cut(html, f'<tr id="shipment-row-{oid}"', "</tr>")

    assert 'data-as="0"' in _tr(prod_as) and "가짜장" in _tr(prod_as)
    assert '<span class="badge bg-danger mb-1">AS</span>' not in _tr(prod_as)
    assert "data-shipment-as-too>AS 방문도</small>" in _tr(prod_as)
    assert 'data-as="1"' in _tr(done_as) and '<span class="badge bg-danger mb-1">AS</span>' in _tr(done_as)  # 대조군
    assert "가짜 문짝 처짐" in _tr(done_as) and "AS 방문도" not in _tr(done_as)
    assert 'data-as="0"' in _tr(plain) and "AS 방문도" not in _tr(plain)
    assert html.index(f'id="shipment-row-{prod_as}"') < html.index(f'id="shipment-row-{done_as}"')
    # 날짜 띠: 그날 시공 2건(생산 + AS · 일반), 완료 + AS 는 안 센다.
    strip = _cut(html, f'<a id="date-{_d(1)}"', "</a>")
    assert '<span class="badge badge-count erp-scheduler-count">2</span>' in strip


def test_tablet_drawer_head_follows_row_kind_and_keeps_as_info(app, client, monkeypatch) -> None:
    prod_as = _order("가짜서랍생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1))
    done_as = _order("가짜서랍완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1))
    _login(client, monkeypatch, role="STAFF", team="SHIPMENT")
    html = client.get(f"/erp/shipment/tablet-sheet/{prod_as}?date={_d(1)}").get_data(as_text=True)
    assert 'class="foms-ship-sheet__as">AS</span>' not in html and " 출고</div>" in html and "AS 방문</div>" not in html
    assert "AS 정보" in html and "가짜 문짝 처짐" in html  # 시공 줄로 열어도 AS 내용은 읽는다
    closed = client.get(f"/erp/shipment/tablet-sheet/{done_as}?date={_d(1)}").get_data(as_text=True)
    assert 'class="foms-ship-sheet__as">AS</span>' in closed and "AS 방문</div>" in closed  # 대조군


def test_partner_shipment_tab_follows_the_same_row_kind(app) -> None:
    org = PartnerOrg(name=f"가짜협력사{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    prod_as = _order("가짜협력생산AS", stage="PRODUCTION", status="AS_RECEIVED", cons=_d(1), partner_org_id=org.id)
    done_as = _order("가짜협력완료AS", stage="COMPLETED", status="AS_RECEIVED", cons=_d(1), partner_org_id=org.id)
    board = partner_shipment_board(db_session, org.id, _d(1), get_today_kst())
    rows = {r["id"]: r for g in board["groups"] for r in g["rows"]}
    assert rows[prod_as]["is_as"] is False and rows[done_as]["is_as"] is True
