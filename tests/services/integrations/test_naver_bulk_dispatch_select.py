"""NAVER-BULKDISPATCH-01 T1: 일괄 발송처리 **대상 선별** 계약.

되돌릴 수 없는 조작의 대상을 정하는 함수다. 그래서 이 파일은 "골라야 할 것을 고르는가"
만큼 **"고르지 말아야 할 것을 안 고르는가"** 에 무게를 둔다 — 양성 후보만 세는 것은
전수가 아니다.

음성 대조군 3종(전부 모집단 **안에서** 고른다 — 술어가 발동할 수 있는 집합 밖 표본은
통과해도 반증이 아니다):

1. 예약금·전화 접수로 만든 ERP 주문 — 링크가 아예 없다.
2. 같은 날 실측인데 **이미 발송된** 네이버 주문 — 우리 표식 / 네이버 원본 양쪽.
3. **링크가 붙은 예약금 주문** — 손으로 재결제를 붙이면 링크가 생긴다. 이건 빠지면 안
   되고 **집 단위로** 정확히 한 집이어야 한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.integrations.naver_commerce.bulk_dispatch import select_targets
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, OrderScheduleDate

from tests.services.integrations.test_naver_workbench import _collected, _uid

TODAY = "2026-08-31"
OTHER_DAY = "2026-09-01"


@pytest.fixture(autouse=True)
def _fresh_db(app):
    """스키마 + 테스트마다 깨끗한 출발선(conftest ``app`` 이 리셋한다).

    선별 함수는 **모집단 전체**를 훑는다 — 앞 테스트가 남긴 행이 남아 있으면 "고르지
    말아야 할 것을 안 골랐다"는 단언이 다른 테스트의 잔재를 세게 된다.
    """
    yield


def _order(*, status: str = "MEASURE", customer: str = "김실측",
           orderer: str = "라홈") -> Order:
    """실측 대시보드 모집단에 드는 ERP 주문 1건.

    Args:
        status: 주문 상태(자가실측 계열이면 scope 가 뺀다).
        customer: 고객명(대조군 구분용).
        orderer: 발주사.

    Returns:
        커밋된 주문 행.
    """
    order = Order(
        received_date=TODAY, customer_name=customer, phone="010-5555-6666",
        address="서울 강남구 테헤란로 1", product="붙박이장",
        status=status, is_erp_order=True,
        structured_data={"parties": {"orderer": {"name": orderer}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _measured_on(order: Order, date: str = TODAY) -> None:
    """그 주문에 실측 일정을 붙인다 — 대시보드 당일 술어가 읽는 자리.

    Args:
        order: 대상 주문.
        date: ``YYYY-MM-DD``.
    """
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=date, source="beta_schedule"))
    db_session.commit()


def _link_to(order: Order, link: ExternalOrderLink) -> ExternalOrderLink:
    """수집 링크를 주문에 붙인다(승격이 하는 것과 같은 모양).

    Args:
        order: 붙일 주문.
        link: 수집된 링크.

    Returns:
        갱신된 링크 행.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return row


def _stamp_ours(link: ExternalOrderLink) -> None:
    """우리 표식(``triage_state.fulfillment.dispatched_at``)을 찍는다.

    Args:
        link: 대상 링크.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = {**(state.get("fulfillment") or {}),
                            "dispatched_at": "2026-08-30T10:00:00"}
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _stamp_naver(link: ExternalOrderLink) -> None:
    """네이버 원본 발송 기록(``delivery.sendDate``)을 얹는다 — 판매자센터 수동 발송분.

    Args:
        link: 대상 링크.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    snapshot = dict(row.raw_snapshot or {})
    snapshot["delivery"] = {"deliveryMethod": "DIRECT_DELIVERY",
                            "sendDate": "2026-08-30T14:03:00.000+09:00"}
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()


