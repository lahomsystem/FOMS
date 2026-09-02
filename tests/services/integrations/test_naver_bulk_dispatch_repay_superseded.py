"""NAVER-BULKDISPATCH-05: 취소 확정 뒤 **재결제 집으로 나간** 집 (2026-09-02).

왜 이 파일이 있나
-----------------
고객이 취소하고 다시 결제하면 같은 ERP 주문에 네이버 집이 둘 붙는다. 발송은 재결제 집으로
나가는데, 옛 집은 보낼 게 남은 채 취소가 걸려 있어 화면에 `보낼 수 없음` 빨간 줄로 **매일**
남았다(운영 #5087 문영미 — 옛 집 ``2026090197104651`` 취소 확정 5건, 재결제 집
``2026090230890571`` 이 2026-09-02 발송 완료). 사람이 매일 같은 줄을 다시 판단한다.

음성 대조군은 **모집단 안에서** 고른다 — 술어가 발동할 수 있는 집합 밖 표본은 통과해도
반증이 아니다:

1. 취소 확정인데 **재결제 집이 아직 안 나간** 집 — 내려가면 안 된다.
2. **확정 전** 취소(요청 단계) + 재결제 발송 — 아직 살아 있을 수 있어 내려가면 안 된다.
3. 취소가 **일부만** 걸린 집 + 재결제 발송 — 나머지는 진짜로 보내야 한다.
4. 재결제 집이 **다른 ERP 주문**에 붙어 있는 경우 — 남의 집으로 승계하면 안 된다.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.integrations.naver_commerce.bulk_dispatch import (
    build_day_summary, build_preview, select_targets,
)
from models import ExternalOrderLink, Order, OrderScheduleDate

from tests.services.integrations.test_naver_workbench import _collected, _uid

TODAY = "2026-08-31"


@pytest.fixture(autouse=True)
def _fresh_db(app):
    """스키마 + 테스트마다 깨끗한 출발선(conftest ``app`` 이 리셋한다)."""
    yield


def _order(customer: str = "문영미") -> Order:
    """당일 실측 일정이 잡힌 ERP 주문 1건.

    Args:
        customer: 고객명.

    Returns:
        커밋된 주문 행.
    """
    order = Order(
        received_date=TODAY, customer_name=customer, phone="010-5555-6666",
        address="서울 강남구 테헤란로 1", product="붙박이장",
        status="MEASURE", is_erp_order=True,
        structured_data={"parties": {"orderer": {"name": "라홈"}}},
    )
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=TODAY, source="beta_schedule"))
    db_session.commit()
    return order


def _attach(order: Order, link: ExternalOrderLink, *,
            relation: str = "NEW") -> ExternalOrderLink:
    """수집 링크를 주문에 붙인다(승격이 하는 것과 같은 모양).

    Args:
        order: 붙일 주문.
        link: 수집된 링크.
        relation: 링크 관계(``NEW``·``REPAY``).

    Returns:
        갱신된 링크 행.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    row.relation = relation
    db_session.commit()
    return row


