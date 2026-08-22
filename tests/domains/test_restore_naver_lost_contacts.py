"""``tools/ops/restore_naver_lost_contacts.py`` 복구 계약 테스트.

폼 저장이 지운 ``parties.buyer.*`` · ``parties.customer.phone2`` 를
``ExternalOrderLink.raw_snapshot`` 에서 되채우는 스크립트다. 고정하는 계약:

* 비어 있는 자리만 채운다 — 사람이 넣은 값은 스냅샷과 달라도 덮지 않는다.
* ``parties.orderer`` 는 건드리지 않는다(그 자리는 발주사다).
* 기본은 dry-run(쓰기 없음), ``execute=True`` 여야 실제로 쓴다.
* 멱등 — 한 번 채우면 다음 실행은 ``restored=0``.
"""
from __future__ import annotations

from db import db_session
from models import ExternalOrderLink, Order

from tools.ops.restore_naver_lost_contacts import (
    apply_parties_restore,
    mask_phone,
    plan_parties_restore,
    run_restore,
)

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _snapshot(*, orderer_tel: str = "010-6279-1403", tel2: str = "010-5555-6666") -> dict:
    """네이버 상세 응답 fixture (구조는 실응답 기준, 값은 가상)."""
    return {
        "order": {
            "orderId": f"N-{_uid()}",
            "ordererName": "김주문",
            "ordererTel": orderer_tel,
            "orderDate": "2026-08-14T10:00:00.000+09:00",
        },
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productOrderStatus": "PAYED",
            "productName": "붙박이장",
            "quantity": 1,
            "totalPaymentAmount": 100000,
            "shippingAddress": {
                "name": "이수취",
                "tel1": "010-3333-4444",
                "tel2": tel2,
                "baseAddress": "서울 강남구 1",
                "detailedAddress": "101호",
                "zipCode": "06232",
            },
        },
    }


#: 폼 저장이 지나간 뒤 남는 모양 — 주문자 전화·보조 연락처가 사라져 있다.
def _stripped_parties() -> dict:
    return {"customer": {"name": "이수취", "phone": "010-3333-4444"},
            "orderer": {"name": "라홈"},
            "manager": {"name": "담당"}}


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
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id,
        external_order_no=snapshot["order"]["orderId"],
        sync_status="LINKED",
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


# --- 순수 함수 계약 ---------------------------------------------------------

def test_plan_restores_only_dropped_contact_keys():
    """비어 있는 orderer.phone·customer.phone2 만 계획에 담긴다(이름 제외)."""
    snapshot_parties = {
        "customer": {"name": "이수취", "phone": "010-3333-4444", "phone2": "010-5555-6666"},
        "orderer": {"name": "라홈"},
        "buyer": {"name": "김주문", "phone": "010-6279-1403"},
    }
    plan = plan_parties_restore(_stripped_parties(), snapshot_parties)
    assert plan == {"buyer.name": "김주문", "buyer.phone": "010-6279-1403",
                    "customer.phone2": "010-5555-6666"}
    assert not any(key.startswith("orderer.") for key in plan)


def test_plan_never_overwrites_existing_value():
    """사람이 넣은 값이 있으면 스냅샷과 달라도 건드리지 않는다."""
    current = {"customer": {"phone2": "010-0000-0000"},
               "buyer": {"name": "김주문", "phone": "010-9999-8888"}}
    snapshot_parties = {"customer": {"phone2": "010-5555-6666"},
                        "buyer": {"name": "김주문", "phone": "010-6279-1403"}}
    assert plan_parties_restore(current, snapshot_parties) == {}


def test_plan_ignores_blank_snapshot_values():
    """스냅샷에 값이 없으면(tel2 미입력) 복구 대상이 아니다."""
    snapshot_parties = {"customer": {"phone2": ""}, "buyer": {"name": "", "phone": "  "}}
    assert plan_parties_restore(_stripped_parties(), snapshot_parties) == {}


