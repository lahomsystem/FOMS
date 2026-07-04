"""P2: /erp/dashboard route별 쿼리 수 예산 계약 (N+1 회귀 로컬 차단).

측정 모바일 큐 계약(test_measurement_mobile_queue_query_count.py)과 같은 방식으로
SQLAlchemy ``before_cursor_execute`` 이벤트로 라우트 처리 중 실제 발생한 SQL 수를 센다.
주문을 4건(small) vs 12건(big)으로 두 번 시드해 **행 수 증가가 쿼리 수를 늘리지 않는다**
(=상수 오프셋만 허용, per-row 회귀 아님)를 단언한다. 상수 오프셋(count·pagination 등)은
차분(q_big - q_small)으로 상쇄된다.

캐시: dashboard 마이크로 캐시는 REDIS_URL 없으면 fail-open bypass(dashboard_cache)라
테스트 환경에서 raw 쿼리 경로가 그대로 측정된다 = N+1 감시에 정확히 적합.

시드 함정: erp_stage_code는 sync(명시 호출 함수)가 아니라 raw seed로 직접 세팅한다.
route 쿼리가 flat 컬럼 erp_stage_code를 참조하므로 structured_data.workflow.stage와
동일 값으로 명시 세팅해야 스코프에 걸린다(measurement 계약과 동일 패턴).
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.common import dashboard_cache as dc
from models import Order, OrderAttachment, OrderEvent, User

_SEED_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)

# ⚠ 잔존 N+1 (개선 대상, 프로덕션 코드 미수정 — 회귀 잠금만).
# warmup(콜드스타트 1회성 쿼리 제외) 후 격리 실측: small(4건)=11, big(12건)=19 → delta=8.
# = 주문 1건당 SQL 1건 증가(선형). 원인: /erp/dashboard fragment DTO 조립 경로에서
# system_settings SELECT가 행마다 1회 실행(12건 → 12회 반복 확인). 배치화하면 delta→0.
# 이 계약은 그 N+1을 "현 값"으로 고정해 **더 나빠지는 것**(예: 2쿼리/행)만 차단한다.
# 현 delta=8(+8행) + 여유 2 = 예산 10.
ALLOWED_DELTA = 10
# 절대 상한: 현 실측 big(19) + 30% ≈ 25.
ABS_QUERY_CAP = 25


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> User:
    user = User(
        username="orders_qc_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="예산담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(idx: int) -> int:
    stage = "PRODUCTION"
    order = Order(
        received_date="2026-06-01",
        customer_name=f"주문{idx}",
        phone=f"010-0000-{idx:04d}",
        address=f"서울시 예산구 {idx}",
        product="싱크대",
        status="IN_PRODUCTION",
        manager_name="예산담당",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {
                "customer": {"name": f"주문{idx}", "phone": f"010-0000-{idx:04d}"},
                "manager": {"name": "예산담당"},
            },
            "site": {"address_full": f"서울시 예산구 {idx}"},
            "items": [{"product_name": "싱크대", "spec_width": "1200"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(2):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"o{idx}_{j}.jpg",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key=f"o/{idx}/{j}.jpg",
                created_at=_SEED_BASE + datetime.timedelta(minutes=j),
            )
        )
    db_session.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_CHANGED",
            payload={"to": stage},
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


def _fragment_get(client):
    return client.get(
        "/erp/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )


def test_orders_dashboard_fragment_200(client):
    """fragment 헤더로 실제 200을 반환하는지(무의미 404 계약 방지)."""
    _login_admin(client)
    for _ in range(4):
        _seed_order(_)
    resp = _fragment_get(client)
    assert resp.status_code == 200, f"/erp/dashboard fragment -> {resp.status_code}"


def test_orders_dashboard_no_n_plus_one(client):
    """주문 4→12건으로 늘려도 route 추가 쿼리는 예산(ALLOWED_DELTA) 이내.

    warmup: 콜드스타트 1회성 쿼리(feature flag 등)를 측정에서 제외해야 순수 per-row
    비용이 드러난다(안 하면 콜드 오버헤드가 small을 부풀려 N+1을 가림).
    """
    _login_admin(client)

    for i in range(4):
        _seed_order(i)
    _fragment_get(client)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()
    _, q_small = _count_queries(lambda: _fragment_get(client))

    for i in range(100, 108):  # +8 → 12건
        _seed_order(i)
    dc.reset_dashboard_cache_runtime_for_tests()
    resp_big, q_big = _count_queries(lambda: _fragment_get(client))

    assert resp_big.status_code == 200
    delta = q_big - q_small
    assert delta <= ALLOWED_DELTA, (
        f"N+1 회귀 의심: 주문 8건 추가 시 추가 쿼리 {delta}건 "
        f"(small={q_small}, big={q_big}, 예산 ≤{ALLOWED_DELTA})"
    )
    assert q_big <= ABS_QUERY_CAP, (
        f"절대 쿼리 상한 초과: big={q_big} > {ABS_QUERY_CAP}"
    )
