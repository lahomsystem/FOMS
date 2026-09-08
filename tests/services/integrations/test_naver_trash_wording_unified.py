# -*- coding: utf-8 -*-
"""휴지통 낱말이 **세 화면에서 한 벌인가** (2026-09-07).

같은 주문이 pane 머리줄에서는 `09-07 08:41`, 후보 표에서는 `2026-09-07 08:41:17` 이라고
떴다. 판정식도 두 벌이었다 — 머리줄은 :func:`orders.state_axes.read_deleted`, 후보 표는
제 식(``deleted_at is not None or status == 'DELETED'``)이었다. 그래서 legacy 축
(``status='DELETED'`` 인데 컬럼은 비어 있는 246건)에서는 후보 표가 "휴지통"이라고만
말하고 **언제인지는 빈칸**이었다.

여기서 못박는 것 다섯:

1. 정본 projection 주문의 후보 행 시각이 ``read_order_trash`` 결과와 **문자 그대로** 같고
   ``MM-DD HH:MM``(KST) 이다.
2. legacy 축 주문도 시각을 되찾는다 — 빈칸이 아니다.
3. 음성 대조군: 복원된 주문은 삭제 흔적이 남아 있어도 조용하다.
4. 위치 계약: ``read_order_trash`` 는 :mod:`foms.services.orders.soft_delete` 에 산다.
   네이버 모듈은 **재수출하지 않는다**(이름이 두 자리에 남으면 다시 갈라 쓴다).
5. 검색 표도 같은 문자열이다 — 후보 표와 같은 ``_order_view`` 를 쓴다.

휴지통에 넣을 때는 정본 엔진(:func:`orders.soft_delete.soft_delete_order`)만 쓴다. 컬럼에
문자열을 직접 꽂으면 ``structured_data['delete']`` 가 안 생겨 실제 경로를 안 재는 셈이다.
"""
import datetime
import re

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.order_candidates import (
    find_order_candidates,
    search_orders_for_attach,
)
from foms.services.orders.soft_delete import read_order_trash, soft_delete_order
from models import ExternalOrderLink, Order, User

#: 화면에 적히는 시각 모양 — 연도가 없다(세 화면 한 벌을 택한 대가).
TRASH_AT_SHAPE = re.compile(r"^\d{2}-\d{2} \d{2}:\d{2}$")

#: 저장은 naive=UTC 규약이다. 기대값을 피검 코드와 **같은 변환기**로 만들면 KST 축이
#: 동어반복이 되므로 손으로 적은 리터럴로 못박는다: 09-06 23:41 UTC + 9h = 09-07 08:41.
TRASHED_AT_UTC = datetime.datetime(2026, 9, 6, 23, 41, 17)
TRASHED_AT_KST_TEXT = "09-07 08:41"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


def _actor() -> User:
    """행위자 1명. soft delete 는 actor 와 OrderEvent 를 남기므로 실제 행이 필요하다."""
    user = User(username=f"twu_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(*, phone: str, status: str = "RECEIVED") -> Order:
    """후보 표에 걸릴 ERP 주문 1건(수취인 전화 일치 축)."""
    order = Order(received_date="2026-08-01", customer_name=f"한벌{_uid()}", phone=phone,
                  erp_phone_digits=phone.replace("-", ""),
                  address="서울시 강남구 테헤란로 152 101동 1001호", product="붙박이장",
                  status=status, payment_amount=0, is_erp_order=True,
                  created_at=now_utc_naive() - datetime.timedelta(days=3))
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, phone: str) -> ExternalOrderLink:
    """아직 주문에 안 붙은 수집분 1줄 — 후보/검색의 기준 링크."""
    external_id = f"PO-TWU-{_uid()}"
    link = ExternalOrderLink(
        channel=CHANNEL, external_id=external_id, sync_status="COLLECTED",
        raw_snapshot={
            "order": {"orderId": f"N-TWU-{external_id}", "ordererTel": phone},
            "productOrder": {
                "productOrderId": external_id, "productName": "붙박이장",
                "totalPaymentAmount": 500_000,
                "shippingAddress": {"name": "이수취", "tel1": phone,
                                    "baseAddress": "서울시 강남구 테헤란로 152",
                                    "detailedAddress": "101동 1001호"},
            },
        },
    )
    db_session.add(link)
    db_session.commit()
    return link


def _trash(order: Order, *, actor: User, reason: str = "고객 취소 확정") -> None:
    """정본 엔진으로 휴지통에 넣는다 — 컬럼에 값을 직접 꽂지 않는다."""
    soft_delete_order(db_session, order_id=int(order.id), actor_user_id=int(actor.id),
                      reason=reason, now=TRASHED_AT_UTC)
    db_session.commit()


