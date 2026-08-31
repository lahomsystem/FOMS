"""NAVER-BULKDISPATCH-02 T2~T5: **결과가 화면에 남는가** 계약.

1회차 운영(2026-08-31)에서 버튼을 누르고 새로고침했더니 띠가 통째로 사라졌다. 발송된 집이
대상에서 빠져 0집이 됐기 때문인데, 그 "사라짐"이 두 가지를 동시에 뜻했다 — ①다 잘 나갔다
②애초에 대상이 없었다. 되돌릴 수 없는 조작에서 그 둘이 구분 안 되면 사람이 판매자센터를
다시 열게 되고, 이 기능이 없앤 일이 되살아난다.

그래서 이 파일이 재는 것은 **화면이 그 둘을 다른 문구로 말하는가** 이고, 두 화면(워크벤치·
실측 대시보드)이 **같은 값**으로 그렇게 하는가다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

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
MEASUREMENT_PATH = "/erp/measurement"
STATE_PATH = "/admin/naver-ingest/bulk-dispatch/state"
_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def today() -> str:
    """오늘(KST).

    Returns:
        ``YYYY-MM-DD``.
    """
    return get_today_kst().strftime("%Y-%m-%d")


def _naver_measured_today(today: str, *, customer: str = "김실측",
                          **kwargs) -> ExternalOrderLink:
    """오늘 실측 일정 + 네이버 링크가 붙은 주문 1건.

    ``OrderScheduleDate`` 행만 꽂으면 안 된다 — 실측 대시보드 요청이 그 테이블을
    재빌드하면서 정본(``structured_data.schedule.measurement.date``)이 없는 고아 행을
    지운다. 직접 호출 테스트는 그 경로를 안 타서 통과하고 화면 테스트만 빨개진다.

    Args:
        today: 오늘 날짜 문자열.
        customer: 고객명.
        **kwargs: :func:`_collected` 인자.

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
    link = _collected(order_no=f"N-RU-{_uid()}", product="붙박이장",
                      amount=1_000_000, **kwargs)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return row


def _stamp_ours(link: ExternalOrderLink) -> None:
    """우리 표식(발송 완료)을 찍는다.

    Args:
        link: 대상 링크.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = {**(state.get("fulfillment") or {}),
                            "dispatched_at": "2026-08-30T22:45:00"}
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _stamp_naver(link: ExternalOrderLink) -> None:
    """판매자센터 수동 발송 기록을 얹는다.

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


