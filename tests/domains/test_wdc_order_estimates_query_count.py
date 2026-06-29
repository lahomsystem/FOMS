"""GET /api/wdcalculator/order-estimates/<order_id> N+1 회귀 가드.

Batch 1: match별 단건 조회(1+N)를 estimate_id 배치 조회(in_, 2)로 교체.
매칭 수 N과 무관하게 wdcalculator 엔진 SELECT가 일정(=2)임을 고정한다.
역행(per-row .first())이 재유입되면 쿼리 수가 1+N으로 늘어 실패한다.
"""
from sqlalchemy import event

from db import db_session
from models import Order
from wdcalculator_db import wd_calculator_session, wd_calculator_engine
from wdcalculator_models import Estimate, EstimateOrderMatch


def _create_order() -> Order:
    order = Order(
        received_date="2026-06-26",
        customer_name="쿼리카운트 고객",
        phone="010-9999-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _create_matched_estimates(order_id: int, n: int) -> list[int]:
    ids: list[int] = []
    for i in range(n):
        est = Estimate(customer_name=f"견적{i}", estimate_data={"totalPrice": 1000 + i})
        wd_calculator_session.add(est)
        wd_calculator_session.flush()
        wd_calculator_session.add(
            EstimateOrderMatch(estimate_id=est.id, order_id=order_id)
        )
        ids.append(est.id)
    wd_calculator_session.commit()
    return ids


def _count_wd_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(wd_calculator_engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(wd_calculator_engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_order_estimates_no_n_plus_one(wdcalculator_settings_env, login):
    """매칭 4건이어도 wd 엔진 SELECT는 2건(matches + estimates in_)으로 고정."""
    client = login
    order = _create_order()
    estimate_ids = _create_matched_estimates(order.id, 4)

    resp, wd_queries = _count_wd_queries(
        lambda: client.get(f"/api/wdcalculator/order-estimates/{order.id}")
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    # 매칭 순서·전체 건수 보존
    assert payload["count"] == 4
    assert [e["id"] for e in payload["estimates"]] == estimate_ids
    # 핵심: 쿼리 수가 N에 비례하지 않음. 배치 조회면 2, per-row면 1+4=5.
    assert wd_queries <= 2, f"N+1 회귀 의심: wd SELECT {wd_queries}건(기대 ≤2)"


def test_order_estimates_empty_matches(wdcalculator_settings_env, login):
    """매칭 0건이면 estimates 빈 배열, in_([]) 쿼리 생략."""
    client = login
    order = _create_order()

    resp = client.get(f"/api/wdcalculator/order-estimates/{order.id}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["count"] == 0
    assert payload["estimates"] == []
