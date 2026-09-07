"""NAVER-MATCH-01 계약: 후보 조회 전화축은 ``erp_phone_digits`` 단독이다.

2026-09-01 네이버 트리아지 자동 매칭 미스의 **원인 줄**을 봉인한다.

전화 축의 사본이 세 벌이다 — ``structured_data`` 원문 · 인덱스 컬럼
``orders.erp_phone_digits`` · 레거시 컬럼 ``orders.phone``. 동기화 함수
:func:`foms.services.erp_sync_columns.sync_erp_flat_columns` 는 ``erp_phone_digits``
만 갱신하고 ``orders.phone`` 은 규약 밖이라, 전화가 바뀌면 ``orders.phone`` 에만
낡은 값이 남는다. 낡은 사본에 판정을 얹으면 데이터 결함이 기능의 받침대가 된다.

그래서 후보 조회는 인덱스 컬럼 하나만 본다. 이 파일은 그것을 **실제 동작으로**
확인하고(양성 + 음성 대조군), 지운 갈래가 되살아나지 않게 소스도 함께 잠근다.
소스 확인만으로는 "조회가 실제로 무엇을 무는가"를 못 보므로 둘을 함께 둔다.
"""

from __future__ import annotations

import datetime
import inspect

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce import order_candidates as candidates_mod
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from models import ExternalOrderLink, Order

# 운영에서 실제로 난 모양: ERP 전화를 새 번호로 고쳐 인덱스 컬럼만 갱신되고
# 레거시 ``orders.phone`` 에는 옛 번호가 그대로 남았다.
_CURRENT_TEL = "010-1111-2222"
_CURRENT_DIGITS = "01011112222"
_STALE_TEL = "010-9621-5670"
# 사람이 하이픈 없이 적어둔 낡은 사본. 지워진 갈래(``Order.phone == digits``)가
# 정확히 이 모양을 물었으므로, 음성 대조군은 이 값이어야 힘이 있다 —
# 하이픈 값으로 두면 지우기 전에도 통과해서 대조군 구실을 못 한다.
_STALE_PHONE_COLUMN = "01096215670"

_ORDER_NAME = "전화축고객"
_ORDER_ADDRESS = "서울시 강남구 테헤란로 152 101동 1001호"


def _stale_phone_order() -> Order:
    """인덱스 컬럼은 새 번호, 레거시 ``phone`` 컬럼은 옛 번호인 주문."""
    order = Order(
        received_date="2026-08-01", customer_name=_ORDER_NAME,
        phone=_STALE_PHONE_COLUMN, address=_ORDER_ADDRESS,
        product="붙박이장", status="RECEIVED",
        erp_phone_digits=_CURRENT_DIGITS,
        created_at=now_utc_naive() - datetime.timedelta(days=3),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _phone_only_link(*, tel: str, external_id: str) -> ExternalOrderLink:
    """전화축으로만 걸릴 수 있는 수집분(이름·주소는 위 주문과 일부러 다르게 둔다)."""
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": f"N-{external_id}", "ordererTel": tel,
                      "ordererName": "다른이름"},
            "productOrder": {
                "productOrderId": external_id, "productName": "로라 무몰딩 1cm",
                "shippingAddress": {"name": "다른이름", "tel1": tel,
                                    "baseAddress": "부산시 해운대구 센텀로 10",
                                    "detailedAddress": "202동 302호"},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


def test_candidate_lookup_uses_indexed_phone_axis_only(app):
    """전화축은 ``erp_phone_digits`` 로만 문다 — 레거시 ``orders.phone`` 은 안 문다.

    양성: 인덱스 컬럼의 새 번호로 조회하면 찾는다.
    음성 대조군: 같은 주문을 ``orders.phone`` 의 옛 번호로 조회하면 **안 찾는다**.
    양성만 보면 축이 둘이어도 통과하므로 대조군이 계약의 본체다.
    """
    order = _stale_phone_order()

    hit = find_order_candidates(
        db_session, _phone_only_link(tel=_CURRENT_TEL, external_id="PO-AXIS-CUR"))
    assert [row["order_id"] for row in hit] == [order.id]
    assert hit[0]["reason"] == "수취인 전화 일치"

    miss = find_order_candidates(
        db_session, _phone_only_link(tel=_STALE_TEL, external_id="PO-AXIS-STALE"))
    assert miss == []


def test_phone_column_not_referenced_in_candidate_query(app):
    """회귀 방지 — 지운 갈래가 소스로 되살아나지 않았는지 본다.

    이 확인만으로는 조회의 실제 동작을 못 보므로 위 동작 테스트와 짝으로만 뜻이 있다.
    """
    source = inspect.getsource(candidates_mod)
    assert "Order.phone ==" not in source