def _naver_order(*, order_no: str, date: str = TODAY, **kwargs) -> tuple[Order, ExternalOrderLink]:
    """당일 실측 + 네이버 링크가 붙은 주문 1건(정상 대상).

    Args:
        order_no: 네이버 묶음 주문번호.
        date: 실측일.
        **kwargs: :func:`_collected` 로 넘길 값.

    Returns:
        ``(주문, 링크)``.
    """
    order = _order(customer=kwargs.pop("customer", "김실측"))
    _measured_on(order, date)
    link = _collected(order_no=order_no, product="붙박이장", amount=1_000_000, **kwargs)
    return order, _link_to(order, link)


# --------------------------------------------------------------------------- #
# 양성 — 골라야 할 것
# --------------------------------------------------------------------------- #

def test_today_naver_order_is_selected_and_eligible():
    """당일 실측 + 네이버 링크 + 발주확인 완료 = 보낼 수 있는 집 1개."""
    _, link = _naver_order(order_no=f"N-OK-{_uid()}")
    targets = select_targets(db_session, on_date=TODAY)
    picked = [t for t in targets if link.id in t.link_ids]
    assert len(picked) == 1, "집이 하나로 접혀야 한다"
    assert picked[0].eligible is True
    assert picked[0].reason == ""
    assert picked[0].pending_link_ids == [link.id]


def test_other_day_measurement_is_not_selected():
    """다른 날 실측 건은 오늘 대상이 아니다(날짜 술어가 실제로 작동하는지)."""
    _, link = _naver_order(order_no=f"N-DAY-{_uid()}", date=OTHER_DAY)
    targets = select_targets(db_session, on_date=TODAY)
    assert not [t for t in targets if link.id in t.link_ids]


# --------------------------------------------------------------------------- #
# 음성 대조군 — 고르지 말아야 할 것
# --------------------------------------------------------------------------- #

def test_control_deposit_order_without_link_is_excluded():
    """대조군 1 — 예약금·전화 접수 ERP 주문은 링크가 없어 대상에서 빠진다."""
    order = _order(customer="박예약")
    _measured_on(order)
    targets = select_targets(db_session, on_date=TODAY)
    assert not [t for t in targets if int(order.id) in t.order_ids]


def test_control_already_dispatched_by_us_is_excluded():
    """대조군 2a — 우리가 이미 보낸 집은 다시 안 고른다."""
    _, link = _naver_order(order_no=f"N-OURS-{_uid()}")
    _stamp_ours(link)
    targets = select_targets(db_session, on_date=TODAY)
    assert not [t for t in targets if link.id in t.pending_link_ids]


def test_control_already_dispatched_in_naver_is_excluded():
    """대조군 2b — **판매자센터에서 사람이 직접 발송한 집**도 안 고른다.

    이게 화면 큐 술어(우리 표식만)와 갈리는 자리다. 화면 술어를 쓰면 이 집이 대상에 들고
    실행하면 ``FulfillmentError`` 로 떨어진다 — 일괄에서는 대량 실패 띠가 된다.
    """
    _, link = _naver_order(order_no=f"N-NV-{_uid()}")
    _stamp_naver(link)
    targets = select_targets(db_session, on_date=TODAY)
    assert not [t for t in targets if link.id in t.pending_link_ids]


def test_control_deposit_order_with_attached_link_is_selected_as_one_household():
    """대조군 3 — **링크가 붙은 예약금 주문**은 빠지면 안 되고, 집 단위로 하나여야 한다.

    예약금 주문에 손으로 재결제를 붙이면 링크가 생긴다(`attach_link_to_order` 는 대상
    주문의 출처를 검사하지 않는다). 그 주문의 예약금 부분에는 대응하는 네이버 상품주문이
    없으므로 **주문 수로 세면 틀리고 집 수로 세야 맞다**.
    """
    order = _order(customer="최예약")
    _measured_on(order)
    order_no = f"N-ATT-{_uid()}"
    first = _link_to(order, _collected(order_no=order_no, product="붙박이장", amount=500_000))
    second = _link_to(order, _collected(order_no=order_no, product="붙박이장", amount=500_000))
    targets = [t for t in select_targets(db_session, on_date=TODAY)
               if int(order.id) in t.order_ids]
    assert len(targets) == 1, "같은 주문번호·같은 주소면 한 집이다"
    assert sorted(targets[0].pending_link_ids) == sorted([first.id, second.id])


