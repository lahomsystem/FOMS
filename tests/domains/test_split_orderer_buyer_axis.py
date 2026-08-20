"""``tools/ops/split_orderer_buyer_axis.py`` 축 분리 백필 계약 테스트 (ORDERER-AXIS-01 T2).

스펙 §4 T2 판정표 5행을 각각 고정한다:

* 발주사 칸의 값이 스냅샷 주문자명과 같으면 사람이다 → `buyer.name` 으로 옮기고 발주사=라홈
* 발주사 칸이 비어 있으면 라홈으로 세운다
* 그 외 값(사람이 고른 발주사)은 건드리지 않는다
* `orderer.phone` 이 스냅샷 주문자 전화와 같으면 `buyer.phone` 으로 옮기고 그 자리를 지운다
* 그 외 번호는 그대로 둔다

그리고 멱등 — 한 번 옮기면 다음 실행 `changed=0`.
"""
from __future__ import annotations

from db import db_session
from models import ExternalOrderLink, Order

from foms.services.integrations.naver_commerce.mapping import build_structured_data
from tools.ops.split_orderer_buyer_axis import (
    apply_axis_split,
    plan_axis_split,
    run_split,
)

_SEQ = [0]

_PERSON = "김주문"
_PERSON_TEL = "010-6279-1403"


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _snapshot() -> dict:
    """네이버 상세 응답 fixture (구조는 실응답 기준, 값은 가상)."""
    return {
        "order": {
            "orderId": f"N-{_uid()}",
            "ordererName": _PERSON,
            "ordererTel": _PERSON_TEL,
            "orderDate": "2026-08-14T10:00:00.000+09:00",
        },
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productOrderStatus": "PAYED",
            "productName": "붙박이장",
            "quantity": 1,
            "totalPaymentAmount": 100000,
            "shippingAddress": {
                "name": "이수취", "tel1": "010-3333-4444",
                "baseAddress": "서울 강남구 1", "detailedAddress": "101호",
                "zipCode": "06232",
            },
        },
    }


def _snapshot_parties() -> dict:
    """새 매핑이 만드는 정본 parties(orderer=라홈 · buyer=사람)."""
    return build_structured_data(_snapshot())["parties"]


def _legacy_parties(**overrides) -> dict:
    """축 분리 이전 수집분 — 발주사 칸에 사람이 들어 있다."""
    parties = {
        "customer": {"name": "이수취", "phone": "010-3333-4444"},
        "orderer": {"name": _PERSON, "phone": _PERSON_TEL},
    }
    parties["orderer"].update(overrides)
    return parties


