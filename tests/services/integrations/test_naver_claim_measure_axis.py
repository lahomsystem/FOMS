"""취소·반품 알림이 **실측 전인가 후인가**를 말한다 (2026-09-07 사용자 요구).

왜 이 계약이 필요한가: 가구는 실측을 나가면 사람·차·시간이 이미 나간 것이다.
**실측 전 취소**와 **실측 후 취소**는 회수·정산·고객 응대가 전부 다른데, 알림은
"취소 요청" 까지만 말하고 그 차이는 담당자가 주문을 따로 열어야 알 수 있었다.

고정하는 계약:

1. 주문이 붙은 집의 알림은 제목에 ``실측 후`` / ``실측 전`` / ``실측일 없음`` 이 붙고
   본문 첫 문장 뒤에 같은 사실이 한 문장으로 나온다.
2. 모르면 **모른다고 말한다** — 실측일이 없으면 날짜를 지어내지 않는다.
3. **음성 대조군**: 아직 주문으로 만들지 않은 수집분의 알림에는 ``실측`` 이라는 낱말이
   제목·본문 어디에도 없다. 붙일 근거가 없기 때문이다(변경 전 문안 그대로).
4. 집 묶음 계약은 그대로다 — 세부옵션 3건이 알림 1건이고, 실측 문장도 한 번만 나온다.

판정은 :func:`foms.services.orders.measure_progress.judge_measure_progress` 한 곳이다.
여기서는 그 판정이 만든 **문구가 알림에 실리는지**를 잰다.
"""

from __future__ import annotations

import datetime

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE,
    refresh_claims,
)
from foms.services.orders.measure_progress import (
    MEASURE_AFTER,
    MEASURE_BEFORE,
    MEASURE_NONE,
    judge_measure_progress,
)
from models import ExternalOrderLink, Notification, Order, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _admin() -> User:
    user = User(username=f"meas_admin_{_uid()}", password="pw-not-committed",
                name="관리자", role="ADMIN", team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _detail(external_id: str, *, order_no: str, claim: str = "CANCEL_REQUEST") -> dict:
    """상품주문 상세 1건 — ``order_no`` 가 같으면 같은 집이다."""
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "PAYED",
        "productName": "붙박이장",
        "productOption": "색상: 화이트",
        "totalPaymentAmount": 500000,
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    detail = {"order": {"orderId": order_no, "ordererName": "김주문"},
              "productOrder": product_order}
    if claim:
        detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    return detail


def _erp_order(measure_date: str | None) -> Order:
    """실측일이 ``measure_date`` 인 ERP 주문 1건(``None`` 이면 실측일 없음).

    ERP structured schedule 에 넣는다 — 실측일 정본 리더
    (:func:`foms.services.measurement_dates.extract_all_measurement_dates`)가 ERP 주문에서
    canonical 로 보는 자리다(싱크 컬럼이 아니다).

    단계는 ``RECEIVED`` 로 둔다 — 단계 축이 실측을 지나지 않아 **날짜 축이 판정한다**.
    """
    schedule = {"measurement": {"date": measure_date}} if measure_date else {}
    order = Order(customer_name="오유정", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-25",
                  status="RECEIVED", is_erp_order=True,
                  structured_data={"schedule": schedule})
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, order: Order | None = None) -> ExternalOrderLink:
    external_id = f"PO-{_uid()}"
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             sync_status="COLLECTED",
                             order_id=order.id if order is not None else None,
                             raw_snapshot=_detail(external_id, order_no=order_no,
                                                  claim=""))
    db_session.add(link)
    db_session.commit()
    return link


class FakeClient:
    """상세 조회만 흉내낸다(네이버로 나가는 HTTP 0회)."""

    def __init__(self, details: list[dict]):
        self._details = details

    def get_product_orders(self, ids):
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


def _sweep(links: list[ExternalOrderLink], *, order_no: str) -> None:
    """링크들에 취소를 한 스윕으로 흘려보낸다(운영과 같은 경로)."""
    details = [_detail(link.external_id, order_no=order_no) for link in links]
    changed = [{"productOrderId": link.external_id,
                "productOrderStatus": "CANCELED"} for link in links]
    refresh_claims(db_session, client=FakeClient(details), changed=changed)
    db_session.commit()