def test_plan_handles_missing_subtree():
    """parties.buyer 가 통째로 없어도 계획이 선다."""
    plan = plan_parties_restore({"customer": {}}, {"buyer": {"phone": "010-6279-1403"}})
    assert plan == {"buyer.phone": "010-6279-1403"}


def test_apply_is_idempotent_and_leaves_other_keys():
    """적용 후 재계획은 비고, 기존 키(발주사 이름 등)와 원본 dict 는 그대로다."""
    snapshot_parties = {"customer": {"phone2": "010-5555-6666"},
                        "buyer": {"name": "김주문", "phone": "010-6279-1403"}}
    sd = {"parties": _stripped_parties(), "site": {"address_full": "서울 강남구 1 101호"}}
    plan = plan_parties_restore(sd["parties"], snapshot_parties)
    new_sd = apply_parties_restore(sd, plan)

    assert new_sd["parties"]["buyer"] == {"name": "김주문", "phone": "010-6279-1403"}
    assert new_sd["parties"]["orderer"] == {"name": "라홈"}  # 발주사 자리는 그대로
    assert new_sd["parties"]["customer"]["phone2"] == "010-5555-6666"
    assert new_sd["site"] == sd["site"]
    assert "buyer" not in sd["parties"]  # 원본 불변(deepcopy)
    assert plan_parties_restore(new_sd["parties"], snapshot_parties) == {}


def test_mask_phone_hides_middle_digits():
    assert mask_phone("010-6279-1403") == "010-****-1403"
    assert mask_phone("01062791403") == "010-****-1403"
    assert mask_phone("12") == "***"


# --- DB 실행 계약 -----------------------------------------------------------

def test_dry_run_reports_without_writing(app):
    """기본 실행은 목록만 만들고 DB 를 바꾸지 않는다."""
    order = _order(_stripped_parties())
    _link(order, _snapshot())
    order_id = order.id

    result = run_restore(db_session, order_ids=[order_id])

    assert result["mode"] == "dry-run"
    assert result["restored"] == 3
    assert result["orders_touched"] == 1
    assert {c["key"] for c in result["changes"]} == {
        "parties.buyer.name", "parties.buyer.phone", "parties.customer.phone2"}

    db_session.expire_all()
    reloaded = db_session.query(Order).filter(Order.id == order_id).first()
    assert "buyer" not in reloaded.structured_data["parties"]


def test_execute_writes_and_second_run_is_noop(app):
    """execute 는 실제로 채우고, 재실행은 복구할 게 없다."""
    order = _order(_stripped_parties())
    _link(order, _snapshot())
    order_id = order.id

    result = run_restore(db_session, execute=True, order_ids=[order_id])
    assert result["restored"] == 3

    db_session.expire_all()
    reloaded = db_session.query(Order).filter(Order.id == order_id).first()
    parties = reloaded.structured_data["parties"]
    assert parties["buyer"] == {"name": "김주문", "phone": "010-6279-1403"}
    assert parties["customer"]["phone2"] == "010-5555-6666"
    assert parties["orderer"]["name"] == "라홈"  # 발주사 자리는 그대로

    again = run_restore(db_session, order_ids=[order_id])
    assert again["restored"] == 0
    assert again["skipped"].get("nothing_missing") == 1


def test_deleted_order_and_snapshotless_link_are_skipped(app):
    """삭제 주문·스냅샷 없는 링크는 사유별로 세고 넘어간다."""
    deleted = _order(_stripped_parties())
    deleted.status = "DELETED"
    db_session.commit()
    _link(deleted, _snapshot())

    bare = _order(_stripped_parties())
    bare_link = _link(bare, _snapshot())
    bare_link.raw_snapshot = None
    db_session.commit()

    result = run_restore(db_session, order_ids=[deleted.id, bare.id])

    assert result["restored"] == 0
    assert result["skipped"].get("order_gone") == 1
    assert result["skipped"].get("no_snapshot") == 1
