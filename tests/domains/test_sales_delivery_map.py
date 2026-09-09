"""`build_sales_delivery_by_ref` (스펙 §4.2) 계약 테스트.

역방향 맵: AS 영업/택배 전달 건(주문)을 배정된 실측 주문 id(ref_order_id) 로 뒤집는다.
모집단·상태 판정은 기존 SSOT(`build_as_tab_query_conditions`, `sales_delivery_link`)를
그대로 타므로, 여기서는 조립 결과(그룹핑·필터링·cap 공시)만 검증한다.
"""
import copy
from datetime import date

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.orders.sales_delivery_link import mark_delivered, set_method, write_link
from foms.services.orders.sales_delivery_map import build_sales_delivery_by_ref
from models import Order


def _create_as_order(
    *,
    status="AS_RECEIVED",
    as_completed_date=None,
    shipment_extra=None,
    customer_name="AS 전달 고객",
    address="서울시 전달동",
):
    """`sales_delivery=true` 플래그가 켜진 AS 주문(전달 건 후보)을 만든다."""
    today = date.today().strftime("%Y-%m-%d")
    shipment = {"sales_delivery": True}
    if shipment_extra:
        shipment.update(shipment_extra)
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-1234-5678",
        address=address,
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today,
        as_completed_date=as_completed_date,
        is_erp_order=True,
        structured_data={"shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assign_link(order, *, ref_order_id, ref_date="2026-09-10", ref_manager="김실측", assigned_by="관리자"):
    """전달 주문에 실측 배정 링크를 붙인다(프로젝트 규약: deepcopy + flag_modified)."""
    sd = copy.deepcopy(order.structured_data or {})
    write_link(
        sd,
        ref_order_id=ref_order_id,
        ref_date=ref_date,
        ref_manager=ref_manager,
        actor_user_id=1,
        actor_name=assigned_by,
    )
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return sd


def test_linked_order_grouped_under_ref_order_id(app):
    order = _create_as_order()
    _assign_link(order, ref_order_id=9001, ref_date="2026-09-11", ref_manager="김실측", assigned_by="박관리")

    result = build_sales_delivery_by_ref(db_session)

    assert 9001 in result["by_ref"]
    items = result["by_ref"][9001]
    assert len(items) == 1
    item = items[0]
    assert item["order_id"] == order.id
    assert item["customer_name"] == "AS 전달 고객"
    assert item["address"] == "서울시 전달동"
    assert item["state"] == "assigned"
    assert item["ref_date"] == "2026-09-11"
    assert item["ref_manager"] == "김실측"
    assert item["assigned_by"] == "박관리"
    assert item["assigned_at"]
    assert result["total"] == 1
    assert result["truncated"] is False


def test_two_orders_same_ref_produce_list_of_two(app):
    order_a = _create_as_order(customer_name="전달 A")
    order_b = _create_as_order(customer_name="전달 B")
    _assign_link(order_a, ref_order_id=9002)
    _assign_link(order_b, ref_order_id=9002)

    result = build_sales_delivery_by_ref(db_session)

    assert len(result["by_ref"][9002]) == 2
    names = {item["customer_name"] for item in result["by_ref"][9002]}
    assert names == {"전달 A", "전달 B"}


def test_order_without_link_is_excluded(app):
    _create_as_order()  # sales_delivery=true 이지만 아직 미배정

    result = build_sales_delivery_by_ref(db_session)

    assert result["by_ref"] == {}
    assert result["total"] == 0


def test_parcel_method_is_excluded(app):
    order = _create_as_order()
    _assign_link(order, ref_order_id=9003)
    sd = copy.deepcopy(order.structured_data)
    set_method(sd, "parcel", parcel={"carrier": "CJ", "tracking_no": "111"}, actor_name="박관리")
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    result = build_sales_delivery_by_ref(db_session)

    assert 9003 not in result["by_ref"]
    assert result["total"] == 0


def test_delivered_status_is_included(app):
    order = _create_as_order()
    _assign_link(order, ref_order_id=9004)
    sd = copy.deepcopy(order.structured_data)
    mark_delivered(sd, by="박관리")
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    result = build_sales_delivery_by_ref(db_session)

    assert 9004 in result["by_ref"]
    assert result["by_ref"][9004][0]["state"] == "delivered"


def test_cap_exceeded_sets_truncated_true(app):
    for i in range(3):
        order = _create_as_order(customer_name=f"캡초과 {i}")
        _assign_link(order, ref_order_id=9100 + i)

    result = build_sales_delivery_by_ref(db_session, cap=2)

    assert result["truncated"] is True
    assert sum(len(v) for v in result["by_ref"].values()) <= 2


def test_completed_as_is_excluded(app):
    today = date.today().strftime("%Y-%m-%d")
    order = _create_as_order(status="AS_COMPLETED", as_completed_date=today)
    _assign_link(order, ref_order_id=9005)

    result = build_sales_delivery_by_ref(db_session)

    assert 9005 not in result["by_ref"]
    assert result["total"] == 0


def test_item_text_uses_as_content_plain_text():
    """전달 카드의 '무엇을 챙기나' 는 AS 내용을 평문 한 줄로 접어서 쓴다."""
    order = _create_as_order(
        shipment_extra={"as_content": "<p>상판 마감캡 6EA</p><p>도어 힌지 교체</p>"}
    )
    _assign_link(order, ref_order_id=90101)

    result = build_sales_delivery_by_ref(db_session)
    item = result["by_ref"][90101][0]

    assert "<" not in item["item_text"]
    assert "\n" not in item["item_text"]
    assert "상판 마감캡 6EA" in item["item_text"]
    assert "도어 힌지 교체" in item["item_text"]


def test_item_text_truncates_long_as_content():
    """AS 내용이 길면 카드 한 줄 길이에서 말줄임한다."""
    order = _create_as_order(shipment_extra={"as_content": "가" * 200})
    _assign_link(order, ref_order_id=90102)

    item = build_sales_delivery_by_ref(db_session)["by_ref"][90102][0]

    assert len(item["item_text"]) <= 60
    assert item["item_text"].endswith("…")


def test_item_text_is_empty_without_as_content():
    """AS 내용이 없으면 빈 문자열이다(카드가 빈 줄을 그리지 않도록 호출부가 판단)."""
    order = _create_as_order()
    _assign_link(order, ref_order_id=90103)

    assert build_sales_delivery_by_ref(db_session)["by_ref"][90103][0]["item_text"] == ""
