"""AS 대시보드 날짜 3열(접수일/방문일/완료일) 헤더 정렬 계약 테스트.

기본은 기존과 같은 AS 접수일 내림차순이고, 방문일/완료일 헤더를 누르면 그 열 기준으로
갈아탄다. 방문일은 컬럼이 없어 schedule.as_visit.date(JSONB)가 정렬 SSOT다.
"""

from db import db_session
from models import Order


def _add_as_order(
    customer_name: str,
    *,
    received: str | None = None,
    visit: str | None = None,
    completed: str | None = None,
    status: str = "AS_RECEIVED",
) -> Order:
    """AS 상태 주문 1건을 만든다.

    Args:
        customer_name: 본문 순서 확인용 고유 고객명.
        received: AS 접수일. visit: AS 방문일. completed: AS 완료일.
        status: 주문 상태(완료 탭 검증 시 AS_COMPLETED).

    Returns:
        커밋된 Order 인스턴스.
    """
    structured: dict = {"parties": {"customer": {"name": customer_name}}}
    if visit:
        structured["schedule"] = {"as_visit": {"date": visit}}
    order = Order(
        received_date="2026-05-12",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 AS로 1",
        product="슬라이딩",
        status=status,
        is_erp_order=True,
        as_received_date=received,
        as_completed_date=completed,
        structured_data=structured,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _order_of(body: str, *names: str) -> list[str]:
    """본문에 등장한 순서대로 이름 목록을 돌려준다(미등장은 제외)."""
    found = [(body.index(name), name) for name in names if name in body]
    return [name for _, name in sorted(found)]


def _seed() -> None:
    _add_as_order("ASMID case", received="2026-06-10", visit="2026-07-10")
    _add_as_order("ASEARLY case", received="2026-06-01", visit="2026-07-20")
    _add_as_order("ASLATE case", received="2026-06-20", visit="2026-07-01")


def test_default_sort_is_received_date_descending(login):
    _seed()

    body = login.get("/erp/as").get_data(as_text=True)

    assert _order_of(body, "ASMID case", "ASEARLY case", "ASLATE case") == [
        "ASLATE case",
        "ASMID case",
        "ASEARLY case",
    ]


def test_visit_date_ascending_uses_structured_schedule(login):
    _seed()

    body = login.get("/erp/as?sort_key=visit&sort_dir=asc").get_data(as_text=True)

    assert _order_of(body, "ASMID case", "ASEARLY case", "ASLATE case") == [
        "ASLATE case",
        "ASMID case",
        "ASEARLY case",
    ]


def test_visit_date_descending_reverses_order(login):
    _seed()

    body = login.get("/erp/as?sort_key=visit&sort_dir=desc").get_data(as_text=True)

    assert _order_of(body, "ASMID case", "ASEARLY case", "ASLATE case") == [
        "ASEARLY case",
        "ASMID case",
        "ASLATE case",
    ]


def test_completed_date_sort_on_completed_tab(login):
    _add_as_order("ASDONEA case", received="2026-06-01", completed="2026-08-05", status="AS_COMPLETED")
    _add_as_order("ASDONEB case", received="2026-06-02", completed="2026-08-01", status="AS_COMPLETED")

    body = login.get("/erp/as?tab=completed&sort_key=completed&sort_dir=asc").get_data(as_text=True)

    assert _order_of(body, "ASDONEA case", "ASDONEB case") == ["ASDONEB case", "ASDONEA case"]


def test_unknown_sort_key_falls_back_to_received(login):
    _seed()

    body = login.get("/erp/as?sort_key=customer&sort_dir=desc").get_data(as_text=True)

    assert _order_of(body, "ASMID case", "ASEARLY case", "ASLATE case") == [
        "ASLATE case",
        "ASMID case",
        "ASEARLY case",
    ]


def test_headers_expose_sort_links_for_all_three_date_columns(login):
    _add_as_order("ASMID case", received="2026-06-10", visit="2026-07-10")

    body = login.get("/erp/as").get_data(as_text=True)

    assert "sort_key=received" in body
    assert "sort_key=visit" in body
    assert "sort_key=completed" in body


def test_blank_dates_go_last_even_when_ascending(login):
    """방문일 미정 행은 오름차순에서도 뒤로 — 1페이지가 빈 행으로 덮이지 않게."""
    _add_as_order("ASNOVISIT case", received="2026-06-05")
    _add_as_order("ASHASVISIT case", received="2026-06-06", visit="2026-07-09")

    body = login.get("/erp/as?sort_key=visit&sort_dir=asc").get_data(as_text=True)

    assert _order_of(body, "ASNOVISIT case", "ASHASVISIT case") == [
        "ASHASVISIT case",
        "ASNOVISIT case",
    ]


def test_pagination_links_keep_the_active_sort_key(login):
    """2페이지로 넘어가도 고른 정렬이 풀리지 않는다."""
    for i in range(120):
        _add_as_order(f"ASPAGE{i:03d} case", received="2026-06-05", visit=f"2026-07-{(i % 28) + 1:02d}")

    body = login.get("/erp/as?sort_key=visit&sort_dir=asc").get_data(as_text=True)

    assert "page=2" in body, "페이지네이션이 렌더되지 않아 계약을 검증할 수 없다"
    page_links = [seg for seg in body.split('class="page-link"') if "page=2" in seg[:400]]
    assert page_links, "2페이지 링크를 찾지 못했다"
    assert "sort_key=visit" in page_links[0]
