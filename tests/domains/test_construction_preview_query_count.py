"""C2: 시공 대시보드 미리보기 첨부 N+1 회귀 가드.

enrich_construction_mobile_rows는 행마다 OrderAttachment를 조회(_collect_preview_items /
count_preview_attachments)했다. 이를 페이지 1회 in_ 배치 조회
(build_construction_preview_attachments_map)로 대체했다. 주문 수 N에 비례해 쿼리가 늘면
(=per-row 회귀) 실패한다. 또한 배치(preloaded) 경로 결과가 per-row 조회 경로와 동일함을
고정한다(동작 보존, 카테고리/정렬 동일).
"""
from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.construction_dashboard_display import (
    _collect_preview_items,
    build_construction_preview_attachments_map,
    build_construction_row_dtos,
    count_preview_attachments,
    enrich_construction_mobile_rows,
)
from models import Order, OrderAttachment, User

_SEED_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="시공담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed_construction_order(idx: int) -> int:
    order = Order(
        received_date="2026-06-01",
        customer_name=f"고객{idx}",
        phone=f"010-9000-{idx:04d}",
        address=f"서울시 프리뷰구 {idx}",
        product="싱크대",
        status="IN_CONSTRUCTION",
        manager_name="시공담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {
                "customer": {"name": f"고객{idx}", "phone": f"010-9000-{idx:04d}"},
                "manager": {"name": "시공담당"},
            },
            "site": {"address_full": f"서울시 프리뷰구 {idx}"},
            "schedule": {"construction": {"date": "2026-06-10"}},
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(3):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"m{idx}_{j}.jpg",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key=f"k/{idx}/{j}.jpg",
                created_at=_SEED_BASE + datetime.timedelta(minutes=j),
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


def _rows_for(order_ids: list[int]) -> list[dict]:
    orders = (
        db_session.query(Order)
        .filter(Order.id.in_(order_ids))
        .order_by(Order.id.asc())
        .all()
    )
    return build_construction_row_dtos(orders, {}, "")


def test_construction_preview_no_n_plus_one(app):
    """주문 4건을 더 넣어도 미리보기 첨부 조회는 상수(배치 1회)."""
    with app.app_context():
        _make_user("constr_preview_nplus1")
        small_ids = [_seed_construction_order(i) for i in range(2)]
        big_ids = [_seed_construction_order(i) for i in range(100, 106)]

        small_rows = _rows_for(small_ids)
        big_rows = _rows_for(big_ids)

        _, q_small = _count_queries(
            lambda: enrich_construction_mobile_rows(
                small_rows, db_session, mobile_v2_active=True
            )
        )
        _, q_big = _count_queries(
            lambda: enrich_construction_mobile_rows(
                big_rows, db_session, mobile_v2_active=True
            )
        )

        extra = q_big - q_small
        # per-row면 4건 추가 × 첨부조회 = 4↑. 배치면 1회뿐이라 ~0.
        assert extra <= 1, (
            f"미리보기 첨부 N+1 회귀 의심: 4건 추가 시 추가 쿼리 {extra}건 "
            f"(small={q_small}, big={q_big}, 기대 ≤1)"
        )


def test_construction_preview_batch_matches_per_row(app):
    """배치(preloaded) 미리보기 항목이 per-row 조회 경로와 동일."""
    with app.app_context():
        _make_user("constr_preview_equal")
        order_id = _seed_construction_order(500)
        rows = _rows_for([order_id])
        row = rows[0]

        preview_map = build_construction_preview_attachments_map(
            db_session, rows, drawing_only=False
        )
        items_batch = _collect_preview_items(
            row,
            db_session,
            drawing_only=False,
            preloaded_attachments=preview_map.get(order_id),
        )
        items_per_row = _collect_preview_items(row, db_session, drawing_only=False)

        assert items_batch == items_per_row
        assert items_batch  # 이미지 첨부가 실제로 미리보기로 잡혔는지 확인


def test_construction_preview_batch_matches_per_row_on_tie(app):
    """created_at 동률 첨부도 (created_at, id) 정렬로 배치==per-row(결정적)."""
    with app.app_context():
        _make_user("constr_preview_tie")
        order = Order(
            received_date="2026-06-01",
            customer_name="동률고객",
            phone="010-9000-7777",
            address="서울시 타이구 1",
            product="싱크대",
            status="IN_CONSTRUCTION",
            manager_name="시공담당",
            is_erp_order=True,
            structured_data={
                "workflow": {"stage": "CONSTRUCTION"},
                "parties": {"customer": {"name": "동률고객"}, "manager": {"name": "시공담당"}},
                "site": {"address_full": "서울시 타이구 1"},
                "schedule": {"construction": {"date": "2026-06-10"}},
            },
        )
        db_session.add(order)
        db_session.flush()
        tie = _SEED_BASE + datetime.timedelta(minutes=42)
        for j in range(5):  # 전부 동일 created_at
            db_session.add(
                OrderAttachment(
                    order_id=order.id,
                    filename=f"tie{j}.jpg",
                    file_type="image",
                    category="measurement",
                    file_size=10,
                    storage_key=f"tie/{order.id}/{j}.jpg",
                    created_at=tie,
                )
            )
        db_session.commit()

        rows = _rows_for([order.id])
        row = rows[0]
        preview_map = build_construction_preview_attachments_map(
            db_session, rows, drawing_only=False
        )
        items_batch = _collect_preview_items(
            row, db_session, drawing_only=False,
            preloaded_attachments=preview_map.get(order.id),
        )
        items_per_row = _collect_preview_items(row, db_session, drawing_only=False)
        assert items_batch == items_per_row
        assert len(items_batch) == 4  # _MAX_PREVIEW_COUNT


def test_construction_preview_drawing_only_count_matches(app):
    """drawing_only +N 카운트도 배치 길이 재사용이 per-row COUNT와 동일."""
    with app.app_context():
        _make_user("constr_preview_count")
        # drawing 카테고리 첨부 1건 추가(시공팀 도면 전용 경로)
        order_id = _seed_construction_order(600)
        order = db_session.get(Order, order_id)
        for j in range(2):
            db_session.add(
                OrderAttachment(
                    order_id=order.id,
                    filename=f"d{j}.jpg",
                    file_type="image",
                    category="drawing",
                    file_size=10,
                    storage_key=f"d/{order_id}/{j}.jpg",
                    created_at=_SEED_BASE + datetime.timedelta(minutes=10 + j),
                )
            )
        db_session.commit()

        rows = _rows_for([order_id])
        row = rows[0]
        preview_map = build_construction_preview_attachments_map(
            db_session, rows, drawing_only=True
        )
        count_batch = count_preview_attachments(
            row, db_session, drawing_only=True,
            preloaded_count=len(preview_map.get(order_id) or []),
        )
        count_per_row = count_preview_attachments(row, db_session, drawing_only=True)
        # 배치(길이 재사용) == per-row(.count()) 정확히 동일
        assert count_batch == count_per_row
        assert count_batch >= 2  # drawing 첨부 2건 반영
