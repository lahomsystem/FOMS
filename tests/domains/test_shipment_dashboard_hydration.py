"""Perf Fix2: 출고 대시보드 hot-path structured_data 배치 하이드레이션 N+1 가드.

panel_orders는 structured_data(64KB JSONB)를 load_only에서 제외해 light 로드하고,
실제 필요한 부분집합(선택 rows·집계 miss·mine_only·AS 파생)만 _hydrate_structured_data로
`id IN (...)` 단일 배치 쿼리로 주입한다. 주문 수 N에 비례해 structured_data를 SELECT하는
쿼리가 늘면(=per-order 회귀) 실패한다. 또한 헬퍼가 set_committed_value로 clean 상태를
주입해 세션 dirty를 만들지 않음(읽기 전용 계약 보존)을 고정한다.
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import load_only, selectinload
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.erp_display import get_today_kst
from foms.web.shipment.dashboard import _hydrate_structured_data
from models import Order, OrderScheduleDate, User


def _login_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="출고 하이드레이션 Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_construction_order(idx: int, cons_date: str) -> int:
    order = Order(
        received_date=cons_date,
        customer_name=f"하이드고객{idx}",
        phone=f"010-7000-{idx:04d}",
        address=f"서울시 하이드구 {idx}",
        product="싱크대",
        status="IN_CONSTRUCTION",
        scheduled_date=cons_date,
        manager_name="하이드담당",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "SHIPMENT"},
            "parties": {
                "customer": {"name": f"하이드고객{idx}", "phone": f"010-7000-{idx:04d}"},
                "manager": {"name": "하이드담당"},
            },
            "schedule": {"construction": {"date": cons_date}},
            "items": [{"product_name": "싱크대", "spec_width": "1200"}],
            "shipment": {"construction_workers": ["시공1"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="construction",
            date=cons_date,
            source="hydration_test",
        )
    )
    db_session.commit()
    return order.id


def _count_structured_data_selects(fn):
    """structured_data 컬럼을 SELECT하는 쿼리 수를 센다(=JSONB 로드 배치 수)."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        if "structured_data" in statement and statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_hydrate_structured_data_single_batch_and_not_dirty(app):
    """미로드 주문 N건을 배치 1쿼리로 채우고, set_committed_value라 dirty가 아니다."""
    with app.app_context():
        today = get_today_kst().strftime("%Y-%m-%d")
        ids = [_seed_construction_order(500 + i, today) for i in range(5)]

        # structured_data를 deferred로 두고 다시 로드(패널 load_only와 동일 패턴).
        orders = (
            db_session.query(Order)
            .filter(Order.id.in_(ids))
            .options(load_only(Order.id, Order.status, Order.is_erp_order))
            .populate_existing()
            .all()
        )
        from sqlalchemy import inspect as sa_inspect
        for o in orders:
            assert "structured_data" in sa_inspect(o).unloaded

        _, n = _count_structured_data_selects(
            lambda: _hydrate_structured_data(db_session, orders)
        )
        assert n == 1, f"배치 하이드레이션은 1쿼리여야 함(실제 {n})"

        for o in orders:
            assert isinstance(o.structured_data, dict)
            assert o.structured_data["shipment"]["construction_workers"] == ["시공1"]
            # set_committed_value 주입 → 세션 dirty에 없어야 함(읽기 전용 계약).
            assert o not in db_session.dirty


def test_shipment_dashboard_structured_data_selects_constant(client, monkeypatch):
    """주문을 3건→9건으로 늘려도 structured_data SELECT 쿼리 수가 상수(배치)여야 함."""
    _login_admin(client, "hydration_route_admin")
    today = get_today_kst().strftime("%Y-%m-%d")

    small_ids = [_seed_construction_order(600 + i, today) for i in range(3)]
    _, q_small = _count_structured_data_selects(
        lambda: client.get(f"/erp/shipment?date={today}")
    )

    big_ids = [_seed_construction_order(700 + i, today) for i in range(9)]
    _, q_big = _count_structured_data_selects(
        lambda: client.get(f"/erp/shipment?date={today}")
    )

    # 배치면 주문 6건 추가에도 structured_data SELECT 증가는 ~0; per-order면 N에 비례해 증가.
    extra = q_big - q_small
    assert extra <= 1, (
        f"N+1 회귀 의심: 주문 6건 추가 시 structured_data SELECT {extra}건 증가 "
        f"(small={q_small}, big={q_big}, 기대 ≤1)"
    )
