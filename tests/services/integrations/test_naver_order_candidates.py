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


# ---------------------------------------------------------------------------
# NAVER-MATCH-01 (2026-09-01 사고): 수집분 문기범 / 주문 #4915
#
# 자동 매칭이 "기존 주문 없음"이라 했는데 수동 검색은 같은 주문을 찾아냈다. 축 2개가
# 동시에 죽어 있었다:
#   * 전화축 — ERP 쪽 전화를 8/30 에 새 번호로 고쳐 ``erp_phone_digits`` 가 갈렸다.
#     (뒤 갈래 ``Order.phone == digits`` 는 포맷 원문과 숫자열을 견주는 죽은 코드다.)
#   * 이름+주소축 — 네이버는 ``서울특별시 …`` 전체 표기, 사람은 ``성북구 …`` 축약형.
#     앞 10자 ``startswith`` 로는 통째로 어긋난다.
#
# 아래 fixture 값은 운영 실데이터 그대로다(기존 ``_order``/``_link`` 기본값은 ERP 주소가
# 네이버 base 를 글자 그대로 접두로 포함하는 모양이라 이 결함을 태우지 못했다).
# ---------------------------------------------------------------------------

_INCIDENT_NAVER_BASE = "서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트)"
_INCIDENT_NAVER_DETAIL = "110동 2403호"
_INCIDENT_ERP_ADDRESS = "성북구 화랑로48길 16, 두산아파트 110동 2403호"


def _incident_link(external_id="PO-MATCH01") -> ExternalOrderLink:
    return _link(recipient_tel="010-3468-7933", orderer_tel="010-3468-7933",
                 name="문기범", base=_INCIDENT_NAVER_BASE,
                 detail=_INCIDENT_NAVER_DETAIL, external_id=external_id)


def test_address_notation_gap_still_matches_name_and_address(app):
    """네이버 전체 표기 vs 사람 축약형 — 같은 집이면 이름·주소축으로 잡아야 한다.

    전화는 ERP 쪽이 새 번호로 바뀌어 있어(운영 #4915 실제 상태) 전화축은 못 쓴다.
    """
    order = _order(name="문기범", phone="010-3468-7933", digits="01096215670",
                   address=_INCIDENT_ERP_ADDRESS)
    got = find_order_candidates(db_session, _incident_link())
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] == "이름·주소 일치"
    assert got[0]["score"] == 60


def test_name_only_match_is_offered_with_weakest_score(app):
    """주소까지 바뀐 재주문도 **보여는 준다** — 단 가장 약한 단서로 표시한다."""
    order = _order(name="문기범", phone="010-3468-7933", digits="01096215670",
                   address="성동구 왕십리로 100, 101동 1호")
    got = find_order_candidates(db_session, _incident_link(external_id="PO-NAMEONLY"))
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] == "수령인명만 일치"
    assert got[0]["score"] == 40


def test_same_address_but_different_name_is_not_a_candidate(app):
    """음성 대조군 — 같은 집이라도 이름이 다르면 남의 주문이다(문기범/문유주)."""
    _order(name="문유주", phone="010-9999-8888", digits="01099998888",
           address=_INCIDENT_ERP_ADDRESS)
    assert find_order_candidates(db_session, _incident_link(external_id="PO-OTHERNAME")) == []


def test_same_road_different_building_number_is_not_address_match(app):
    """음성 대조군 — 도로명이 같아도 건물번호가 다르면 주소 일치가 아니다."""
    order = _order(name="문기범", phone="010-3468-7933", digits="01096215670",
                   address="성북구 화랑로48길 18, 두산아파트 110동 2403호")
    got = find_order_candidates(db_session, _incident_link(external_id="PO-OTHERBLDG"))
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] == "수령인명만 일치"


def test_same_road_different_district_is_not_address_match(app):
    """음성 대조군 — 도로명·번지가 같아도 구가 다르면 다른 집이다."""
    order = _order(name="문기범", phone="010-3468-7933", digits="01096215670",
                   address="성동구 화랑로48길 16, 두산아파트 110동 2403호")
    got = find_order_candidates(db_session, _incident_link(external_id="PO-OTHERGU"))
    assert got[0]["reason"] == "수령인명만 일치"
    assert got[0]["order_id"] == order.id


def test_raw_phone_column_alone_does_not_win_the_phone_axis(app):
    """현재 계약: 전화축은 ``erp_phone_digits`` 만 실질 축이다.

    flat ``Order.phone`` 컬럼이 네이버 번호를 들고 있어도 그것만으로는 100점이 아니다 —
    그 컬럼은 저장 경로에 따라 갱신이 갈리는 낡은 값이라(운영 활성 주문 130건 어긋남)
    거기에 판정을 얹으면 데이터 결함이 기능의 받침대가 된다. 이 축을 바꾸는 날 이
    테스트가 빨개져서 **의도한 변경**임을 강제한다.
    """
    order = _order(name="문기범", phone="010-3468-7933", digits="01096215670",
                   address="성동구 왕십리로 100, 101동 1호")
    got = find_order_candidates(db_session, _incident_link(external_id="PO-RAWPHONE"))
    assert [row["order_id"] for row in got] == [order.id]
    assert got[0]["reason"] != "수취인 전화 일치"


def test_name_scan_cap_is_reported_not_silent(app, caplog, monkeypatch):
    """이름 스캔 캡에 닿으면 **닿았다고 말한다** — 조용한 절단은 "이게 전부"로 읽힌다."""
    from foms.services.integrations.naver_commerce import order_candidates as mod

    monkeypatch.setattr(mod, "NAME_SCAN_CAP", 2)
    for idx in range(3):
        _order(name="문기범", phone="010-3468-7933", digits="01096215670",
               address=f"성북구 화랑로48길 16, 두산아파트 110동 {idx}호")
    with caplog.at_level("WARNING"):
        find_order_candidates(db_session, _incident_link(external_id="PO-CAP"))
    assert any("이름 스캔 캡" in rec.getMessage() for rec in caplog.records)
