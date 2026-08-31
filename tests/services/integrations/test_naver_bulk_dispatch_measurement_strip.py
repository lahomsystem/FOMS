"""NAVER-BULKDISPATCH-01 T3: 실측 대시보드의 발송처리 미리보기 띠 계약.

같은 미리보기를 두 화면에 낸다. 그래서 이 파일이 가장 무겁게 재는 것은 **두 화면이 같은
값을 쓴다**는 것이다 — 화면마다 따로 세면 두 화면이 다른 수를 말하고, 그건 네이버 집 수가
45집 vs 43집으로 갈렸던 결함과 같은 모양이다.

**픽스처 함정(2026-08-31 발견)**: `OrderScheduleDate` 행만 손으로 꽂으면 안 된다. 실측
대시보드 요청이 그 테이블을 **재빌드**하면서 정본(`structured_data.schedule.measurement.date`)
이 없는 고아 행을 지운다. 직접 호출 테스트(T1)는 그 경로를 안 타서 통과하고 화면 테스트만
빨개진다 — 두 번 속지 않게 여기 적어 둔다.

두 번째는 **날짜 정직성**이다. 다른 날짜를 보는 중에 "오늘 실측한 네이버 건"을 띄우면
화면이 거짓말을 한다. 실행 버튼이 붙는 날에는 더 나쁘다 — 옆에 다른 날짜 목록을 두고
오늘 것을 보내게 된다.
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
)

MEASUREMENT_PATH = "/erp/measurement"


@pytest.fixture()
def today() -> str:
    """오늘(KST).

    Returns:
        ``YYYY-MM-DD``.
    """
    return get_today_kst().strftime("%Y-%m-%d")


def _naver_measured_today(today: str, *, customer: str = "김실측") -> ExternalOrderLink:
    """오늘 실측 일정 + 네이버 링크가 붙은 주문 1건.

    Args:
        today: 오늘 날짜 문자열.
        customer: 고객명.

    Returns:
        붙인 링크 행.
    """
    order = Order(received_date=today, customer_name=customer,
                  phone="010-5555-6666", address="서울 강남구 테헤란로 1",
                  product="붙박이장", status="MEASURE", is_erp_order=True,
                  measurement_completed=True, measurement_date=today,
                  erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    link = _collected(order_no=f"N-MS-{_uid()}", product="붙박이장", amount=1_000_000)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return row


def _body(client, query: str = "") -> str:
    """실측 대시보드 본문.

    Args:
        client: 로그인된 클라이언트.
        query: 쿼리스트링(앞의 ``?`` 포함).

    Returns:
        HTML 문자열.
    """
    response = client.get(f"{MEASUREMENT_PATH}{query}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_strip_renders_on_measurement_dashboard(client, today):
    """오늘 실측 + 네이버 링크가 있으면 실측 대시보드에도 띠가 뜬다."""
    _login(client)
    _naver_measured_today(today)
    body = _body(client)
    assert 'data-naver-dispatch-count="1"' in body
    assert "오늘 실측한 네이버 건" in body


def test_strip_absent_without_naver_link(client, today):
    """예약금·전화 접수 건만 있으면 띠가 안 뜬다."""
    _login(client)
    order = Order(received_date=today, customer_name="박예약", phone="010-1-2",
                  address="서울 강남구 1", product="붙박이장", status="MEASURE",
                  is_erp_order=True, measurement_date=today,
                  erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    assert "data-naver-dispatch-count=" not in _body(client)


def test_strip_hidden_when_viewing_another_day(client, today):
    """**다른 날짜를 보는 중에는 띠가 안 뜬다** — 화면이 거짓말하지 않게.

    띠는 '오늘 실측한' 건을 말한다. 과거 날짜를 보는 중에 그대로 떠 있으면 사람이 그 목록이
    지금 화면의 날짜라고 읽는다.
    """
    _login(client)
    _naver_measured_today(today)
    assert 'data-naver-dispatch-count="1"' in _body(client)
    assert "data-naver-dispatch-count=" not in _body(client, "?date=2026-01-02")


def test_strip_matches_workbench_count(client, today):
    """**두 화면이 같은 수를 말한다** — 값 조립 함수를 공유하는지 소스로 판정.

    화면 렌더를 두 번 비교하는 것으로는 '우연히 같은 값'과 '같은 함수'를 구별하지 못한다.
    """
    import inspect

    from foms.web.admin import naver_ingest
    from foms.web.measurement import dashboard

    for module, name in ((naver_ingest, "워크벤치"), (dashboard, "실측 대시보드")):
        assert "build_preview" in inspect.getsource(module), (
            f"{name}가 미리보기 값을 따로 조립하면 두 화면이 다른 수를 말한다"
        )


def test_measurement_strip_has_no_execute_control(client, today):
    """실측 대시보드 띠에도 실행 수단이 없다(T3 는 읽기 전용)."""
    _login(client)
    _naver_measured_today(today)
    body = _body(client)
    start = body.index('data-naver-dispatch-count="1"')
    strip = body[start:body.index("</details>", start)]
    assert "<button" not in strip
    assert "<form" not in strip


def test_strip_says_cancel_is_blocked_after_dispatch(client, today):
    """취소가 막힌다는 사실을 띠가 직접 말한다 — 누르는 사람이 매번 알아야 한다."""
    _login(client)
    _naver_measured_today(today)
    body = _body(client)
    assert "아직 아무것도 나가지 않습니다" in body
    assert "취소할 수 없습니다" in body