def _stamp_failure(link: ExternalOrderLink) -> None:
    """발송처리 실패 표식을 얹는다.

    Args:
        link: 대상 링크.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = {**(state.get("fulfillment") or {}),
                            "last_error": "발송처리에 실패했습니다: 네이버 500",
                            "last_error_at": "2026-08-31T07:45:00",
                            "last_error_action": "dispatch"}
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _work(client) -> str:
    """워크벤치 처리 탭 본문.

    Args:
        client: 로그인된 클라이언트.

    Returns:
        HTML 문자열.
    """
    response = client.get(f"{TRIAGE_PATH}?tab=work")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _measurement(client) -> str:
    """실측 대시보드 본문.

    Args:
        client: 로그인된 클라이언트.

    Returns:
        HTML 문자열.
    """
    response = client.get(MEASUREMENT_PATH)
    assert response.status_code == 200
    return response.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 워크벤치 — 4상태가 갈리는가
# --------------------------------------------------------------------------- #

def test_workbench_says_done_after_everything_is_sent(client, workbench_on, today):
    """**전부 나간 날에도 띠가 남고 '완료'라고 말한다** — 이 작업의 존재 이유."""
    _login(client)
    _stamp_ours(_naver_measured_today(today))
    body = _work(client)
    assert 'data-wb-bulk-dispatch-state="done"' in body
    assert "발송처리 완료" in body
    assert "판매자센터를 다시 열 필요 없습니다" in body


def test_workbench_strip_is_absent_when_no_naver_order_today(client, workbench_on, today):
    """**오늘 대상이 아예 없는 날은 문구가 다르다** — 띠 자체가 없다.

    "다 나갔다"와 같은 모양이면 안 된다. 그 둘이 같은 모양이었던 것이 1회차 결함이다.
    """
    _login(client)
    order = Order(received_date=today, customer_name="박예약", phone="010-1-2",
                  address="서울 강남구 1", product="붙박이장", status="MEASURE",
                  is_erp_order=True, measurement_date=today, erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    body = _work(client)
    assert "data-wb-bulk-dispatch=" not in body
    assert "발송처리 완료" not in body


def test_workbench_says_partial_with_both_numbers(client, workbench_on, today):
    """일부만 나간 날은 **보낸 수와 남은 수를 함께** 말한다."""
    _login(client)
    _stamp_ours(_naver_measured_today(today, customer="김보냄"))
    _naver_measured_today(today, customer="이남음")
    body = _work(client)
    assert 'data-wb-bulk-dispatch-state="partial"' in body
    assert "2집 중" in body and "1집 발송됨" in body and "1집 남음" in body


def test_workbench_shows_failure_line_with_reason(client, workbench_on, today):
    """실패한 집은 **빨간 줄 + 사유**로 뜬다 — 다시 보낼 사람이 이유를 알아야 한다."""
    _login(client)
    _stamp_failure(_naver_measured_today(today))
    body = _work(client)
    assert "발송처리 실패 1집" in body
    assert "네이버 500" in body


def test_workbench_marks_seller_center_manual_dispatch(client, workbench_on, today):
    """**판매자센터에서 사람이 보낸 집**은 그렇게 말한다 — 우리가 한 일과 구별된다."""
    _login(client)
    _stamp_naver(_naver_measured_today(today))
    body = _work(client)
    assert 'data-wb-bulk-dispatch-state="done"' in body
    assert "판매자센터에서 보낸 건입니다" in body


# --------------------------------------------------------------------------- #
# 실측 대시보드 — 같은 값으로 같은 말을
# --------------------------------------------------------------------------- #

def test_measurement_strip_says_done_after_everything_is_sent(client, today):
    """실측 대시보드도 전부 나간 날 '완료'라고 말한다(띠가 사라지지 않는다)."""
    _login(client)
    _stamp_ours(_naver_measured_today(today))
    body = _measurement(client)
    assert 'data-naver-dispatch-state="done"' in body
    assert "네이버 발송처리 완료" in body


def test_measurement_strip_says_partial(client, today):
    """실측 대시보드도 보낸 수와 남은 수를 함께 말한다."""
    _login(client)
    _stamp_ours(_naver_measured_today(today, customer="김보냄"))
    _naver_measured_today(today, customer="이남음")
    body = _measurement(client)
    assert 'data-naver-dispatch-state="partial"' in body
    assert "1집 발송됨" in body and "1집 남음" in body


def test_measurement_strip_absent_when_no_naver_order(client, today):
    """네이버 건이 없으면 실측 대시보드에도 띠가 없다."""
    _login(client)
    order = Order(received_date=today, customer_name="박예약", phone="010-1-2",
                  address="서울 강남구 1", product="붙박이장", status="MEASURE",
                  is_erp_order=True, measurement_date=today, erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    assert "data-naver-dispatch-count=" not in _measurement(client)


# --------------------------------------------------------------------------- #
# 진행 조회 GET — 화면이 새로고침 없이 읽는 값
# --------------------------------------------------------------------------- #

def test_state_route_returns_the_same_values_as_the_strip(client, today):
    """진행 조회가 띠와 **같은 값**을 준다 — 술어를 한 벌 더 만들지 않았다는 계약."""
    _login(client)
    _stamp_ours(_naver_measured_today(today))
    response = client.get(STATE_PATH)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["state"] == "done"
    assert data["sent"] == 1 and data["count"] == 0 and data["day_total"] == 1
    assert data["show"] is True
    assert data["day_rows"][0]["state"] == "sent"


def test_state_route_is_read_only_and_reuses_build_preview():
    """진행 조회가 :func:`build_preview` 를 그대로 부른다(소스로 판정).

    진행률용 판정을 한 벌 더 두면 화면 큐와 워커가 갈렸던 그 결함을 재생산한다.
    """
    import inspect

    from foms.web.admin import naver_ingest

    source = inspect.getsource(naver_ingest.naver_ingest_bulk_dispatch_state)
    assert "build_preview" in source
    for forbidden in ("enqueue", "commit(", "log_access"):
        assert forbidden not in source, f"읽기 전용 라우트가 {forbidden} 을 부르면 안 된다"


def test_state_route_rejects_staff(client, today):
    """STAFF 는 진행 조회를 못 읽는다 — 이 값을 읽는 사람은 버튼을 가진 사람이다."""
    _login(client, role="STAFF")
    _naver_measured_today(today)
    assert client.get(STATE_PATH).status_code in (302, 403)


# --------------------------------------------------------------------------- #
# 버튼 배선 — 알림창 대신 띠 안에서 말한다
# --------------------------------------------------------------------------- #

def _partial_source() -> str:
    """공용 실행 버튼 파셜 원문.

    Returns:
        템플릿 원문.
    """
    path = _REPO_ROOT / "templates" / "partials" / "shared" / "naver_bulk_dispatch_button.html"
    return path.read_text(encoding="utf-8")


def test_button_reports_result_in_the_strip_not_in_an_alert():
    """성공 경로가 ``window.alert`` 로 끝나지 않는다.

    알림창은 닫는 순간 사라진다 — 사람이 새로고침해서 확인하게 만든 것이 1회차 결함의
    나머지 절반이었다. 결과는 띠 안에 남아야 한다.
    """
    source = _partial_source()
    assert "data-naver-bulk-dispatch-status" in source, "결과가 앉을 자리가 있어야 한다"
    assert "bulk-dispatch/state" in source, "결과를 다시 읽는 배선이 있어야 한다"
    # 알림창은 자리가 아예 없을 때의 마지막 수단으로만 남는다(자리가 있으면 안 쓴다).
    # 세는 자리는 **코드뿐**이다 — 머리말 주석이 옛 방식을 설명하느라 같은 이름을 적는다.
    code = source[source.index("<script>"):]
    assert code.count("window.alert") == 1
    assert "if (!box) { window.alert(text); return; }" in source


def test_button_keeps_the_irreversible_confirmation():
    """되돌릴 수 없다는 확인은 그대로다 — 진행 표시를 붙이며 조용히 빼지 않았다."""
    source = _partial_source()
    assert "window.confirm" in source
    assert "되돌릴 수 없습니다" in source


def test_v3_full_page_still_hides_the_button():
    """v3 풀페이지에서는 버튼을 안 그린다(그 셸은 페이지 스크립트를 통째로 안 싣는다).

    보이는데 안 눌리는 버튼은 되돌릴 수 없는 조작에서 가장 나쁜 실패 모양이다.
    """
    path = (_REPO_ROOT / "templates" / "measurement" / "partials"
            / "naver_dispatch_strip.html")
    source = path.read_text(encoding="utf-8")
    assert "shell_variant != 'v3'" in source
    assert "data-naver-bulk-dispatch-run" in source
    button_at = source.index("data-naver-bulk-dispatch-run")
    gate_at = source.index("shell_variant != 'v3'")
    assert gate_at < button_at, "게이트가 버튼보다 뒤에 있으면 v3 에서 버튼이 그려진다"
