"""생산 대시보드 실측일/시공일 컬럼 헤더 정렬 계약 테스트.

기본(sort 미지정)은 기존 '시공일 빠른 순'을 유지하고, 헤더를 눌렀을 때만 그 컬럼·방향으로
갈아탄다. ERP 작업 큐와 같은 sort/dir 규약을 쓴다.
"""

from db import db_session
from models import Order


def _add_production_order(customer_name: str, *, measure: str | None, construction: str | None) -> Order:
    """생산 단계 ERP 주문 1건을 만든다.

    Args:
        customer_name: 본문에서 순서를 확인하기 위한 고유 고객명.
        measure: 실측일 싱크 컬럼 값(None이면 미정).
        construction: 시공일 싱크 컬럼 값(None이면 미정).

    Returns:
        커밋된 Order 인스턴스.
    """
    order = Order(
        received_date="2026-05-12",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 생산로 1",
        product="슬라이딩",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="PRODUCTION",
        erp_measurement_date=measure,
        erp_construction_date=construction,
        structured_data={
            "workflow": {"stage": "PRODUCTION"},
            "parties": {"customer": {"name": customer_name}},
            "site": {"address_full": "서울시 테스트구 생산로 1"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _order_of(body: str, *names: str) -> list[str]:
    """본문에 등장한 순서대로 이름 목록을 돌려준다(미등장은 제외)."""
    found = [(body.index(name), name) for name in names if name in body]
    return [name for _, name in sorted(found)]


def _seed() -> None:
    _add_production_order("PRODA middle", measure="2026-06-10", construction="2026-07-10")
    _add_production_order("PRODB early", measure="2026-06-01", construction="2026-07-01")
    _add_production_order("PRODC late", measure="2026-06-20", construction="2026-07-20")


def test_default_keeps_construction_date_ascending(login):
    _seed()

    body = login.get("/erp/production/dashboard").get_data(as_text=True)

    assert _order_of(body, "PRODA middle", "PRODB early", "PRODC late") == [
        "PRODB early",
        "PRODA middle",
        "PRODC late",
    ]


def test_measure_date_descending_header_sort(login):
    _seed()

    body = login.get("/erp/production/dashboard?sort=measure_date&dir=desc").get_data(as_text=True)

    assert _order_of(body, "PRODA middle", "PRODB early", "PRODC late") == [
        "PRODC late",
        "PRODA middle",
        "PRODB early",
    ]


def test_construction_date_descending_header_sort(login):
    _seed()

    body = login.get("/erp/production/dashboard?sort=construction_date&dir=desc").get_data(as_text=True)

    assert _order_of(body, "PRODA middle", "PRODB early", "PRODC late") == [
        "PRODC late",
        "PRODA middle",
        "PRODB early",
    ]


def test_unknown_sort_key_falls_back_to_default_order(login):
    _seed()

    body = login.get("/erp/production/dashboard?sort=customer&dir=desc").get_data(as_text=True)

    assert _order_of(body, "PRODA middle", "PRODB early", "PRODC late") == [
        "PRODB early",
        "PRODA middle",
        "PRODC late",
    ]


def test_header_links_point_at_production_route_and_toggle(login):
    _add_production_order("PRODA middle", measure="2026-06-10", construction="2026-07-10")

    body = login.get("/erp/production/dashboard").get_data(as_text=True)
    assert "/erp/production/dashboard?sort=measure_date&amp;dir=asc" in body
    assert "/erp/production/dashboard?sort=construction_date&amp;dir=asc" in body

    asc = login.get("/erp/production/dashboard?sort=measure_date&dir=asc").get_data(as_text=True)
    assert "/erp/production/dashboard?sort=measure_date&amp;dir=desc" in asc
