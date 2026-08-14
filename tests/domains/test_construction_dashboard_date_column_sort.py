"""시공 대시보드 실측일/시공일 컬럼 헤더 정렬 계약 테스트.

기본(sort 미지정)은 기존 접수 최신순을 유지하고, 헤더를 눌렀을 때만 그 컬럼·방향으로
갈아탄다. ERP 작업 큐와 같은 sort/dir 규약을 쓴다.
"""

import datetime

from db import db_session
from models import Order


def _add_construction_order(
    customer_name: str,
    *,
    measure: str | None,
    construction: str | None,
    created_at: datetime.datetime | None = None,
) -> Order:
    """시공 단계 ERP 주문 1건을 만든다.

    Args:
        customer_name: 본문 순서 확인용 고유 고객명.
        measure: 실측일 싱크 컬럼 값(None이면 미정).
        construction: 시공일 싱크 컬럼 값(None이면 미정).
        created_at: 접수 순서 고정용 생성시각(같은 트랜잭션의 동시각 타이 방지).

    Returns:
        커밋된 Order 인스턴스.
    """
    order = Order(
        received_date="2026-05-12",
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울시 테스트구 시공로 1",
        product="슬라이딩",
        status="RECEIVED",
        is_erp_order=True,
        erp_stage_code="CONSTRUCTION",
        erp_measurement_date=measure,
        erp_construction_date=construction,
        created_at=created_at,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": customer_name}},
            "site": {"address_full": "서울시 테스트구 시공로 1"},
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
    """접수 순서(created_at)를 시공일 순서와 다르게 심어 두 정렬을 구분한다."""
    base = datetime.datetime(2026, 5, 12, 9, 0, 0)
    _add_construction_order(
        "CONA middle", measure="2026-06-10", construction="2026-07-10",
        created_at=base + datetime.timedelta(minutes=2),
    )
    _add_construction_order(
        "CONB early", measure="2026-06-01", construction="2026-07-01",
        created_at=base + datetime.timedelta(minutes=1),
    )
    _add_construction_order(
        "CONC late", measure="2026-06-20", construction="2026-07-20",
        created_at=base,
    )


_NAMES = ("CONA middle", "CONB early", "CONC late")


def test_default_keeps_newest_received_first(login):
    _seed()

    body = login.get("/erp/construction/dashboard").get_data(as_text=True)

    assert _order_of(body, *_NAMES) == ["CONA middle", "CONB early", "CONC late"]


def test_construction_date_ascending_header_sort(login):
    _seed()

    body = login.get(
        "/erp/construction/dashboard?sort=construction_date&dir=asc"
    ).get_data(as_text=True)

    assert _order_of(body, *_NAMES) == ["CONB early", "CONA middle", "CONC late"]


def test_measure_date_descending_header_sort(login):
    _seed()

    body = login.get("/erp/construction/dashboard?sort=measure_date&dir=desc").get_data(as_text=True)

    assert _order_of(body, *_NAMES) == ["CONC late", "CONA middle", "CONB early"]


def test_unknown_sort_key_falls_back_to_default_order(login):
    _seed()

    body = login.get("/erp/construction/dashboard?sort=customer&dir=asc").get_data(as_text=True)

    assert _order_of(body, *_NAMES) == ["CONA middle", "CONB early", "CONC late"]


def test_header_links_point_at_construction_route(login):
    _add_construction_order("CONA middle", measure="2026-06-10", construction="2026-07-10")

    body = login.get("/erp/construction/dashboard").get_data(as_text=True)

    assert "/erp/construction/dashboard?sort=measure_date&amp;dir=asc" in body
    assert "/erp/construction/dashboard?sort=construction_date&amp;dir=asc" in body
