"""협력사 희망 시공일도 시공 건수에 든다(사용자 결정 2026-10-28).

협력사는 주문 · 실측까지만 하고 도면 · 제작 · 시공 · AS 는 우리가 한다. 그래서 확정 전 희망일도 우리 모바일 홈
달력 · 그날 목록 · 협력사 달력 · 출고 14일 칸의 시공 건수에 넣고, 시공일이 정해지면 그 날짜로 옮겨 한 번만 센다.
출고가도 그날 금액에 싣고, 출고 화면 그날 목록 · 자수에도 넣는다(사용자 결정 2026-10-29). 대조군: 희망일 없는 협력사 주문, 시공일 확정 뒤.
"""
from __future__ import annotations

import datetime
import re

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.services.orders.dashboard_control_tower as tower
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.partners.construction_calendar import partner_construction_calendar
from models import Order, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    world,
)

_TODAY = datetime.date(2026, 11, 1)


@pytest.fixture
def priced(monkeypatch):
    """출고가 = 300만(시험용) — 실제 식은 우리 달력 시험이 고정한다."""
    monkeypatch.setattr(tower, "erp_shipping_price_from_structured", lambda sd: 3_000_000)


def _order(app, partner_id, date="", name="희망고객") -> int:
    extra = {"requested_construction_date": date, "requested_construction_time": "오후"} if date else {}
    resp = _create(app, partner_id, {**_PAYLOAD, "customer_name": name, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _confirm(order_id, date):
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"date": date, "time": "오전"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.erp_construction_date = date
    db_session.commit()


def _cell(cal, iso):
    return next(c for w in cal["weeks"] for c in w if c["iso"] == iso)


def test_partner_calendar_counts_request_once(app, world, priced):
    asked = _order(app, world["partner_a"], "2026-11-03")
    _order(app, world["partner_b"], name="희망없음")
    cal = partner_construction_calendar(db_session, world["org_b"], "2026-11", today=_TODAY)
    assert _cell(cal, "2026-11-03")["count"] == 1 and cal["construction_total"] == 1
    assert _cell(cal, "2026-11-03")["amount_label"] == ""  # 다른 회사 주문 — 건수만
    own = partner_construction_calendar(db_session, world["org_a"], "2026-11", today=_TODAY)
    assert _cell(own, "2026-11-03")["amount_label"] == "300만" and own["own_amount_label"] == "300만"
    _confirm(asked, "2026-11-05")
    cal = partner_construction_calendar(db_session, world["org_b"], "2026-11", today=_TODAY)
    assert _cell(cal, "2026-11-03")["count"] == 0
    assert _cell(cal, "2026-11-05")["count"] == 1 and cal["construction_total"] == 1


def test_home_calendar_and_day_sheet_list_request(app, world, priced):
    asked = _order(app, world["partner_a"], "2026-11-03")
    admin = db_session.get(User, world["admin"])
    month = tower.build_month_calendar(db_session, admin, "2026-11", today=_TODAY)
    # 칸 금액은 발주방 PUSH 된 주문만(2026-10-29) — 확정 대기 희망일은 건수만
    assert _cell(month, "2026-11-03")["construction"] == 1 and _cell(month, "2026-11-03")["amount_label"] == ""
    day = tower.build_field_ops_for_day(db_session, admin, "2026-11-03", today=_TODAY)
    assert day["construction_count"] == 1 and day["count"] == 1
    row = next(r for r in day["rows"] if r["id"] == asked)
    assert row["type_code"] == "construction" and row["time"] == "오후"
    assert row["readiness_label"] == "협력사 희망 · 확정 대기" and row["amount"] == 3_000_000
    assert day["amount_label"] == "300만"
    _confirm(asked, "2026-11-05")
    assert tower.build_field_ops_for_day(db_session, admin, "2026-11-03", today=_TODAY)["rows"] == []
    month = tower.build_month_calendar(db_session, admin, "2026-11", today=_TODAY)
    assert _cell(month, "2026-11-03")["amount_label"] == "" and _cell(month, "2026-11-05")["amount_label"] == ""
    assert month["amount_label"] == "0원"  # 칸·이달 합계는 발주방 PUSH 된 주문만(2026-10-29) — 이 주문은 PUSH 전
    row = tower.build_field_ops_for_day(db_session, admin, "2026-11-05", today=_TODAY)["rows"][0]
    assert row["id"] == asked and row["readiness_label"] != "협력사 희망 · 확정 대기"


def _panel_count(page: str, iso: str) -> int:
    match = re.search(rf'id="date-{iso}".*?erp-scheduler-count">(\d+)<', page, re.S)
    assert match, iso
    return int(match.group(1))


def test_shipment_panel_counts_request(app, world):
    day = (get_today_kst() + datetime.timedelta(days=3)).isoformat()
    asked = _order(app, world["partner_a"], day)
    admin = _client(app, db_session.get(User, world["admin"]))
    page = admin.get("/erp/shipment").get_data(as_text=True)
    assert _panel_count(page, day) == 1 and "날짜별 시공 건수 · 자수 · 그날 목록에 들어가 있습니다" in page
    staff = _client(app, db_session.get(User, world["staff"]))
    assert _panel_count(staff.get("/erp/shipment?mine=1").get_data(as_text=True), day) == 0
    _confirm(asked, day)
    assert _panel_count(admin.get("/erp/shipment").get_data(as_text=True), day) == 1


def test_shipment_day_list_and_units_include_request(app, world):
    day = (get_today_kst() + datetime.timedelta(days=4)).isoformat()
    asked = _order(app, world["partner_a"], day)
    _order(app, world["partner_b"], name="희망없음")  # 대조군: 희망일 없는 협력사 주문
    order = db_session.get(Order, asked)
    sd = dict(order.structured_data)
    sd["items"] = [{"product_name": "붙박이장", "spec_width": "3000"}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    admin = _client(app, db_session.get(User, world["admin"]))
    page = admin.get(f"/erp/shipment?date={day}").get_data(as_text=True)
    assert f'id="shipment-row-{asked}"' in page and "data-shipment-partner-request" in page
    assert "희망없음" not in page
    used = re.search(rf'href="[^"]*#date-{day}">\s*<span class="foms-ship-cap-card__top">.*?foms-ship-cap-card__val">([\d.]+)/', page, re.S)
    assert used and float(used.group(1)) == 10.0
    other_day = (get_today_kst() + datetime.timedelta(days=5)).isoformat()
    assert f'id="shipment-row-{asked}"' not in admin.get(f"/erp/shipment?date={other_day}").get_data(as_text=True)
    staff = _client(app, db_session.get(User, world["staff"]))
    assert f'id="shipment-row-{asked}"' not in staff.get(f"/erp/shipment?date={day}&mine=1").get_data(as_text=True)
    _confirm(asked, day)  # 확정 뒤에는 우리 시공 일정 행으로 한 번만 — 확정 대기 표시는 빠진다
    page = admin.get(f"/erp/shipment?date={day}").get_data(as_text=True)
    assert page.count(f'id="shipment-row-{asked}"') == 1 and "data-shipment-partner-request" not in page