# --------------------------------------------------------------------------- #
# 서비스 가드에 없는 조건 — 선별이 대신 건다
# --------------------------------------------------------------------------- #

def test_broken_collection_is_reported_not_eligible():
    """``sync_status`` 가 깨진 수집분은 보낼 수 없다고 **표시**한다.

    ``_broken_collection_guard`` 는 발주확인에서만 불린다 — 발송처리는 그대로 나간다.
    단건은 사람이 보고 누르지만 일괄은 아무도 안 본 채로 나가므로 선별이 막는다.
    """
    _, link = _naver_order(order_no=f"N-BRK-{_uid()}")
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.sync_status = "PENDING_REVIEW"
    db_session.commit()
    picked = [t for t in select_targets(db_session, on_date=TODAY) if link.id in t.link_ids]
    assert len(picked) == 1, "조용히 빼지 않는다 — 사유와 함께 보여준다"
    assert picked[0].eligible is False
    assert "수집이 완전하지" in picked[0].reason


def test_place_pending_is_reported_not_eligible():
    """발주확인 전 집은 사유와 함께 보낼 수 없음으로 뜬다."""
    _, link = _naver_order(order_no=f"N-PP-{_uid()}", place_status="")
    picked = [t for t in select_targets(db_session, on_date=TODAY) if link.id in t.link_ids]
    assert len(picked) == 1
    assert picked[0].eligible is False
    assert "발주확인이 먼저" in picked[0].reason


def test_claim_blocked_household_is_reported_not_eligible():
    """취소·반품·교환이 걸린 집은 보낼 수 없다."""
    _, link = _naver_order(order_no=f"N-CLM-{_uid()}", claim_status="CANCEL_REQUEST")
    picked = [t for t in select_targets(db_session, on_date=TODAY) if link.id in t.link_ids]
    assert len(picked) == 1
    assert picked[0].eligible is False
    assert picked[0].reason


# --------------------------------------------------------------------------- #
# 화면 필터·캡을 상속하지 않는다
# --------------------------------------------------------------------------- #

def test_selection_ignores_display_cap():
    """표시 캡(300)은 모집단이 아니다 — 캡 뒤에서 좁히면 섹션이 통째로 빈다."""
    from foms.services.measurement_read_model import MEASUREMENT_MAIN_DISPLAY_CAP

    assert MEASUREMENT_MAIN_DISPLAY_CAP, "캡 상수가 사라지면 이 계약을 다시 봐야 한다"
    import inspect

    from foms.services.integrations.naver_commerce import bulk_dispatch

    source = inspect.getsource(bulk_dispatch)
    assert "MEASUREMENT_MAIN_DISPLAY_CAP" not in source, (
        "선별이 화면 캡을 참조하면 캡 밖 주문이 조용히 대상에서 빠진다"
    )


def test_selection_does_not_read_request_filters():
    """검색어·담당자·mine 필터를 읽지 않는다 — 누가 눌러도 같은 대상이어야 한다."""
    import inspect

    from foms.services.integrations.naver_commerce import bulk_dispatch

    source = inspect.getsource(bulk_dispatch)
    for needle in ("request", "mine_only", "manager_filter"):
        assert needle not in source, f"선별이 화면 필터({needle})를 상속하면 안 된다"


def test_selection_does_not_use_structured_source_marker():
    """``structured_data['source']`` 로 네이버 유래를 판정하지 않는다(오염분 존재)."""
    import inspect

    from foms.services.integrations.naver_commerce import bulk_dispatch

    source = inspect.getsource(bulk_dispatch)
    assert "SOURCE_MARKER" not in source
    assert "naver_linked" not in source
