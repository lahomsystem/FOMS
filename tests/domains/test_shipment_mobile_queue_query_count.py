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


# ── 라우트 단위: 폰(모바일 큐) · 태블릿 가로 출고 탭 쿼리 수가 줄 수에 따라 늘지 않는다 ──
# 2026-11-16 실측: 폰 98문 · 태블릿 37문. 패널 load_only 가 모바일 큐 빌더 · 표 칸이 읽는 칼럼
# (lat · lng · measurement_completed · received_date · partner_org_id · is_self_measurement · product)을
# 빼 행마다 칼럼 하나씩 지연 로드했다. 위 빌더 시험은 _fresh() 로 전체 칼럼을 실어 이 구멍을 못 봤다.

import re as _re

import pytest as _pytest

from foms.services.common import dashboard_cache as _dc
from foms.services.datetime_kst import get_today_kst as _today_kst
from models import OrderScheduleDate as _OSD

_ROUTE = "/erp/shipment"
_SHELL = {"X-FOMS-ERP-SHELL": "1"}
_LAZY_COLUMN = _re.compile(r"SELECT orders\.(\w+) AS \w+\s+FROM orders\s+WHERE orders\.id = ")


def _route_order(idx: int, day: str, *, items: bool = True) -> None:
    sd = {
        "workflow": {"stage": "SHIPMENT"},
        "parties": {"customer": {"name": f"가짜출고{idx}"}, "manager": {"name": "가짜영업"}},
        "site": {"address_full": "가짜시 1"},
        "schedule": {"construction": {"date": day}},
        "shipment": {"construction_workers": ["가짜기사"]},
    }
    if items:
        sd["items"] = [{"product_name": "가짜장", "spec_width": "1200"}]
    order = Order(received_date=day, customer_name=f"가짜출고{idx}", phone="010-0000-0000", address="가짜시 1",
                  product="가짜장", status="SHIPMENT", manager_name="가짜영업", is_erp_order=True,
                  structured_data=sd, erp_stage_code="SHIPMENT", scheduled_date=day)
    db_session.add(order)
    db_session.flush()
    db_session.add(_OSD(order_id=order.id, kind="construction", date=day, source="beta_schedule"))
    db_session.commit()


def _route_statements(client, url: str) -> list[str]:
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    _dc.reset_dashboard_cache_runtime_for_tests()
    event.listen(engine, "before_cursor_execute", _before)
    try:
        assert client.get(url, headers=_SHELL).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return seen


@_pytest.mark.parametrize("device", ["phone", "tablet"])
def test_shipment_route_query_count_flat_and_no_deferred_column_loads(client, monkeypatch, device) -> None:
    """폰 · 태블릿 가로 출고 탭: 줄 3 → 9 에도 쿼리 수 그대로(≤2), 행 칼럼 지연 로드 0."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _make_user(f"ship_route_{device}")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    if device == "tablet":
        client.set_cookie("foms_ptr", "coarse", domain="localhost")
        client.set_cookie("foms_vw", "wide", domain="localhost")
    day = _today_kst().isoformat()
    for i in range(3):
        _route_order(i, day, items=(i != 0))  # 품목 없는 주문 = product 칼럼 폴백 경로
    url = f"{_ROUTE}?date={day}"
    client.get(url, headers=_SHELL)  # 데우기
    small = _route_statements(client, url)
    for i in range(6):
        _route_order(10 + i, day)
    big = _route_statements(client, url)
    lazy = sorted({m.group(1) for s in big for m in [_LAZY_COLUMN.search(s)] if m})
    assert lazy == [], (device, lazy)
    assert len(big) - len(small) <= 2, (device, len(small), len(big))
