"""시공일 옮기기 — 나눠 시공 주문은 '시공 끝' 제품의 날을 옮기지 않는다(설계서 2026-11-21 8절, 최종 검수 F-B1 · F-B3).

* 시공 불가 다시 잡기: 남은 제품 날 가운데 방문 날 이하 가장 늦은 날, 없으면 그 뒤 가장 가까운 남은 날.
* 대시보드 칸: 남은 제품 날 가운데 글에 처음 적힌 날. 남은 날이 없을 때만 지금 규칙.
* 대시보드 칸에서 날이 그대로면 생산팀 알림을 건너뛴다. 합성 주문만.
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.services.notifications.production_change as production_change
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_schedule import (
    first_order_date,
    move_first_date_for_field,
    reschedule_text_after_fail,
    visit_order_date,
)
from models import Order, User


@pytest.fixture(autouse=True)
def flag_on(monkeypatch):
    monkeypatch.setenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", "1")


def _uid(idx: int) -> str:
    return f"00000000-0000-0000-0000-{idx:012d}"  # 이름표 길이(36자)를 맞춘 합성 uid


def _sd(order_dates: str, item_dates: list, done: tuple = ()) -> dict:
    items = [{"uid": _uid(idx), "product_name": f"제품{idx}", "construction_date": day}
             for idx, day in enumerate(item_dates)]
    marks = {_uid(idx): {"date": item_dates[idx], "source": "visit"} for idx in done}
    return {"workflow": {"stage": "PRODUCTION"},
            "parties": {"customer": {"name": "합성손님", "phone": "010-0000-0000"}},
            "site": {"address_full": "합성 주소", "address_main": "합성 주소"},
            "items": items, "schedule": {"construction": {"date": order_dates, "time": ""}}, "shipment": {},
            "item_construction_done": marks}


def test_시공_불가는_시공_끝_제품의_날을_옮기지_않는다():
    sd = _sd("2026-11-05, 2026-11-17", ["2026-11-05", "2026-11-17"], done=(0,))
    assert visit_order_date(sd, datetime.date(2026, 11, 16)) == "2026-11-17"
    started = datetime.datetime(2026, 11, 16, 1, 0)  # UTC 01:00 = 한국 11/16 10:00
    assert reschedule_text_after_fail(sd, "2026-11-20", started) == "2026-11-05, 2026-11-20"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-11-05", "2026-11-20"]


def test_대시보드_칸은_남은_제품_날_가운데_글에_처음_적힌_날():
    sd = _sd("2026-11-05, 2026-11-17", ["2026-11-05", "2026-11-17"], done=(0,))
    assert first_order_date(sd) == "2026-11-17"
    assert move_first_date_for_field(sd, "2026-11-24") == "2026-11-17"
    assert sd["schedule"]["construction"]["date"] == "2026-11-05, 2026-11-24"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-11-05", "2026-11-24"]


def test_남은_날이_없거나_시공_끝이_없으면_지금_규칙():
    all_done = _sd("2026-11-17, 2026-11-05", ["2026-11-05", "2026-11-17"], done=(0, 1))
    assert first_order_date(all_done) == "2026-11-17"
    assert visit_order_date(all_done, datetime.date(2026, 11, 16)) == "2026-11-05"
    plain = _sd("2026-11-17, 2026-11-05", ["2026-11-05", "2026-11-17"])
    assert first_order_date(plain) == "2026-11-17"
    assert visit_order_date(plain, datetime.date(2026, 11, 16)) == "2026-11-05"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def test_대시보드_칸_날이_그대로면_생산팀_알림이_없다(client, monkeypatch):
    calls: list = []
    real = production_change.apply_production_change_alert
    monkeypatch.setattr(production_change, "apply_production_change_alert",
                        lambda *a, **k: (calls.append(a[3] if len(a) > 3 else k), real(*a, **k))[1])
    user = User(username="mvr_field", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    sd = _sd(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)])
    order = Order(received_date="2026-07-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="붙박이장", status="PRODUCTION", manager_name="담당", is_erp_order=True,
                  structured_data=sd, erp_stage_code="PRODUCTION")
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    oid = order.id

    same = client.post("/api/update_order_field", json={"order_id": oid, "field": "scheduled_date", "value": _day(3)})
    assert same.status_code == 200, same.get_data(as_text=True)
    assert calls == []
    moved = client.post("/api/update_order_field", json={"order_id": oid, "field": "scheduled_date", "value": _day(5)})
    assert moved.status_code == 200, moved.get_data(as_text=True)
    assert len(calls) == 1
    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data["schedule"]["construction"]["date"] == f"{_day(5)}, {_day(10)}"
