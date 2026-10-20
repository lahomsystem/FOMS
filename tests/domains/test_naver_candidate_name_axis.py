"""후보 조회 이름축은 표시 기호를 뗀 글자로 견준다.

2026-10-20 운영 강민주 건: 담당자가 ERP 이름을 ``★강민주`` 로 표시해 둔 사이 네이버
집(수취인 ``강민주``, 안심번호)이 수집돼 후보 0건으로 떴고, 새 주문이 하나 더 생겼다.
전화가 안심번호면 이름축이 유일한 단서라 완전 일치로는 못 잡는다.
"""

from __future__ import annotations

import datetime

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from models import ExternalOrderLink, Order


def _order(name: str, address: str = "강북구 솔샘로 159, 벽산 라이브파크 107-102") -> Order:
    order = Order(
        received_date="2026-10-15", customer_name=name, phone="010-2577-0000",
        address=address, product="붙박이장",
        status="RECEIVED", erp_phone_digits="01025770000",
        created_at=now_utc_naive() - datetime.timedelta(days=5),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _link(name: str, external_id: str) -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": f"N-{external_id}", "ordererTel": "0502-2727-3545",
                      "ordererName": name},
            "productOrder": {
                "productOrderId": external_id, "productName": "로라 무몰딩 붙박이장",
                "shippingAddress": {"name": name, "tel1": "0502-2727-3545",
                                    "baseAddress": "서울특별시 강북구 솔샘로 159",
                                    "detailedAddress": "107동 102호"},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


def test_marked_erp_name_still_matches(app):
    """``★강민주`` 주문이 ``강민주`` 수집분의 후보로 뜬다."""
    order = _order("★강민주")
    rows = find_order_candidates(db_session, _link("강민주", "PO-NAME-MARK"))
    assert [row["order_id"] for row in rows] == [order.id]
    # 주소 키는 운영 두 표기(쉼표·동호 축약)를 같은 키로 맞춘다 — 그래서 이름·주소 일치다.
    assert rows[0]["reason"] == "이름·주소 일치"


def test_longer_name_is_not_matched(app):
    """음성 대조군 — 포함만 되는 다른 이름(``강민주희``)은 후보가 아니다."""
    # 주소축이 따로 잡지 않게 다른 호수로 둔다.
    _order("강민주희", "강북구 솔샘로 159, 벽산 라이브파크 107-909")
    assert find_order_candidates(db_session, _link("강민주", "PO-NAME-LONGER")) == []


def _addr_order(name: str, address: str) -> Order:
    order = Order(
        received_date="2026-10-06", customer_name=name, phone="010-1234-0000",
        address=address, product="붙박이장", status="RECEIVED",
        erp_phone_digits="01012340000",
        created_at=now_utc_naive() - datetime.timedelta(days=5),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _addr_link(external_id: str) -> ExternalOrderLink:
    """2026-10-20 운영 이재천 건 모양 — 이름·전화는 다르고 집만 같다."""
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": f"N-{external_id}", "ordererTel": "010-3953-9212",
                      "ordererName": "이재천"},
            "productOrder": {
                "productOrderId": external_id, "productName": "로라 몰딩 여닫이",
                "shippingAddress": {
                    "name": "이재천", "tel1": "010-3953-9212",
                    "baseAddress": "경기도 화성시 동탄구 동탄대로10길 20 (산척동, 동탄 더샵 레이크에듀타운)",
                    "detailedAddress": "2505동 1103호"},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


def test_same_unit_address_matches_without_name(app):
    """이름이 달라도 도로명·건물번호·동·호가 같으면 후보다."""
    order = _addr_order("김세진", "동탄대로10길 20 더샵레이크에듀타운 2505동 1103호")
    rows = find_order_candidates(db_session, _addr_link("PO-ADDR-SAME"))
    assert [row["order_id"] for row in rows] == [order.id]
    assert rows[0]["reason"] == "주소(동·호)만 일치"


def test_same_complex_other_unit_is_not_matched(app):
    """음성 대조군 — 같은 단지 다른 호수는 후보가 아니다."""
    _addr_order("김세진", "동탄대로10길 20 더샵레이크에듀타운 2505동 1104호")
    assert find_order_candidates(db_session, _addr_link("PO-ADDR-OTHER")) == []