def _claims() -> list[Notification]:
    return (db_session.query(Notification)
            .filter(Notification.notification_type == NOTIFICATION_TYPE)
            .order_by(Notification.id).all())


def _shift(days: int) -> str:
    """오늘 기준 ``days`` 만큼 옮긴 날짜(YYYY-MM-DD)."""
    return (get_today_kst() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# 1. 실측 후 / 실측 전 / 모름
# --------------------------------------------------------------------------- #

def test_cancel_after_measurement_says_after(app):
    """실측일이 지난 주문의 취소 알림은 '실측 후'라고 말한다(비용이 이미 나갔다)."""
    _admin()
    order_no = f"N-{_uid()}"
    measured_on = _shift(-5)
    order = _erp_order(measured_on)
    assert judge_measure_progress(order).code == MEASURE_AFTER

    _sweep([_link(order_no=order_no, order=order)], order_no=order_no)

    row = _claims()[0]
    assert "실측 후" in row.title, "제목에 실측 축이 없다"
    assert "실측을 마친 뒤" in row.message
    # 날짜는 알림에서 ISO 로 말한다(화면은 MM-DD).
    assert measured_on in row.message


def test_cancel_before_measurement_says_before(app):
    """실측일이 아직 안 온 주문은 '실측 전'이다 — 아직 나간 비용이 없다."""
    _admin()
    order_no = f"N-{_uid()}"
    planned_on = _shift(5)
    order = _erp_order(planned_on)
    assert judge_measure_progress(order).code == MEASURE_BEFORE

    _sweep([_link(order_no=order_no, order=order)], order_no=order_no)

    row = _claims()[0]
    assert "실측 전" in row.title and "실측 후" not in row.title
    assert "아직 실측 전입니다" in row.message
    assert planned_on in row.message


def test_cancel_without_measurement_date_says_it_does_not_know(app):
    """실측일이 없으면 **모른다고 말한다** — 날짜를 지어내지 않는다."""
    _admin()
    order_no = f"N-{_uid()}"
    order = _erp_order(None)
    assert judge_measure_progress(order).code == MEASURE_NONE

    _sweep([_link(order_no=order_no, order=order)], order_no=order_no)

    row = _claims()[0]
    assert "실측일 없음" in row.title
    assert "모릅니다" in row.message
    # 아는 척 금지 — 없는 날짜를 만들어 적지 않는다.
    assert "실측 후" not in row.message and "실측 예정" not in row.message


# --------------------------------------------------------------------------- #
# 2. 음성 대조군 — 붙일 근거가 없으면 한 글자도 안 붙는다
# --------------------------------------------------------------------------- #

def test_unlinked_collection_notification_has_no_measure_words(app):
    """주문에 안 붙은 수집분의 알림에는 '실측' 이라는 낱말이 아예 없다.

    실측은 ERP 주문 1건의 사실이라, 주문이 없으면 잴 대상 자체가 없다. 이 건의 문안은
    변경 전과 **한 글자도** 같아야 한다(기존 계약 테스트가 title 정확일치로 잡는다).
    """
    _admin()
    order_no = f"N-{_uid()}"

    _sweep([_link(order_no=order_no)], order_no=order_no)

    row = _claims()[0]
    assert "실측" not in row.title and "실측" not in row.message
    assert row.title == "네이버 취소 요청 — 이수취"


# --------------------------------------------------------------------------- #
# 3. 집 묶음 계약은 그대로다
# --------------------------------------------------------------------------- #

def test_grouping_contract_survives_measure_axis(app):
    """세부옵션 3건이 알림 1건이고, 실측 문장도 그 1건에 한 번만 나온다."""
    _admin()
    order_no = f"N-{_uid()}"
    order = _erp_order(_shift(-3))
    links = [_link(order_no=order_no, order=order) for _ in range(3)]

    _sweep(links, order_no=order_no)

    rows = _claims()
    assert len(rows) == 1, "세부옵션 수만큼 알림이 생겼다(집 묶음 회귀)"
    assert f"상품주문번호 {links[0].external_id} 외 2건" in rows[0].message
    assert rows[0].message.count("실측을 마친 뒤") == 1
    assert rows[0].title.count("실측 후") == 1