def _row(link: ExternalOrderLink, order: Order) -> dict:
    """후보 표에서 그 주문의 행 하나를 집는다."""
    rows = find_order_candidates(db_session, link)
    picked = [row for row in rows if int(row["order_id"]) == int(order.id)]
    assert picked, f"후보 표에 주문 #{order.id} 이 없다 — 모집단이 흔들렸다"
    return picked[0]


def test_candidate_row_says_the_same_words_as_the_pane(app):
    """정본 projection 주문 — 후보 행 시각이 ``read_order_trash`` 와 문자 그대로 같다."""
    actor = _actor()
    phone = "010-7610-0001"
    order = _order(phone=phone)
    _trash(order, actor=actor)

    row = _row(_link(phone=phone), order)

    assert row["trashed"] is True
    assert row["trashed_at"] == read_order_trash(order)["trashed_at_text"], (
        "후보 표와 pane 머리줄이 같은 사실을 두 문자열로 말한다")
    assert TRASH_AT_SHAPE.match(row["trashed_at"]), row["trashed_at"]
    assert row["trashed_at"] == TRASHED_AT_KST_TEXT, "KST 환산이 어긋났다"


def test_legacy_status_axis_recovers_the_time(app):
    """legacy 축(컬럼은 비고 단계만 ``DELETED``)도 시각을 되찾는다 — 옛 식은 빈칸이었다.

    운영 휴지통 308건 중 246건이 이 모양이다(2026-09-07 읽기전용 조회). 후보 표가
    컬럼만 읽던 시절에는 그 246건 전부가 "언제 접혔는지"를 말하지 못했다.
    """
    actor = _actor()
    phone = "010-7610-0002"
    order = _order(phone=phone)
    _trash(order, actor=actor)
    # legacy 미러가 status 를 덮고 컬럼은 비어 있던 모양을 그대로 만든다.
    order.deleted_at = None
    order.status = "DELETED"
    db_session.commit()
    assert (order.structured_data or {}).get("delete"), "legacy 모양을 못 만들면 검증이 헛돈다"

    row = _row(_link(phone=phone), order)

    assert row["trashed"] is True
    assert row["trashed_at"] != "", "컬럼이 비었다고 언제인지를 못 말하면 안 된다"
    assert row["trashed_at"] == TRASHED_AT_KST_TEXT


def test_restored_order_is_silent_in_the_candidate_table(app):
    """음성 대조군 — 복원된 주문은 삭제 흔적이 남아 있어도 아무 말도 안 한다.

    legacy 복원 분기(``foms/web/orders/trash.py:318``)는 컬럼과 status 만 되돌리고
    ``structured_data['delete']`` 를 pop 하지 않는다. projection 을 무조건 읽으면
    살아 있는 주문 행에 삭제 시각이 찍힌다.
    """
    actor = _actor()
    phone = "010-7610-0003"
    order = _order(phone=phone)
    _trash(order, actor=actor)
    order.deleted_at = None
    order.status = "RECEIVED"
    db_session.commit()
    assert (order.structured_data or {}).get("delete"), "복원 잔재를 못 만들면 검증이 헛돈다"

    row = _row(_link(phone=phone), order)

    assert row["trashed"] is False, "복원했는데 후보 표가 휴지통이라고 말한다"
    assert row["trashed_at"] == "", "복원된 주문에 삭제 시각이 찍혔다"


def test_read_order_trash_lives_in_soft_delete_only(app):
    """위치 계약 — 쓰는 자리와 읽는 자리를 한 파일에 둔다. 재수출은 없다.

    이름이 두 자리에 남아 있으면 다음 사람이 다시 갈라 쓰고, 오늘 고친 드리프트가
    그대로 돌아온다(그래서 ``ghost_orders.__all__`` 을 음성 대조군으로 함께 잰다).
    """
    from foms.services.integrations.naver_commerce import ghost_orders
    from foms.services.orders import soft_delete

    assert soft_delete.read_order_trash is read_order_trash
    assert "read_order_trash" in soft_delete.__all__
    assert "read_order_trash" not in ghost_orders.__all__, "네이버 모듈이 다시 재수출했다"


def test_search_table_says_the_same_words(app):
    """검색 표도 같은 문자열이다 — 후보 표와 같은 ``_order_view`` 를 쓴다."""
    actor = _actor()
    phone = "010-7610-0004"
    order = _order(phone=phone)
    _trash(order, actor=actor)
    link = _link(phone=phone)

    found = search_orders_for_attach(db_session, link, query=f"#{int(order.id)}")

    rows = [row for row in found["rows"] if int(row["order_id"]) == int(order.id)]
    assert rows, "손으로 주문번호를 쳤는데 검색 표가 그 주문을 못 냈다"
    assert rows[0]["trashed"] is True
    assert rows[0]["trashed_at"] == TRASHED_AT_KST_TEXT
    assert rows[0]["trashed_at"] == _row(link, order)["trashed_at"], (
        "검색 표와 후보 표가 같은 주문을 두 문자열로 말한다")
