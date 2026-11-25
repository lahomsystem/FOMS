"""P2: /erp/drawing-workbench route별 쿼리 수 예산 계약 (N+1 회귀 로컬 차단).

SQLAlchemy ``before_cursor_execute`` 이벤트로 라우트 처리 중 실제 SQL 수를 센다.
주문 4건(small) vs 12건(big) 차분으로 상수 오프셋을 상쇄하고, **행 수 증가가 쿼리
수를 늘리지 않음**(≤ALLOWED_DELTA)을 단언한다.

warmup: 콜드스타트 1회성 쿼리(feature flag 등)를 측정에서 제외해야 순수 per-row 비용이
드러난다(안 하면 콜드 오버헤드가 small을 부풀려 N+1을 가림).

캐시: dashboard 마이크로 캐시는 REDIS_URL 없으면 fail-open bypass(dashboard_cache)라
테스트 환경에서 raw 쿼리 경로가 그대로 측정됨 = N+1 감시에 적합.

시드 함정:
- workbench는 active_filter() + is_erp_order 스코프 후, 행별로 stage_code=='DRAWING'
  (또는 drawing_status=='RETURNED')만 남긴다. 그래서 workflow.stage='DRAWING'로 시드해야
  목록에 남아 per-row 조립 경로가 돈다. erp_stage_code는 sync(명시 호출)가 아니라 raw seed로
  직접 세팅한다(동일 값).
- seed는 250 cap 구조라 4/12건은 무관.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from foms.services.common import dashboard_cache as dc
from models import Order, OrderAttachment, OrderEvent, ProductionPartMark, User

_SEED_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)

# warmup 후 격리 실측: small(4건)=3, big(12건)=3 → delta=0 (완전 배치, per-row 없음).
# 여유 +2로 예산 2.
ALLOWED_DELTA = 2
# 절대 상한: 현 실측 big(3) + 여유 1 = 4.
ABS_QUERY_CAP = 4


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> User:
    user = User(
        username="drawing_qc_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면담당",
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
    stage = "DRAWING"
    order = Order(
        received_date="2026-06-01",
        customer_name=f"도면{idx}",
        phone=f"010-5000-{idx:04d}",
        address=f"서울시 도면구 {idx}",
        product="붙박이장",
        status="DRAWING",
        manager_name="도면담당",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {
                "customer": {"name": f"도면{idx}", "phone": f"010-5000-{idx:04d}"},
                "manager": {"name": "도면담당"},
            },
            "site": {"address_full": f"서울시 도면구 {idx}"},
            "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
            "drawing": {"status": "PENDING"},
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(2):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"d{idx}_{j}.jpg",
                file_type="image",
                category="drawing",
                file_size=10,
                storage_key=f"d/{idx}/{j}.jpg",
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
        "/erp/drawing-workbench?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )


def test_drawing_workbench_fragment_200(client):
    """fragment 헤더로 실제 200을 반환하는지(무의미 404 계약 방지)."""
    _login_admin(client)
    for i in range(4):
        _seed_order(i)
    resp = _fragment_get(client)
    assert resp.status_code == 200, f"/erp/drawing-workbench fragment -> {resp.status_code}"


def test_drawing_workbench_no_n_plus_one(client):
    """주문 4→12건으로 늘려도 route 추가 쿼리는 예산(≤ALLOWED_DELTA) 이내."""
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


# '생산 중' 칸(설계서 2026-11-25 §7, D3) — 모집단 SQL 두 번 + 하이드레이트(기본 큐와 한 번에) + 파트 표시 1번(그 쪽 주문 IN).
# 주문 8건을 더해도 증가 0, 절대 상한 = 기본 목록 실측 + 3. 기본 목록 실측 = 4(로그인 사용자 · seed · 칸 카운트 · 하이드레이트 —
# 2026-11-25 D3 전 코드도 4, 위 "3" 주석은 사용자 읽기를 빼고 센 옛 값). 칸 숫자는 누적 완료 카운트와 같은 문장에서 세어 그대로 4.
DEFAULT_LIST_QUERIES = 4
PRODUCTION_TAB_ABS_CAP = DEFAULT_LIST_QUERIES + 3


def _seed_production_order(idx: int) -> int:
    """'생산 중' 칸 가짜 주문(확정 도면 2장 · 파트 표시 1줄) — 줄 · 공장 진행 요약 경로가 돈다. ``idx % 4`` 로 모양을 돌린다:
    보통 · 영업 요청(RETURNED) · 공장 요청 + 고치는 중(``drawing_fix``) · 시공 대기(시공일 남음 — 표시 안 읽음)."""
    kind = idx % 4
    stage = "CONSTRUCTION" if kind == 3 else "PRODUCTION"
    order = Order(
        received_date="2026-06-01", customer_name=f"생산{idx}", phone=f"010-6000-{idx:04d}", address=f"서울시 생산구 {idx}",
        product="붙박이장", status=stage, manager_name="도면담당", is_erp_order=True, erp_stage_code=stage,
        erp_construction_date=(get_today_kst() + datetime.timedelta(days=3 + idx % 5)).isoformat(),
        structured_data={"workflow": {"stage": stage}, "parties": {"customer": {"name": f"생산{idx}"}},
                         "drawing_status": "RETURNED" if kind == 1 else "CONFIRMED", "drawing_current_files": []},
    )
    db_session.add(order)
    db_session.flush()
    files = [{"key": f"orders/{order.id}/drawing_wizard/exports/s{j}.png", "filename": f"s{j}.png", "sheet_id": f"s{j}"}
             for j in range(2)]
    history = [{"action": "REQUEST_REVISION", "by_user_name": "이영업", "at": "2026-06-02 01:00:00", "note": "깊이 고침"}] if kind == 1 else []
    fix = {"drawing_fix": {"fixing": {"sheet:s1": {"no": 2, "by_name": "김도면", "at": "2026-06-02T01:00:00Z"}},
                           "requests": [{"id": f"fr{idx}", "from": "factory", "targets": ["sheet:s0"], "numbers": [1],
                                         "state": "open", "by_name": "박반장", "at": "2026-06-02T02:00:00Z"}]}} if kind == 2 else {}
    order.structured_data = {**order.structured_data, "drawing_current_files": files, "drawing_transfer_history": history, **fix}
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=files[0]["key"], part="cut", state="DONE",
                                      done_by_name="김재단"))
    db_session.commit()
    return order.id


def _production_get(client):
    return client.get("/erp/drawing-workbench?view=fragment&status=PRODUCTION", headers={"X-FOMS-ERP-SHELL": "1"})


def test_drawing_workbench_production_tab_no_n_plus_one(client):
    """'생산 중' 칸: 주문 4 → 12건에도 쿼리 증가 0, 절대 상한 기본 목록 + 3."""
    _login_admin(client)
    for i in range(4):
        _seed_production_order(i)
    _production_get(client)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()
    _, q_small = _count_queries(lambda: _production_get(client))

    for i in range(100, 108):
        _seed_production_order(i)
    dc.reset_dashboard_cache_runtime_for_tests()
    resp_big, q_big = _count_queries(lambda: _production_get(client))

    html = resp_big.get_data(as_text=True)
    assert resp_big.status_code == 200 and html.count("dw-prod-prog") == 12 and "<b>제작 완료</b>" in html
    assert "수정 요청 · 영업" in html and "수정 요청 · 공장" in html and "도면 고치는 중" in html     # 모양 넷이 모두 돈다
    assert q_big - q_small == 0, f"'생산 중' 칸 N+1 의심: small={q_small}, big={q_big}"
    assert q_big <= PRODUCTION_TAB_ABS_CAP, f"'생산 중' 칸 절대 상한 초과: big={q_big} > {PRODUCTION_TAB_ABS_CAP}"


def test_default_list_queries_do_not_grow_with_production_tile(client):
    """기본 목록은 '생산 중' 칸 숫자를 세어도 쿼리가 늘지 않는다(누적 완료 카운트와 한 문장) — 생산 주문이 있어도 그대로."""
    _login_admin(client)
    for i in range(4):
        _seed_order(i)
    for i in range(200, 208):
        _seed_production_order(i)
    _fragment_get(client)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()
    resp, queries = _count_queries(lambda: _fragment_get(client))
    assert resp.status_code == 200 and "dw-prod-prog" not in resp.get_data(as_text=True)
    assert queries == DEFAULT_LIST_QUERIES, f"기본 목록 쿼리 {queries}건(전 {DEFAULT_LIST_QUERIES}건)"
