"""Wave 2(W2-3): 실측 모바일 v2 큐 N+1 회귀 가드.

foms.web.measurement.dashboard 의 모바일 큐 루프가 batch_ctx 없이
build_mobile_queue_order_row 를 행마다 호출해 행당 ~5쿼리(첨부 카운트/미리보기/
타임라인/담당자)를 발생시켰다. 출고 대시보드와 동일하게 build_mobile_queue_batch_context
1회 조회 + batch_ctx 전달로 대체했다.

이 테스트는 라우트가 실제로 쓰는 빌더 경로(batch context + per-row(batch_ctx=))를
그대로 재현해, 주문 수 N에 비례해 쿼리가 늘면(=per-row 회귀) 실패한다. 또한 batch
경로 결과가 per-row 경로와 동일함(동작 보존)을 고정한다.
"""
from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.erp_display import normalize_manager_name
from foms.services.erp_mobile_order_display import (
    build_mobile_queue_batch_context,
    build_mobile_queue_order_row,
)
from models import Order, OrderAttachment, OrderEvent, User

_SEED_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="MEASURE",
        name="실측담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed_measurement_order(idx: int) -> int:
    order = Order(
        received_date="2026-06-01",
        customer_name=f"실측고객{idx}",
        phone=f"010-1000-{idx:04d}",
        address=f"서울시 실측구 {idx}",
        product="붙박이장",
        status="MEASURED",
        measurement_date="2026-06-05",
        manager_name="실측담당",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {
                "customer": {"name": f"실측고객{idx}", "phone": f"010-1000-{idx:04d}"},
                "manager": {"name": "실측담당"},
            },
            "site": {"address_full": f"서울시 실측구 {idx}"},
            "schedule": {"measurement": {"date": "2026-06-05"}},
            "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(2):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"m{idx}_{j}.jpg",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key=f"m/{idx}/{j}.jpg",
                created_at=_SEED_BASE + datetime.timedelta(minutes=j),
            )
        )
    db_session.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_CHANGED",
            payload={"to": "MEASURE"},
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


def _build_measurement_queue_rows(rows: list[Order], user) -> list[dict]:
    """라우트(foms.web.measurement.dashboard)의 모바일 큐 조립 경로를 재현.

    batch context 1회 조회 후 per-row(batch_ctx=) + 담당자명 정규화.
    """
    batch_ctx = build_mobile_queue_batch_context(db_session, rows)
    out: list[dict] = []
    for _o in rows:
        _row = build_mobile_queue_order_row(db_session, _o, user, batch_ctx=batch_ctx)
        _mgr = normalize_manager_name(
            ((_o.structured_data or {}).get("parties") or {}).get("manager"),
            getattr(_o, "manager_name", None),
        )
        if _mgr:
            _row["manager_name"] = _mgr
        out.append(_row)
    return out


def test_measurement_mobile_queue_builder_no_n_plus_one(app):
    """주문 6건을 더 넣어도 모바일 큐 빌더 추가 쿼리는 상수(배치 1회 조회)."""
    with app.app_context():
        user = _make_user("measure_queue_nplus1")
        small_ids = [_seed_measurement_order(i) for i in range(2)]
        big_ids = [_seed_measurement_order(i) for i in range(200, 206)]  # 6건

        small = _fresh(small_ids)
        big = _fresh(big_ids)

        _, q_small = _count_queries(lambda: _build_measurement_queue_rows(small, user))
        _, q_big = _count_queries(lambda: _build_measurement_queue_rows(big, user))

        extra = q_big - q_small
        # 배치면 주문 4건↑에도 추가 쿼리 ~0; per-row면 4×(카운트+그리드+미리보기+타임라인)≈16+.
        assert extra <= 3, (
            f"N+1 회귀 의심: 주문 4건 추가 시 추가 쿼리 {extra}건 "
            f"(small={q_small}, big={q_big}, 기대 ≤3)"
        )


def test_measurement_mobile_queue_batch_matches_per_row(app):
    """batch context 경로 결과 dict가 per-row 경로와 동일(동작 100% 보존)."""
    with app.app_context():
        user = _make_user("measure_queue_equal")
        order_id = _seed_measurement_order(7)
        (order,) = _fresh([order_id])

        ctx = build_mobile_queue_batch_context(db_session, [order])
        row_batch = build_mobile_queue_order_row(db_session, order, user, batch_ctx=ctx)
        row_plain = build_mobile_queue_order_row(db_session, order, user)

        assert row_batch == row_plain
