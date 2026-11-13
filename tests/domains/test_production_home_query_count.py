"""생산 첫 화면(``/erp/production/home``) 쿼리 수 계약 — 설계서 §15.6 '쿼리 수' · §15.7(P15-3 첫 단계).

옛 보드 계약(``test_production_dashboard_query_count.py``)과 같은 꼴: SQLAlchemy ``before_cursor_execute`` 로 라우트
한 번의 실제 SQL 수를 세고, 주문 4건 대 12건 차이로 **주문이 늘어도 쿼리가 늘지 않음**(≤``ALLOWED_DELTA``)과 절대
상한(실측 + 30%)을 함께 단언한다. 파트 화면(P15-5)은 이 위에 표시 줄 읽기 +1 만 허용한다.

warmup: 첫 요청의 한 번뿐인 쿼리(설정 · 기능 스위치 등)를 재기에서 뺀다 — 안 빼면 small 이 부풀어 N+1 을 가린다.
시드 함정: 첫 화면 쿼리는 납작 칸 ``erp_stage_code`` 와 ``erp_construction_date`` 로 고르므로 둘 다 직접 넣는다.
"""
from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from models import Order, ProductionRun, User

HOME_URL = "/erp/production/home"

# 실측(2026-11-13, SQLite 레인, 파트 없는 생산팀 계정): small(4건) = 9, big(12건) = 9 → 차이 0.
# 아홉 = 로그인 사용자 · 바탕 주문 · 지난 주문 수 · 제작 회차 id · 설정 2(출고 설정 · 물어보기 설정) · 변경 알림
# 이벤트 · 묘비(취소 주문) · 협력사 이름 목록. 행마다 붙는 쿼리는 없다.
ALLOWED_DELTA = 2
# 절대 상한 = 실측 big(9) + 30% ≈ 11.
ABS_QUERY_CAP = 11


def _login(client) -> User:
    user = User(
        username="prod_home_qc", password=generate_password_hash("x"), role="STAFF",
        team="PRODUCTION", name="생산첫화면", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(idx: int) -> int:
    """생산 단계 주문 1건 — 확정 도면 2장, 짝수는 제작 회차까지(제작 대기 · 만드는 중 섞기)."""
    day = (get_today_kst() + datetime.timedelta(days=idx % 5)).isoformat()
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "parties": {"customer": {"name": f"첫화면{idx}", "phone": f"010-3000-{idx:04d}"}},
        "site": {"address_full": f"서울시 생산구 {idx}"},
        "schedule": {"construction": {"date": day}},
        "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
        "drawing_current_files": [
            {"key": f"orders/{idx}/drawing/a{j}.png", "filename": f"a{j}.png"} for j in range(2)
        ],
    }
    order = Order(
        received_date=get_today_kst().isoformat(), customer_name=f"첫화면{idx}", phone=f"010-3000-{idx:04d}",
        address=f"서울시 생산구 {idx}", product="붙박이장", status="PRODUCTION", manager_name="생산첫화면",
        is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=day, structured_data=sd,
    )
    db_session.add(order)
    db_session.flush()
    if idx % 2 == 0:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
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


def test_production_home_query_count_does_not_grow_with_orders(client):
    """주문 4 → 12건으로 늘려도 첫 화면(날짜 탭) 쿼리 수가 늘지 않고, 절대 상한 안이다."""
    _login(client)
    for i in range(4):
        _seed_order(i)
    warm = client.get(HOME_URL)
    assert warm.status_code == 200
    resp_small, q_small = _count_queries(lambda: client.get(HOME_URL))
    assert resp_small.status_code == 200
    assert "첫화면0" in resp_small.get_data(as_text=True)  # 시드가 실제로 화면에 섰다(빈 화면 재기 방지)

    for i in range(100, 108):  # +8 → 12건
        _seed_order(i)
    resp_big, q_big = _count_queries(lambda: client.get(HOME_URL))
    assert resp_big.status_code == 200
    assert "첫화면107" in resp_big.get_data(as_text=True)

    delta = q_big - q_small
    assert delta <= ALLOWED_DELTA, f"N+1 회귀 의심: 주문 8건 더해 쿼리 {delta}건 늘었어요(small={q_small}, big={q_big})"
    assert q_big <= ABS_QUERY_CAP, f"절대 쿼리 상한 넘음: big={q_big} > {ABS_QUERY_CAP}"