def _order(parties: dict) -> Order:
    order = Order(
        received_date="2026-08-14", customer_name="이수취", phone="010-3333-4444",
        address="서울 강남구 1 101호", product="붙박이장", status="RECEIVED",
        is_erp_order=True,
        structured_data={"source": "NAVER_SMARTSTORE", "parties": parties},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _link(order: Order, snapshot: dict) -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER", external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id, external_order_no=snapshot["order"]["orderId"],
        sync_status="LINKED", raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


# --- 판정표 5행 -------------------------------------------------------------

def test_person_name_in_orderer_slot_moves_to_buyer():
    """발주사 칸의 사람 이름 → buyer.name, 발주사는 라홈."""
    plan = plan_axis_split(_legacy_parties(), _snapshot_parties())
    assert plan["set"]["buyer.name"] == _PERSON
    assert plan["set"]["orderer.name"] == "라홈"


def test_empty_orderer_becomes_lahom():
    """발주사 칸이 비어 있으면 라홈으로 세운다."""
    plan = plan_axis_split({"orderer": {}}, _snapshot_parties())
    assert plan["set"]["orderer.name"] == "라홈"
    assert plan["set"]["buyer.name"] == _PERSON


def test_human_chosen_orderer_is_left_alone():
    """사람이 고른 발주사(하우드)는 건드리지 않고 buyer 만 채운다."""
    plan = plan_axis_split(_legacy_parties(name="하우드"), _snapshot_parties())
    assert "orderer.name" not in plan["set"]
    assert plan["set"]["buyer.name"] == _PERSON


def test_person_phone_in_orderer_slot_is_moved_and_removed():
    """orderer.phone 이 스냅샷 주문자 전화면 buyer.phone 으로 옮기고 그 자리를 지운다."""
    plan = plan_axis_split(_legacy_parties(), _snapshot_parties())
    assert plan["set"]["buyer.phone"] == _PERSON_TEL
    assert plan["unset"] == ["orderer.phone"]


def test_other_phone_in_orderer_slot_stays():
    """사람이 넣은 다른 번호는 남긴다(옮기지도 지우지도 않는다)."""
    plan = plan_axis_split(_legacy_parties(phone="010-0000-1111"), _snapshot_parties())
    assert plan["unset"] == []


def test_existing_buyer_value_is_not_overwritten():
    """buyer 에 이미 값이 있으면 스냅샷이 덮지 않는다."""
    current = {"orderer": {"name": "라홈"},
               "buyer": {"name": "다른사람", "phone": "010-7777-8888"}}
    plan = plan_axis_split(current, _snapshot_parties())
    assert plan == {"set": {}, "unset": []}


def test_apply_then_replan_is_empty():
    """적용 후 재계획은 비어 있다(멱등)."""
    sd = {"parties": _legacy_parties(), "site": {"address_full": "서울 강남구 1 101호"}}
    snapshot_parties = _snapshot_parties()
    new_sd = apply_axis_split(sd, plan_axis_split(sd["parties"], snapshot_parties))

    assert new_sd["parties"]["orderer"] == {"name": "라홈"}
    assert new_sd["parties"]["buyer"] == {"name": _PERSON, "phone": _PERSON_TEL}
    assert new_sd["site"] == sd["site"]
    assert sd["parties"]["orderer"]["name"] == _PERSON  # 원본 불변(deepcopy)
    assert plan_axis_split(new_sd["parties"], snapshot_parties) == {"set": {}, "unset": []}


# --- DB 실행 계약 -----------------------------------------------------------

def test_dry_run_reports_without_writing(app):
    """기본 실행은 목록만 만들고 DB 를 바꾸지 않는다."""
    order = _order(_legacy_parties())
    _link(order, _snapshot())
    order_id = order.id

    result = run_split(db_session, order_ids=[order_id])

    assert result["mode"] == "dry-run"
    assert result["changed"] == 4
    assert {(c["op"], c["key"]) for c in result["changes"]} == {
        ("set", "parties.buyer.name"),
        ("set", "parties.buyer.phone"),
        ("set", "parties.orderer.name"),
        ("unset", "parties.orderer.phone"),
    }

    db_session.expire_all()
    reloaded = db_session.query(Order).filter(Order.id == order_id).first()
    assert reloaded.structured_data["parties"]["orderer"]["name"] == _PERSON
    assert "buyer" not in reloaded.structured_data["parties"]


def test_execute_moves_axis_and_second_run_is_noop(app):
    """execute 는 실제로 옮기고, 재실행은 바꿀 게 없다."""
    order = _order(_legacy_parties())
    _link(order, _snapshot())
    order_id = order.id

    run_split(db_session, execute=True, order_ids=[order_id])

    db_session.expire_all()
    parties = db_session.query(Order).filter(
        Order.id == order_id).first().structured_data["parties"]
    assert parties["orderer"] == {"name": "라홈"}
    assert parties["buyer"] == {"name": _PERSON, "phone": _PERSON_TEL}
    assert parties["customer"]["phone"] == "010-3333-4444"  # 고객은 그대로

    again = run_split(db_session, order_ids=[order_id])
    assert again["changed"] == 0
    assert again["skipped"].get("already_split") == 1


def test_deleted_order_is_skipped(app):
    """삭제 주문은 사유별로 세고 넘어간다."""
    deleted = _order(_legacy_parties())
    deleted.status = "DELETED"
    db_session.commit()
    _link(deleted, _snapshot())

    result = run_split(db_session, order_ids=[deleted.id])

    assert result["changed"] == 0
    assert result["skipped"].get("order_gone") == 1
