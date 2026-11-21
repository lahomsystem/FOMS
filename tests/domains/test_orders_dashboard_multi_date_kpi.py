"""주문 대시보드 시공 D-3 · 생산 D-2 숫자판과 필터가 시공일 전부를 본다 (묶음 B 리뷰 B-2).

평면 칸 ``erp_construction_date`` 는 글에서 먼저 적힌 날뿐이라, 첫 날이 지나고 둘째 날이 임박한
주문은 줄에 임박 배지가 떠도 숫자판 수에 안 들고 칸을 누르면 목록에서 빠졌다.
숫자판 · 1차 SQL 후보 · 줄 배지가 같은 주문을 가리키는지 잠근다.
"""
from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services import erp_display
from foms.services.orders import dashboard_read_model as rm
from foms.services.orders.dashboard_filters import OrdersDashboardFilters
from models import Order

TODAY = datetime.date(2026, 11, 16)   # 월요일 — D-3 창은 16~19일, D-2 창은 16~18일


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(rm, "get_today_kst", lambda: TODAY)
    monkeypatch.setattr(erp_display, "get_today_kst", lambda: TODAY)


def _order(name, cons_text, *, stage="PRODUCTION"):
    first = cons_text.split(",")[0].strip()
    return Order(
        received_date="2026-10-01", customer_name=name, phone="010-1234-0000", address="서울",
        product="붙박이장", status=stage, erp_stage_code=stage, is_erp_order=True,
        erp_construction_date=first,
        structured_data={"workflow": {"stage": stage}, "schedule": {"construction": {"date": cons_text}}},
    )


def _seed():
    rows = {
        # 고쳐지는 꼴 — 첫 날은 지났고 둘째 날(내일)이 임박
        "two": _order("둘째 날 임박", "2026-11-02, 2026-11-17"),
        # 대조군 — 날짜 하나가 임박(전에도 셌다)
        "one": _order("하루 임박", "2026-11-18"),
        # 대조군 — 멀리 있는 날 하나, 지난 날 둘
        "far": _order("먼 날", "2026-11-30"),
        "past": _order("모두 지남", "2026-11-02, 2026-11-09"),
        # 대조군 — 시공 단계는 생산 D-2 에서 빠진다(시공 D-3 에는 든다)
        "cons": _order("시공 단계", "2026-11-02, 2026-11-17", stage="CONSTRUCTION"),
    }
    db_session.add_all(rows.values())
    db_session.commit()
    return {k: o.id for k, o in rows.items()}


def _filters(alert_type=""):
    return OrdersDashboardFilters(
        stage="", urgent="", has_alert="", alert_type=alert_type, q="", effective_stage="", team="",
        sort="latest", today="", tower_mine=False, mine=False, date="", field="", risk="",
        focus_order_id=None,
    )


def _badge_ids(orders, key):
    return {o.id for o in orders if erp_display._erp_alerts(o, o.structured_data, 0).get(key)}


def test_kpi_tiles_count_the_later_imminent_date(app, fixed_today):
    ids = _seed()
    _q, stats, _d, _iso = rm.build_orders_dashboard_queries(db_session, None, True, _filters())
    summary = rm.compute_orders_summary_slice(stats.order_by(None))
    assert summary["kpis"]["construction_d3_count"] == 3        # two · one · cons
    assert summary["kpis"]["production_d2_count"] == 2          # two · one (시공 단계 제외)
    steps = {s["label"]: s for s in summary["process_steps"]}
    assert steps["생산"]["imminent"] == 2 and steps["시공"]["imminent"] == 1
    # 숫자판 수 = 줄 배지 수
    every = db_session.query(Order).filter(Order.id.in_(ids.values())).all()
    assert len(_badge_ids(every, "construction_d3")) == 3
    assert len(_badge_ids(every, "production_d2")) == 2


@pytest.mark.parametrize("alert_type, expected", [
    ("construction_d3", {"two", "one", "cons"}),
    ("production_d2", {"two", "one"}),
])
def test_alert_filter_keeps_rows_whose_badge_is_on(app, fixed_today, alert_type, expected):
    ids = _seed()
    query, _stats, _d, _iso = rm.build_orders_dashboard_queries(db_session, None, True, _filters(alert_type))
    found = query.all()
    want = {ids[k] for k in expected}
    # 1차 SQL 후보가 배지가 켜진 줄을 하나도 빠뜨리지 않고, 먼 날 · 지난 날은 넣지 않는다
    assert {o.id for o in found} == want
    assert _badge_ids(found, alert_type) == want