def _dispatched(link: ExternalOrderLink) -> None:
    """우리 표식(``triage_state.fulfillment.dispatched_at``)을 찍는다.

    Args:
        link: 대상 링크.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = {**(state.get("fulfillment") or {}),
                            "dispatched_at": "2026-08-31T10:19:05"}
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _canceled_household(order: Order, *, order_no: str, count: int = 2,
                        claim_status: str = "CANCEL_DONE") -> list[ExternalOrderLink]:
    """취소가 걸린 옛 결제 집.

    Args:
        order: 붙일 ERP 주문.
        order_no: 네이버 묶음 주문번호.
        count: 상품주문 수.
        claim_status: 클레임 상태 원문.

    Returns:
        붙은 링크 목록.
    """
    rows = []
    for idx in range(count):
        link = _collected(order_no=order_no, product="옛 결제 %d" % idx,
                          amount=500_000, claim_status=claim_status)
        rows.append(_attach(order, link))
    return rows


def _repay_household(order: Order, *, order_no: str, count: int = 2,
                     dispatched: bool = True) -> list[ExternalOrderLink]:
    """재결제 집(기본은 이미 발송된 상태).

    Args:
        order: 붙일 ERP 주문.
        order_no: 네이버 묶음 주문번호.
        count: 상품주문 수.
        dispatched: 발송 표식을 찍을지.

    Returns:
        붙은 링크 목록.
    """
    rows = []
    for idx in range(count):
        link = _collected(order_no=order_no, product="재결제 %d" % idx, amount=500_000)
        row = _attach(order, link, relation="REPAY")
        if dispatched:
            _dispatched(row)
        rows.append(row)
    return rows


def _target_of(order_no: str):
    """그 네이버 주문번호의 집 1개를 오늘 요약에서 찾는다.

    Args:
        order_no: 네이버 묶음 주문번호.

    Returns:
        :class:`BulkDispatchTarget`.
    """
    targets = [t for t in build_day_summary(db_session, on_date=TODAY)
               if t.external_order_no == order_no]
    assert len(targets) == 1, "집이 하나로 접히지 않았다: %d" % len(targets)
    return targets[0]


# --------------------------------------------------------------------------- #
# 양성 — 내려가야 할 것
# --------------------------------------------------------------------------- #

def test_canceled_household_with_dispatched_repay_is_superseded():
    """운영 #5087 의 모양 — 취소 확정 집 + 이미 나간 재결제 집 = `superseded`."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no)
    _repay_household(order, order_no=new_no)

    target = _target_of(old_no)
    assert target.state == "superseded", "취소 확정 + 재결제 발송인데 안 내려갔다"
    assert target.eligible is False
    assert target.superseded_by == new_no, "어느 집으로 나갔는지를 말해야 한다"
    assert target.superseded_at, "나간 시각이 비었다"
    assert target.reason == "", "끝난 줄에 막힘 사유가 남았다"


def test_superseded_is_not_a_send_target():
    """`superseded` 집은 보낼 대상에서 빠진다 — 매일 세면 띠가 영영 partial 이다."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no)
    _repay_household(order, order_no=new_no)

    preview = build_preview(db_session, on_date=TODAY)
    assert preview["superseded"] == 1
    assert not [row for row in preview["rows"] if row["order_no"] == old_no], \
        "재결제로 나간 옛 집이 '보낼 대상'에 남았다"
    # 목록에서 **빼지는** 않는다 — 사람이 확인할 자리가 있어야 한다.
    assert [row for row in preview["day_rows"] if row["order_no"] == old_no], \
        "옛 집이 화면 목록에서 통째로 사라졌다"


def test_superseded_household_is_never_sendable():
    """선별에도 안 걸린다 — 되돌릴 수 없는 호출의 대상이 되면 안 된다."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no)
    _repay_household(order, order_no=new_no)

    sendable = [t for t in select_targets(db_session, on_date=TODAY) if t.eligible]
    assert not [t for t in sendable if t.external_order_no == old_no]


# --------------------------------------------------------------------------- #
# 음성 대조군 — 내려가면 안 되는 것
# --------------------------------------------------------------------------- #

def test_control_canceled_without_dispatched_repay_stays_blocked():
    """대조군 1 — 재결제 집이 아직 안 나갔으면 옛 집은 그대로 막힌 줄이다."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no)
    _repay_household(order, order_no=new_no, dispatched=False)

    target = _target_of(old_no)
    assert target.state == "blocked"
    assert target.superseded_by == ""


def test_control_pending_claim_is_not_superseded():
    """대조군 2 — **확정 전** 취소 요청은 아직 살아 있을 수 있다."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no, claim_status="CANCEL_REQUEST")
    _repay_household(order, order_no=new_no)

    target = _target_of(old_no)
    assert target.state == "blocked", "확정 전 취소인데 끝난 줄로 내려갔다"


def test_control_partially_canceled_household_is_not_superseded():
    """대조군 3 — 일부만 취소된 집은 나머지를 진짜로 보내야 한다."""
    order = _order()
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(order, order_no=old_no, count=1)
    _attach(order, _collected(order_no=old_no, product="살아 있는 줄", amount=700_000))
    _repay_household(order, order_no=new_no)

    target = _target_of(old_no)
    assert target.state != "superseded", "살아 있는 상품주문이 있는데 끝난 줄이 됐다"


def test_control_repay_on_other_order_does_not_supersede():
    """대조군 4 — 남의 ERP 주문으로 나간 집은 승계 근거가 아니다."""
    mine, other = _order(), _order(customer="다른고객")
    old_no, new_no = "OLD-%s" % _uid(), "NEW-%s" % _uid()
    _canceled_household(mine, order_no=old_no)
    _repay_household(other, order_no=new_no)

    target = _target_of(old_no)
    assert target.state == "blocked", "다른 주문의 발송으로 내 집이 끝난 줄이 됐다"
