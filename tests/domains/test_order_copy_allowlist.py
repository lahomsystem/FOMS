"""주문 복사 — 넣을 것만 넣기 (설계서 2026-11-20 6.3 · M14).

완료 기준: 고객 · 발주사 · 주문한 사람 · 주소 · 제품 본문(가격 · 규격 계산) · 할인 · 자유입력 · 전화 · 주소 특이사항 ·
라홈시스템 표식 · 담당 뱃지는 따라온다. 결제 확인 · 예약금 · 현금영수증 · 정산 · AS 기록 · 알림톡 · AS PUSH 이력 · 통화 ·
제작 · 시공 기록 · 네이버 칸 · 협력사 표식 · 휴지통 기록 · 제품 칸의 날짜 · 첨부 · 네이버 금액 · 긴급 표시 · 실측 메모는
따라오지 않는다. **허용 목록에 없는 새 열쇠는 저절로 빠진다.** 복사본은 AS 화면 모집단에 안 들고 일정 줄이 없다.
"""

from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace

from db import db_session
from foms.services.order_copy import _copy_structured_data
from models import Order, OrderEvent, OrderScheduleDate
from tests.domains.test_auth_finance import _login, _make_user

PHONE = "010-5551-2468"
ADDRESS = "합성시 가상구 시험대로10길 20 합성아파트 2505동 1103호"

#: 복사본에 있어도 되는 맨 위 칸 — 허용 목록 + create_order 가 새로 심는 것.
ALLOWED_TOP_KEYS = {"parties", "site", "items", "notes", "flags", "payment", "meta", "workflow", "quests", "totals"}


def rich_structured_data() -> dict:
    """복사가 흘리던 칸을 모두 가진 원본(합성 값)."""
    return {
        "entity_type": "order_structured", "schema_version": 1, "raw": "붙여넣기 원문", "confidence": "high",
        "workflow": {"stage": "PRODUCTION", "stage_updated_at": "2026-11-01T10:00:00"},
        "parties": {
            "customer": {"name": "합성고객", "phone": PHONE, "phone2": "010-5551-0002", "memo_internal": "x"},
            "orderer": {"name": "라홈"},
            "buyer": {"name": "주문한사람", "phone": "010-5551-0003"},
            "manager": {"name": "담당A (합성협력사)", "names": ["담당A", "담당B"], "partner_user_id": 77,
                        "partner_user_name": "담당A"},
            "installer": {"name": "시공자"},
        },
        "site": {"address_full": ADDRESS, "address_main": ADDRESS, "address_detail": "", "zip_code": "12345",
                 "address_note": "공동현관 #1234", "map_url": "https://map.example/x"},
        "items": [
            {"uid": "a" * 36, "product_name": "합성 붙박이장", "name": "합성 붙박이장", "spec": "2400x600x2300",
             "spec_rows": [{"spec_width": "2400", "spec_depth": "600", "spec_height": "2300"}],
             "spec_width": "2400", "spec_depth": "600", "spec_height": "2300", "internal": "A", "color": "화이트",
             "option_detail": "댐핑", "handle": "매립", "misc": "기타", "options": "옵션 글", "quantity": 1,
             "price": 1200000, "extra_input": "추가", "pricing": {"enabled": True, "product_id": 3},
             "measurement_date": "2026-11-03", "construction_date": "2026-11-17",
             "attachments": [{"key": "orders/1/a.png"}], "naver_paid_amount": 1200000,
             "production_done": True},
            {"uid": "b" * 36, "product_name": "합성 수납장", "price": "300,000", "construction_date": "2026-11-24",
             "cancel": {"reason": "customer_change"}},
        ],
        "notes": {"phone_note": "오후에만 통화", "address_note": "주차 불가", "measurement_note": "천장 2350",
                  "construction_note": "1차 시공 메모"},
        "flags": {"urgent": True, "urgent_reason": "입주 임박", "factory2": True, "happy_call": "ABSENT",
                  "estimate_needs_update": True},
        "payment": {"deposit": "300,000", "discount": 50000, "discounts": [{"label": "행사", "amount": 50000}],
                    "free_input": "배송 30000", "cash_receipt": "010-5551-2468", "balance_note": "잔금 메모",
                    "deposit_confirmed": True, "deposit_confirmed_at": "2026-11-01T10:00:00",
                    "balance_confirmed": True, "balance_method": "CARD"},
        "payments": [{"amount": 300000}],
        "settlement": {"deductions": [{"amount": 10000}], "cash_receipt_issued": True},
        "totals": {"items_total": 9},
        "schedule": {"construction": {"date": "2026-11-17"}, "measurement": {"date": "2026-11-03"}},
        "shipment": {"as_log": [{"text": "x"}]},
        "as_lifecycle": {"current_cycle_id": "c1", "cycles": [
            {"cycle_id": "c1", "transitions": [{"to": "RECEIVED", "at": "2026-11-10T09:00:00"}]}]},
        "as_info": [{"content": "문짝 처짐"}],
        "as_drawing": {"rounds": [{"round": 1}]}, "as_drawing_status": "REQUESTED",
        "alimtalk_measurement": {"sent_at": "2026-11-02T09:00:00"},
        "alimtalk_construction": {"sent_at": "2026-11-16T09:00:00"},
        "alimtalk_share": {"sent_at": "2026-11-05T09:00:00"},
        "channeltalk_push": {"pushed": True}, "channeltalk_push_as": {"pushed": True},
        "channeltalk_push_as_drawing_room": {"pushed": True},
        "measurement_visits": [{"at": "2026-11-03"}], "calls": [{"result": "ABSENT"}],
        "production": {"steps": {"cut": True}},
        "construction": {"evidence": {"photos": ["k"]}}, "construction_fail_history": [{"reason": "부재"}],
        "source": "PARTNER", "partner_intake": {"submitted_by_name": "담당A"},
        "naver": {"product_order_id": "2026"}, "pricing": {"deposit_base": 1}, "naver_linked": True,
        "delete": {"deleted_at": "2026-10-01T00:00:00"}, "checklist": {"a": True},
        "drawing_current_files": [{"key": "d.png"}], "quests": [{"stage": "PRODUCTION"}],
        "assignments": {"owner_team": "PRODUCTION"},
        "meta": {"draft": False, "created_via": "WIZARD", "wizard_v1": True, "wizard_draft_key": "wk-1",
                 "finalized_at": "2026-11-01T10:00:00", "wdc_estimate_id": 9},
        "brand_new_server_key": {"anything": 1},
    }


