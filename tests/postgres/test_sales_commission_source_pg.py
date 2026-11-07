"""영업 수수료 얇은 문서 — SQL 투영 == 파이썬 정본 (FCOMM-01 T5 · PGTEST-00 lane).

수수료 읽기 모델(:mod:`foms.services.sales_commission.read_model`)은 정산과 같은 얇은 문서 장치
(:func:`settlement_source.fetch_settlement_rows`)에 자기 나무 :data:`COMMISSION_SD_SPEC` 를 넘긴다.
SQLite 레인은 투영을 파이썬 정본으로 하므로, 진짜 SQL 이 같은 문서를 내는지는 여기서만 잴 수 있다.

1. 정산 표본 모양마다 SQL 투영 == 파이썬 정본(``json.dumps`` 문자열까지).
2. 수수료가 읽는 칸(품목 취소 표시 · 발주사 · 담당자 · 실측일 · 시공일 · 차감)이 투영 문서에 살아 있다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from foms.services import settlement_source as ss
from foms.services.sales_commission import calc
from foms.services.sales_commission.read_model import COMMISSION_SD_SPEC
from models import Order
from tests.domains.settlement_source_helpers import seed_shapes


@pytest.fixture
def sql_projection(pg_session):
    """SQL 투영이 실제로 걸리는 서버인지 확인한다(PostgreSQL 16+)."""
    if not ss.supports_sql_projection(pg_session):
        pytest.skip("PostgreSQL 16 미만 — JSON_OBJECT ABSENT ON NULL 이 없어 파이썬 투영으로 떨어진다")
    return pg_session


def _seed_commission_order(session) -> int:
    """수수료가 읽는 칸을 모두 가진 주문 한 건(가짜 값)."""
    sd = {
        "items": [
            {"product_name": "붙박이장", "price": 2_000_000},
            {"product_name": "화장대", "price": 500_000, "cancel": {"cancelled": True}},
        ],
        "payment": {"discount": 100_000},
        "parties": {
            "manager": {"name": "가짜프리", "names": ["가짜프리", "다른사람"]},
            "customer": {"name": "가짜손님"},
            "orderer": {"name": "하우드"},
        },
        "schedule": {"construction": {"date": "2026-11-20"}, "measurement": {"date": "2026-11-03"}},
        "settlement": {"deductions": [
            {"id": "DED-1", "department": "SALES", "amount": -50_000, "charge_to_user_id": 7},
            {"id": "DED-2", "department": "SALES", "amount": -9_000, "charge_to_user_id": 7,
             "voided_at": "2026-11-21T10:00:00+09:00"},
        ]},
        "quests": {"big": "읽지 않는 칸"},
    }
    order = Order(received_date="2026-11-01", customer_name="FCOMM-PG-1", phone="010-0000-0000",
                  address="서울", product="붙박이장", status="CS", is_erp_order=True,
                  erp_stage_code="CS", structured_data=sd)
    session.add(order)
    session.flush()
    return order.id


def test_commission_projection_equals_the_python_reference(sql_projection):
    """정산 표본 모양 + 수수료 주문마다 SQL 투영 == 파이썬 정본(키 순서까지)."""
    session = sql_projection
    ids = seed_shapes(session) + [_seed_commission_order(session)]
    full = dict(session.execute(select(Order.id, Order.structured_data).where(Order.id.in_(ids))).all())
    rows = ss.fetch_settlement_rows(session, (Order.id, Order.customer_name), (Order.id.in_(ids),),
                                    COMMISSION_SD_SPEC)
    assert len(rows) == len(ids)
    for row in rows:
        expected = ss.project_settlement_sd(full[row.id], COMMISSION_SD_SPEC)
        assert row.structured_data == expected, row.customer_name
        assert (json.dumps(row.structured_data, ensure_ascii=False)
                == json.dumps(expected, ensure_ascii=False)), f"{row.customer_name}: 키 순서"


def test_commission_fields_survive_the_projection(sql_projection):
    """수수료 판정이 읽는 칸이 투영 문서에서도 같은 답을 낸다(통째 원본과 비교)."""
    session = sql_projection
    order_id = _seed_commission_order(session)
    full = session.execute(select(Order.structured_data).where(Order.id == order_id)).scalar_one()
    (row,) = ss.fetch_settlement_rows(session, (Order.id,), (Order.id == order_id,), COMMISSION_SD_SPEC)
    thin = row.structured_data

    assert "quests" not in thin
    assert calc.commission_shipping_price(thin) == calc.commission_shipping_price(full) == 1_900_000
    assert calc.sales_deduction_total(thin, 7) == calc.sales_deduction_total(full, 7) == 50_000
    assert calc.extract_order_fields(thin) == calc.extract_order_fields(full)
