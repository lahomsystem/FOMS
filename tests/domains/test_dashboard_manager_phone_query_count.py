"""C1: 생산/시공 대시보드 행 DTO의 실측담당자 연락처 N+1 회귀 가드.

build_construction_row_dtos / build_production_enriched_rows는 행마다
load_erp_shipment_settings(SystemSetting 조회)를 호출하던 것을, 출고 설정 1회 로드로
만든 manager_phone_map 재사용으로 바꿨다. 시공 대시보드는 브라우즈에서 최대 300행을
DTO로 만들기 때문에 이 N+1이 TTFB의 큰 비중이었다(스테이징 실측: 시공 대시보드 warm
TTFB가 생산 대비 ~2배).

본 테스트는 (1) 주문 수를 늘려도 추가 쿼리가 상수임(=설정 1회 로드), (2) map 경로
결과가 기존 per-row(설정 매 호출) 경로와 동일함(동작 100% 보존)을 고정한다.
"""
from __future__ import annotations

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.construction_dashboard_display import build_construction_row_dtos
from foms.services.erp_mobile_order_display import resolve_manager_phone_for_queue
from foms.services.estimate_service import build_measurement_manager_phone_map
from foms.services.production_dashboard_display import build_production_enriched_rows
from models import Order, SystemSetting, User

_MANAGER_NAME = "큐담당"
_MANAGER_PHONE = "010-1234-5678"


def _make_user(username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CONSTRUCTION",
        name=_MANAGER_NAME,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed_settings() -> None:
    existing = (
        db_session.query(SystemSetting)
        .filter_by(setting_key="erp_shipment_settings")
        .first()
    )
    if existing:
        return
    db_session.add(
        SystemSetting(
            setting_key="erp_shipment_settings",
            setting_value={
                "measurement_manager": [
                    {"name": _MANAGER_NAME, "phone": _MANAGER_PHONE, "sort_order": 1}
                ],
                "construction_workers": [],
                "drawing_manager": [],
                "construction_time": [],
                "site_extra": [],
            },
            description="test",
        )
    )
    db_session.commit()


def _seed_order(idx: int, stage: str) -> int:
    order = Order(
        received_date="2026-06-01",
        customer_name=f"고객{idx}",
        phone=f"010-7000-{idx:04d}",
        address=f"서울시 디티오구 {idx}",
        product="싱크대",
        status="IN_CONSTRUCTION",
        manager_name=_MANAGER_NAME,
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {
                "customer": {"name": f"고객{idx}", "phone": f"010-7000-{idx:04d}"},
                "manager": {"name": _MANAGER_NAME},
            },
            "site": {"address_full": f"서울시 디티오구 {idx}"},
            "schedule": {"construction": {"date": "2026-06-10"}},
        },
    )
    db_session.add(order)
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
    return (
        db_session.query(Order)
        .filter(Order.id.in_(order_ids))
        .order_by(Order.id.asc())
        .all()
    )


def test_construction_row_dtos_no_n_plus_one(app):
    """주문 4건을 더 넣어도 manager_phone 설정 조회가 늘지 않는다(1회 로드)."""
    with app.app_context():
        _seed_settings()
        small_ids = [_seed_order(i, "CONSTRUCTION") for i in range(2)]
        big_ids = [_seed_order(i, "CONSTRUCTION") for i in range(100, 106)]  # 6건

        small = _fresh(small_ids)
        big = _fresh(big_ids)

        _, q_small = _count_queries(
            lambda: build_construction_row_dtos(small, {}, "")
        )
        _, q_big = _count_queries(
            lambda: build_construction_row_dtos(big, {}, "")
        )

        extra = q_big - q_small
        # per-row면 추가 4건 × 설정조회 = 4↑. 배치면 설정 1회뿐이라 ~0.
        assert extra <= 1, (
            f"manager_phone N+1 회귀 의심: 4건 추가 시 추가 쿼리 {extra}건 "
            f"(small={q_small}, big={q_big}, 기대 ≤1)"
        )


def test_production_enriched_rows_no_n_plus_one(app):
    """생산 대시보드도 manager_phone 설정 조회가 행 수와 무관(1회)."""
    with app.app_context():
        _seed_settings()
        small_ids = [_seed_order(i, "PRODUCTION") for i in range(200, 202)]
        big_ids = [_seed_order(i, "PRODUCTION") for i in range(300, 306)]

        small = _fresh(small_ids)
        big = _fresh(big_ids)

        _, q_small = _count_queries(
            lambda: build_production_enriched_rows(small, {})
        )
        _, q_big = _count_queries(
            lambda: build_production_enriched_rows(big, {})
        )

        extra = q_big - q_small
        assert extra <= 1, (
            f"manager_phone N+1 회귀 의심(production): 추가 쿼리 {extra}건 "
            f"(small={q_small}, big={q_big}, 기대 ≤1)"
        )


def test_manager_phone_map_matches_per_row(app):
    """map 경로(resolve with map)가 기존 per-row 경로(설정 매 호출)와 동일 값."""
    with app.app_context():
        _seed_settings()
        order_id = _seed_order(500, "CONSTRUCTION")
        (order,) = _fresh([order_id])
        parties = (order.structured_data or {}).get("parties") or {}

        phone_map = build_measurement_manager_phone_map()
        with_map = resolve_manager_phone_for_queue(
            parties, order=order, manager_phone_map=phone_map
        )
        per_row = resolve_manager_phone_for_queue(parties, order=order)

        assert with_map == per_row == _MANAGER_PHONE


def test_construction_row_manager_phone_resolved(app):
    """DTO 행의 manager_phone이 설정값으로 채워진다(end-to-end)."""
    with app.app_context():
        _seed_settings()
        order_id = _seed_order(600, "CONSTRUCTION")
        rows = build_construction_row_dtos(_fresh([order_id]), {}, "")
        assert rows and rows[0]["manager_phone"] == _MANAGER_PHONE
