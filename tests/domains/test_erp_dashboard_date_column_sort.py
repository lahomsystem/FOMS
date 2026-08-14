"""ERP 대시보드 실측일/시공일 컬럼 헤더 정렬 계약 테스트.

정렬은 서버(SQL order_by)에서 이뤄져야 페이지 경계를 넘어 전체가 정렬된다.
헤더 링크는 현재 필터를 유지하고 3단 토글(기본 → 오름차순 → 내림차순 → 기본)로 동작한다.
"""

from db import db_session
from models import Order


def _add_erp_order(customer_name: str, *, measure: str | None, construction: str | None) -> Order:
    """정렬 검증용 ERP 주문 1건을 만든다.

    Args:
        customer_name: 본문에서 순서를 확인하기 위한 고유 고객명.
        measure: 실측일 싱크 컬럼 값(None이면 미정).
        construction: 시공일 싱크 컬럼 값(None이면 미정).

    Returns:
        커밋된 Order 인스턴스.
    """
    schedule: dict = {}
    if measure:
        schedule["measurement"] = {"date": measure}
    if construction:
        schedule["construction"] = {"date": construction}
    order = Order(
        received_date="2026-05-12",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 정렬로 1",
        product="슬라이딩",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        erp_measurement_date=measure,
        erp_construction_date=construction,
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {"customer": {"name": customer_name}},
            "site": {"address_full": "서울시 테스트구 정렬로 1"},
            "schedule": schedule,
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _order_of(body: str, *names: str) -> list[str]:
    """본문에 등장한 순서대로 이름 목록을 돌려준다(미등장은 제외)."""
    found = [(body.index(name), name) for name in names if name in body]
    return [name for _, name in sorted(found)]


def _seed_sort_fixture() -> None:
    _add_erp_order("SORTA middle", measure="2026-06-10", construction="2026-07-10")
    _add_erp_order("SORTB earliest", measure="2026-06-01", construction="2026-07-01")
    _add_erp_order("SORTC latest", measure="2026-06-20", construction="2026-07-20")
    _add_erp_order("SORTD undated", measure=None, construction=None)


def test_measure_date_ascending_puts_earliest_first_and_undated_last(login):
    _seed_sort_fixture()

    body = login.get("/erp/dashboard?sort=measure_date&dir=asc").get_data(as_text=True)

    assert _order_of(body, "SORTA middle", "SORTB earliest", "SORTC latest", "SORTD undated") == [
        "SORTB earliest",
        "SORTA middle",
        "SORTC latest",
        "SORTD undated",
    ]


def test_measure_date_descending_reverses_dated_rows_only(login):
    _seed_sort_fixture()

    body = login.get("/erp/dashboard?sort=measure_date&dir=desc").get_data(as_text=True)

    assert _order_of(body, "SORTA middle", "SORTB earliest", "SORTC latest", "SORTD undated") == [
        "SORTC latest",
        "SORTA middle",
        "SORTB earliest",
        "SORTD undated",
    ]


def test_construction_date_sort_uses_construction_column(login):
    _seed_sort_fixture()

    body = login.get("/erp/dashboard?sort=construction_date&dir=desc").get_data(as_text=True)

    assert _order_of(body, "SORTA middle", "SORTB earliest", "SORTC latest") == [
        "SORTC latest",
        "SORTA middle",
        "SORTB earliest",
    ]


def test_invalid_direction_falls_back_to_ascending(login):
    _seed_sort_fixture()

    body = login.get("/erp/dashboard?sort=measure_date&dir=sideways").get_data(as_text=True)

    assert _order_of(body, "SORTB earliest", "SORTC latest") == ["SORTB earliest", "SORTC latest"]


def test_header_link_toggles_ascending_then_descending_then_off(login):
    _add_erp_order("SORTA middle", measure="2026-06-10", construction="2026-07-10")

    default_body = login.get("/erp/dashboard").get_data(as_text=True)
    assert "sort=measure_date&amp;dir=asc" in default_body
    assert "sort=construction_date&amp;dir=asc" in default_body

    asc_body = login.get("/erp/dashboard?sort=measure_date&dir=asc").get_data(as_text=True)
    assert "sort=measure_date&amp;dir=desc" in asc_body

    desc_body = login.get("/erp/dashboard?sort=measure_date&dir=desc").get_data(as_text=True)
    assert "sort=measure_date" not in desc_body.split('class="erp-col-sort is-active"')[1][:400]


def test_header_sort_link_preserves_active_filters(login):
    _add_erp_order("SORTA middle", measure="2026-06-10", construction="2026-07-10")

    body = login.get("/erp/dashboard?stage=MEASURE&team=MEASURE&mine=1").get_data(as_text=True)

    sort_links = [seg for seg in body.split('class="erp-col-sort') if "sort=measure_date" in seg[:600]]
    assert sort_links, "실측일 정렬 링크가 렌더되지 않았다"
    link = sort_links[0]
    assert "stage=MEASURE" in link
    assert "team=MEASURE" in link
    assert "mine=1" in link
