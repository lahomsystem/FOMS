"""NAVER-INGEST-02 T16-C: 기존 주문 후보 매칭 계약 테스트.

재결제·차액 결제를 사람이 알아보려면 "이 고객의 기존 주문"이 먼저 보여야 한다.
자동으로 붙이지 않으므로, 이 모듈의 계약은 **맞는 후보를 빠뜨리지 않고 남을 끌어오지
않는 것**이다.
"""

from __future__ import annotations

import datetime

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from models import ExternalOrderLink, Order


def _order(*, name="김고객", phone="010-1111-2222", digits="01011112222",
           address="서울시 강남구 테헤란로 152 101동 1001호", product="붙박이장",
           days_ago=3, status="RECEIVED") -> Order:
    order = Order(
        received_date="2026-08-01", customer_name=name, phone=phone, address=address,
        product=product, status=status,
        erp_phone_digits=digits,
        created_at=now_utc_naive() - datetime.timedelta(days=days_ago),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, recipient_tel="010-1111-2222", orderer_tel="010-1111-2222",
          name="김고객", base="서울시 강남구 테헤란로 152", detail="101동 1001호",
          external_id="PO-CAND") -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": "N-CAND", "ordererTel": orderer_tel, "ordererName": name},
            "productOrder": {
                "productOrderId": external_id, "productName": "로라 무몰딩 1cm",
                "shippingAddress": {"name": name, "tel1": recipient_tel,
                                    "baseAddress": base, "detailedAddress": detail},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


def test_recipient_phone_match_is_top_candidate(app):
    """수취인 전화 일치가 가장 강한 단서다."""
    order = _order()
    got = find_order_candidates(db_session, _link())
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] == "수취인 전화 일치"
    assert got[0]["score"] == 100


def test_orderer_phone_match_covers_proxy_orders(app):
    """대리주문 — 주문자와 수취인 전화가 다르면 둘 다 본다."""
    proxy = _order(name="이대리", phone="010-9999-8888", digits="01099998888",
                   address="부산시 해운대구 센텀로 10")
    got = find_order_candidates(
        db_session,
        _link(recipient_tel="010-3333-4444", orderer_tel="010-9999-8888",
              name="박수취", base="대전시 유성구 대학로 1", detail="", external_id="PO-PROXY"),
    )
    assert [row["order_id"] for row in got] == [proxy.id]
    assert got[0]["reason"] == "주문자 전화 일치"


def test_name_and_address_match_when_phone_changed(app):
    """전화가 바뀐 재주문도 이름+주소 앞부분으로 잡는다."""
    order = _order(phone="010-5555-6666", digits="01055556666")
    got = find_order_candidates(
        db_session,
        _link(recipient_tel="010-7777-8888", orderer_tel="010-7777-8888",
              external_id="PO-NAMEADDR"),
    )
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] == "이름·주소 일치"


def test_unrelated_orders_are_not_pulled_in(app):
    """남의 주문을 끌어오면 안 된다 — 잘못 붙이면 금액이 남의 집에 섞인다."""
    _order(name="남남남", phone="010-0000-0000", digits="01000000000",
           address="인천시 남동구 예술로 100")
    assert find_order_candidates(db_session, _link(external_id="PO-NONE")) == []


def test_soft_deleted_orders_are_excluded(app):
    """휴지통 주문은 후보가 아니다."""
    order = _order()
    order.deleted_at = "2026-08-10"
    db_session.commit()
    assert find_order_candidates(db_session, _link(external_id="PO-DEL")) == []


def test_orders_outside_window_are_excluded(app):
    """오래된 주문은 후보에서 뺀다(180일 창)."""
    _order(days_ago=400)
    assert find_order_candidates(db_session, _link(external_id="PO-OLD")) == []


def test_link_own_order_is_not_its_own_candidate(app):
    """이미 이 링크가 붙은 주문은 후보가 아니다(자기 자신)."""
    order = _order()
    link = _link(external_id="PO-SELF")
    link.order_id = order.id
    db_session.commit()
    assert find_order_candidates(db_session, link) == []


def test_broken_snapshot_returns_empty_not_crash(app):
    """원본이 깨져도 화면이 죽으면 안 된다."""
    link = ExternalOrderLink(channel="NAVER", external_id="PO-BROKEN",
                             sync_status="COLLECTED", raw_snapshot=None)
    db_session.add(link)
    db_session.commit()
    assert find_order_candidates(db_session, link) == []


def test_candidate_reports_existing_naver_link_count(app):
    """이미 네이버 수집분이 붙은 주문인지 알려준다(재결제 판단 근거)."""
    order = _order()
    prior = ExternalOrderLink(channel="NAVER", external_id="PO-PRIOR",
                              sync_status="LINKED", order_id=order.id,
                              raw_snapshot={"productOrder": {"productOrderId": "PO-PRIOR"}})
    db_session.add(prior)
    db_session.commit()

    got = find_order_candidates(db_session, _link(external_id="PO-WITHPRIOR"))
    assert got[0]["naver_link_count"] == 1
