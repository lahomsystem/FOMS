"""NAVER-BULKDISPATCH-01 T2: 오늘 실측한 네이버 건 **미리보기 띠** 계약.

이 띠는 아직 버튼이 없다 — 그게 계약이다. 5시에 무엇이 나갈지 보여주기만 하고 아무것도
보내지 않는다. 그래서 이 파일이 가장 무겁게 재는 것은 **"띠가 조작 수단을 만들지 않았다"**
이다. 미리보기에 실행 버튼이 슬쩍 끼면 사람이 대상 목록을 확인하기 전에 누른다.

두 번째 무게는 **재진술의 정직함**이다. 보낼 수 없는 집을 조용히 빼면 띠가 "N집"이라고
말하면서 실제 대상은 다른 수가 된다 — 화면 큐와 워커가 갈렸던 것과 같은 모양의 결함이다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import ExternalOrderLink, Order, OrderScheduleDate

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"


@pytest.fixture()
def today() -> str:
    """오늘(KST) — 띠가 세는 날짜와 같은 자리에서 얻는다.

    Returns:
        ``YYYY-MM-DD``.
    """
    return get_today_kst().strftime("%Y-%m-%d")


def _order_measured_today(today: str, *, customer: str = "김실측",
                          done: bool = True) -> Order:
    """오늘 실측 일정이 잡힌 ERP 주문 1건.

    Args:
        today: 오늘 날짜 문자열.
        customer: 고객명.
        done: 실측완료 표시 여부.

    Returns:
        커밋된 주문 행.
    """
    order = Order(received_date=today, customer_name=customer,
                  phone="010-5555-6666", address="서울 강남구 테헤란로 1",
                  product="붙박이장", status="MEASURE", is_erp_order=True,
                  measurement_completed=done)
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    return order


def _linked(order: Order, **kwargs) -> ExternalOrderLink:
    """수집 링크를 그 주문에 붙인다.

    Args:
        order: 붙일 주문.
        **kwargs: :func:`_collected` 인자.

    Returns:
        갱신된 링크 행.
    """
    link = _collected(order_no=kwargs.pop("order_no", f"N-PV-{_uid()}"),
                      product="붙박이장", amount=1_000_000, **kwargs)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return row


def _body(client) -> str:
    """처리 탭 화면 본문.

    Args:
        client: 로그인된 테스트 클라이언트.

    Returns:
        HTML 문자열.
    """
    response = client.get(f"{TRIAGE_PATH}?tab=work")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_strip_counts_today_naver_households(client, workbench_on, today):
    """오늘 실측 + 네이버 링크가 있으면 띠가 집 수를 말한다."""
    _login(client)
    _linked(_order_measured_today(today))
    body = _body(client)
    assert 'data-wb-bulk-dispatch="1"' in body
    assert "오늘 실측한 네이버 건" in body


def test_strip_absent_without_naver_link(client, workbench_on, today):
    """예약금·전화 접수 건만 있으면 띠가 아예 안 뜬다(0집에 빈 띠를 만들지 않는다)."""
    _login(client)
    _order_measured_today(today, customer="박예약")
    assert "data-wb-bulk-dispatch=" not in _body(client)


def test_strip_shows_blocked_household_with_reason(client, workbench_on, today):
    """보낼 수 없는 집도 **사유와 함께** 뜬다 — 조용히 빼지 않는다."""
    _login(client)
    _linked(_order_measured_today(today), place_status="")
    body = _body(client)
    assert 'data-wb-bulk-dispatch="1"' in body
    assert "보낼 수 없음" in body
    assert "발주확인이 먼저" in body


def test_strip_separates_eligible_from_blocked_in_summary(client, workbench_on, today):
    """머리말이 '보낼 수 있는 집'과 '먼저 해결할 집'을 나눠 말한다.

    총 집 수만 말하면 사람이 그 수가 그대로 나간다고 읽는다.
    """
    _login(client)
    _linked(_order_measured_today(today, customer="김보냄"))
    _linked(_order_measured_today(today, customer="이막힘"), place_status="")
    body = _body(client)
    assert 'data-wb-bulk-dispatch="2"' in body
    assert "지금 보낼 수 있는 집 1집" in body
    assert "먼저 해결할 집 1집" in body


def test_strip_marks_schedule_only_household(client, workbench_on, today):
    """실측 **일정**만 있고 완료 표시가 없으면 그렇게 말한다.

    일정과 완료는 다른 축이다. 방문 취소·부재 건이 5시 대상에 그대로 든다 — 거르지는
    않되(사람의 결정이다) 눈에 보이게 한다.
    """
    _login(client)
    _linked(_order_measured_today(today, done=False))
    body = _body(client)
    assert "완료 표시 없음" in body
    assert "방문했는지 확인하세요" in body


def test_strip_says_nothing_is_sent_yet(client, workbench_on, today):
    """미리보기라는 사실과 취소 불가를 머리말이 직접 말한다."""
    _login(client)
    _linked(_order_measured_today(today))
    body = _body(client)
    assert "아직 아무것도 나가지 않습니다" in body
    assert "취소할 수 없습니다" in body


def test_strip_has_no_execute_control(client, workbench_on, today):
    """**띠에 실행 수단이 없다** — T2 는 읽기 전용이다.

    미리보기에 버튼이 슬쩍 끼면 사람이 대상 목록을 확인하기 전에 누른다. 되돌릴 수 없는
    조작이라 "아직 없다"가 이 단계의 계약이다.
    """
    _login(client)
    _linked(_order_measured_today(today))
    body = _body(client)
    start = body.index('data-wb-bulk-dispatch="1"')
    strip = body[start:body.index("</details>", start)]
    assert "<button" not in strip, "미리보기 띠에 버튼이 있으면 안 된다"
    assert "<form" not in strip
    for needle in ("bulk-dispatch-confirm", "action=\"dispatch\"", "wb-bulk-dispatch-run"):
        assert needle not in strip
