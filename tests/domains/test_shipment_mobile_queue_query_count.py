"""Batch 3: shipment 모바일 v2 큐 행 빌더 N+1 회귀 가드.

build_mobile_queue_order_row의 주문별 단건 조회(첨부 카운트/그리드/미리보기/타임라인/
담당자 연락처 설정)를 batch context 1회 조회로 대체했다. 주문 수 N에 비례해 쿼리가
늘면(=per-row 회귀) 실패한다. 또한 batch 경로 결과가 per-row 경로와 동일함(동작 보존)을
고정한다.
"""
from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.erp_mobile_order_display import (
    build_mobile_queue_batch_context,
    build_mobile_queue_order_row,
)
from foms.services.shipment_dashboard_display import build_shipment_mobile_queue_rows
from models import Order, OrderAttachment, OrderEvent, User

_SEED_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="큐담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed_shipment_order(idx: int) -> int:
    order = Order(
        received_date="2026-06-01",
        customer_name=f"큐고객{idx}",
        phone=f"010-0000-{idx:04d}",
        address=f"서울시 큐구 {idx}",
        product="싱크대",
        status="IN_CONSTRUCTION",
        scheduled_date="2026-06-10",
        manager_name="큐담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {
                "customer": {"name": f"큐고객{idx}", "phone": f"010-0000-{idx:04d}"},
                "manager": {"name": "큐담당"},
            },
            "site": {"address_full": f"서울시 큐구 {idx}"},
            "schedule": {"construction": {"date": "2026-06-10"}},
            "items": [{"product_name": "싱크대", "spec_width": "1200"}],
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(2):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"f{idx}_{j}.jpg",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key=f"k/{idx}/{j}.jpg",
                created_at=_SEED_BASE + datetime.timedelta(minutes=j),
            )
        )
    db_session.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_CHANGED",
            payload={"to": "SHIPMENT"},
            created_at=_SEED_BASE + datetime.timedelta(minutes=5),
        )
    )
    db_session.commit()
    return order.id


def _count_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def _fresh(order_ids: list[int]) -> list[Order]:
    """expire_on_commit reload 잡음 제거: 측정 전 1회 쿼리로 행 전체 적재."""
    return (
        db_session.query(Order)
        .filter(Order.id.in_(order_ids))
        .order_by(Order.id.asc())
        .all()
    )


def test_shipment_mobile_queue_builder_no_n_plus_one(app):
    """주문 4건을 더 넣어도 모바일 큐 빌더 추가 쿼리는 상수(배치 1회 조회)."""
    with app.app_context():
        user = _make_user("queue_nplus1")
        small_ids = [_seed_shipment_order(i) for i in range(2)]
        big_ids = [_seed_shipment_order(i) for i in range(100, 106)]  # 6건

        small = _fresh(small_ids)
        big = _fresh(big_ids)

        _, q_small = _count_queries(
            lambda: build_shipment_mobile_queue_rows(
                db_session, small, user, mobile_v2_active=True
            )
        )
        _, q_big = _count_queries(
            lambda: build_shipment_mobile_queue_rows(
                db_session, big, user, mobile_v2_active=True
            )
        )

        extra = q_big - q_small
        # 배치면 주문 4건↑에도 추가 쿼리 ~0; per-row면 4×(카운트+그리드+미리보기+타임라인+설정)≈20.
        assert extra <= 3, (
            f"N+1 회귀 의심: 주문 4건 추가 시 추가 쿼리 {extra}건 "
            f"(small={q_small}, big={q_big}, 기대 ≤3)"
        )


def test_shipment_mobile_queue_batch_matches_per_row(app):
    """batch context 경로 결과 dict가 per-row 경로와 동일(동작 100% 보존)."""
    with app.app_context():
        user = _make_user("queue_equal")
        order_id = _seed_shipment_order(7)
        (order,) = _fresh([order_id])

        ctx = build_mobile_queue_batch_context(db_session, [order])
        row_batch = build_mobile_queue_order_row(db_session, order, user, batch_ctx=ctx)
        row_plain = build_mobile_queue_order_row(db_session, order, user)

        assert row_batch == row_plain
