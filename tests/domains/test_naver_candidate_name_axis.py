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


def _order(name: str) -> Order:
    order = Order(
        received_date="2026-10-15", customer_name=name, phone="010-2577-0000",
        address="강북구 솔샘로 159, 벽산 라이브파크 107-102", product="붙박이장",
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
    _order("강민주희")
    assert find_order_candidates(db_session, _link("강민주", "PO-NAME-LONGER")) == []