def make_original() -> Order:
    sd = rich_structured_data()
    order = Order(
        received_date="2026-11-01", received_time="09:10", customer_name="합성고객", phone=PHONE, address=ADDRESS,
        product="합성 붙박이장", notes="접수 비고", status="PRODUCTION", is_erp_order=True, structured_data=sd,
        erp_stage_code="PRODUCTION", erp_phone_digits="01055512468", as_axis_status="RECEIVED",
        structured_schema_version=1,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_copy_structured_data_keeps_only_the_allowlist():
    source = rich_structured_data()
    untouched = copy.deepcopy(source)

    out = _copy_structured_data(SimpleNamespace(id=41, structured_data=source), datetime.datetime(2026, 11, 20, 9))

    assert set(out) == {"parties", "site", "items", "notes", "flags", "payment", "meta"}
    assert out["parties"] == {
        "customer": {"name": "합성고객", "phone": PHONE, "phone2": "010-5551-0002"},
        "orderer": {"name": "라홈"},
        "buyer": {"name": "주문한사람", "phone": "010-5551-0003"},
        "manager": {"name": "담당A (합성협력사)", "names": ["담당A", "담당B"]},
    }
    assert out["site"] == {"address_full": ADDRESS, "address_main": ADDRESS, "address_detail": "",
                           "zip_code": "12345", "address_note": "공동현관 #1234"}
    first, second = out["items"]
    assert first == {
        "product_name": "합성 붙박이장", "name": "합성 붙박이장", "spec": "2400x600x2300",
        "spec_rows": [{"spec_width": "2400", "spec_depth": "600", "spec_height": "2300"}],
        "spec_width": "2400", "spec_depth": "600", "spec_height": "2300", "internal": "A", "color": "화이트",
        "option_detail": "댐핑", "handle": "매립", "misc": "기타", "options": "옵션 글", "quantity": 1,
        "price": 1200000, "extra_input": "추가", "pricing": {"enabled": True, "product_id": 3},
    }
    assert second == {"product_name": "합성 수납장", "price": "300,000"}, "취소 품목도 살아서 따라온다(날짜 · 취소 표시 없이)"
    assert out["notes"] == {"phone_note": "오후에만 통화", "address_note": "주차 불가"}
    assert out["flags"] == {"factory2": True}
    assert out["payment"] == {"discount": 50000, "discounts": [{"label": "행사", "amount": 50000}],
                              "free_input": "배송 30000"}
    assert out["meta"] == {"draft": False, "created_via": "ORDER_COPY", "copied_from_order_id": 41,
                           "copied_at": "2026-11-20T09:00:00"}
    assert source == untouched, "원본은 그대로"
    # 깊은 복사: 복사본을 고쳐도 원본이 바뀌지 않는다.
    out["items"][0]["spec_rows"][0]["spec_width"] = "9999"
    assert source["items"][0]["spec_rows"][0]["spec_width"] == "2400"


def test_unknown_new_key_is_dropped_by_default():
    source = {"parties": {"customer": {"name": "합성고객"}}, "items": [{"product_name": "장", "future_item_key": 1}],
              "future_top_key": {"x": 1}, "flags": {"future_flag": True}, "payment": {"future_payment": 1},
              "notes": {"future_note": "x"}, "site": {"future_site": "x"}}

    out = _copy_structured_data(SimpleNamespace(id=1, structured_data=source), datetime.datetime(2026, 11, 20))

    assert "future_top_key" not in out
    assert out["items"] == [{"product_name": "장"}]
    assert out["flags"] == {} and out["payment"] == {} and out["notes"] == {} and out["site"] == {}
    assert out["parties"] == {"customer": {"name": "합성고객"}}


def test_text_notes_and_scalar_manager_are_kept():
    # 마법사 · 협력사 주문은 접수 메모가 글 한 칸이고, 옛 주문은 담당이 이름 글이다.
    source = {"notes": "접수 메모 한 줄", "parties": {"manager": "옛담당", "customer": "글"}}

    out = _copy_structured_data(SimpleNamespace(id=1, structured_data=source), datetime.datetime(2026, 11, 20))

    assert out["notes"] == "접수 메모 한 줄"
    assert out["parties"] == {"manager": "옛담당", "customer": "글"}


def test_copy_api_does_not_leak_payment_as_alimtalk_dates_or_schedule_rows(client):
    staff = _make_user("STAFF", "SALES")
    _login(client, staff)
    original = make_original()
    original_id = original.id
    # 대조군: 원본은 제품 칸 날짜로 일정 줄이 생겨 있고 AS 축이 열려 있다.
    assert db_session.query(OrderScheduleDate).filter_by(order_id=original_id, kind="construction").count() >= 1

    response = client.post("/api/orders/copy", json={"order_ids": [original_id]})

    assert response.status_code == 200, response.get_json()
    new_id = response.get_json()["orders"][0]["new_order_id"]
    db_session.expire_all()
    copied = db_session.get(Order, new_id)
    sd = copied.structured_data

    assert set(sd) <= ALLOWED_TOP_KEYS, set(sd) - ALLOWED_TOP_KEYS
    # 옮긴 것
    assert copied.customer_name == "합성고객" and copied.phone == PHONE and copied.address == ADDRESS
    assert sd["parties"]["customer"]["phone2"] == "010-5551-0002"
    assert sd["parties"]["buyer"] == {"name": "주문한사람", "phone": "010-5551-0003"}
    assert [item["product_name"] for item in sd["items"]] == ["합성 붙박이장", "합성 수납장"]
    assert sd["items"][0]["price"] == 1200000 and sd["items"][0]["pricing"] == {"enabled": True, "product_id": 3}
    assert sd["payment"]["discount"] == 50000 and sd["payment"]["free_input"] == "배송 30000"
    assert sd["flags"]["factory2"] is True
    assert sd["notes"] == {"phone_note": "오후에만 통화", "address_note": "주차 불가"}
    assert sd["totals"]["items_total"] == 1500000 and sd["totals"]["discount_amount"] == 50000
    # 옮기지 않은 것
    assert sd["totals"]["deposit_amount"] == 0 and not copied.payment_amount
    for key in ("deposit", "cash_receipt", "balance_note", "deposit_confirmed", "balance_confirmed", "balance_method"):
        assert key not in sd["payment"], key
    for item in sd["items"]:
        for key in ("measurement_date", "construction_date", "attachments", "naver_paid_amount", "cancel",
                    "production_done"):
            assert key not in item, key
    assert {item["uid"] for item in sd["items"]}.isdisjoint({"a" * 36, "b" * 36}), "제품 uid 는 새로 준다"
    assert "urgent" not in sd["flags"] and copied.erp_urgent is False
    assert sd["workflow"]["stage"] == "RECEIVED"
    assert set(sd["meta"]) == {"draft", "created_via", "copied_from_order_id", "copied_at"}
    assert "partner_user_id" not in sd["parties"]["manager"]
    # 복사본은 AS 화면 모집단에 들지 않고, 일정 줄이 하나도 없다.
    assert copied.as_axis_status is None
    assert copied.erp_construction_date in (None, "") and copied.erp_measurement_date in (None, "")
    assert db_session.query(OrderScheduleDate).filter_by(order_id=new_id).count() == 0
    # 원본은 그대로다.
    original_saved = db_session.get(Order, original_id)
    assert original_saved.as_axis_status == "RECEIVED"
    assert original_saved.structured_data["payment"]["deposit"] == "300,000"
    assert original_saved.structured_data["as_lifecycle"]["current_cycle_id"] == "c1"


def test_copy_records_the_in_progress_original_in_created_event(client):
    staff = _make_user("STAFF", "SALES")
    staff_id = staff.id
    _login(client, staff)
    original_id = make_original().id

    new_id = client.post("/api/orders/copy", json={"order_ids": [original_id]}).get_json()["orders"][0]["new_order_id"]

    event = db_session.query(OrderEvent).filter_by(order_id=new_id, event_type="ORDER_CREATED").one()
    assert event.payload == {"owner_user_id": staff_id, "status": "RECEIVED", "open_order_ids": [original_id]}
