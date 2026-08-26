"""P2: /erp/history route별 쿼리 수 예산 계약 (N+1 회귀 로컬 차단).

SQLAlchemy ``before_cursor_execute`` 이벤트로 라우트 처리 중 실제 SQL 수를 센다.
주문 4건(small) vs 12건(big) 차분으로 상수 오프셋을 상쇄하고, **행 수 증가가 쿼리
수를 늘리지 않음**(≤ALLOWED_DELTA)을 단언한다.

warmup: 콜드스타트 1회성 쿼리(feature flag 등)를 측정에서 제외해야 순수 per-row 비용이
드러난다(안 하면 콜드 오버헤드가 small을 부풀려 N+1을 가림).

캐시: dashboard 마이크로 캐시는 REDIS_URL 없으면 fail-open bypass(dashboard_cache)라
테스트 환경에서 raw 쿼리 경로가 그대로 측정됨 = N+1 감시에 적합.

시드/route 함정:
- history route는 url_prefix='/erp/history' + '/' 라 반드시 **trailing slash**(`/erp/history/`)로
  요청해야 308 리다이렉트를 피한다.
- history는 필수 필터가 있어야 목록을 로드한다(무차별 Full Scan 방지). 여기선 stage 필터를
  주어(?stage=CONSTRUCTION) has_filter=True → 실제 per-row 조립 경로가 돈다.
- active_filter(전기간) + stage(erp_stage_code==f_stage OR status==f_stage) 스코프.
  erp_stage_code는 sync(명시 호출)가 아니라 raw seed로 직접 세팅한다.
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

# warmup 후 격리 실측: small(4건)=10, big(12건)=10 → delta=0 (완전 배치, per-row 없음).
# 모바일 queue-card-v2 행 조립(첨부/미리보기/타임라인 배치)이 상수 쿼리를 더한다.
# 여유 +2로 예산 2.
ALLOWED_DELTA = 2
# 절대 상한: 현 실측 big(10) + 30% ≈ 13.
ABS_QUERY_CAP = 13


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> User:
    user = User(
        username="history_qc_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="이력담당",
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
    stage = "CONSTRUCTION"
    order = Order(
        received_date="2026-06-01",
        customer_name=f"이력{idx}",
        phone=f"010-4000-{idx:04d}",
        address=f"서울시 이력구 {idx}",
        product="싱크대",
        status="IN_CONSTRUCTION",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={
            "workflow": {"stage": stage},
            "parties": {
                "customer": {"name": f"이력{idx}", "phone": f"010-4000-{idx:04d}"},
                "manager": {"name": "이력담당"},
            },
            "site": {"address_full": f"서울시 이력구 {idx}"},
            "items": [{"product_name": "싱크대", "spec_width": "1200"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    for j in range(2):
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename=f"h{idx}_{j}.jpg",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key=f"h/{idx}/{j}.jpg",
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
    # trailing slash 필수(308 회피) + stage 필터로 has_filter=True(목록 로드).
    return client.get(
        "/erp/history/?view=fragment&stage=CONSTRUCTION",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )


def test_history_dashboard_fragment_200(client):
    """fragment 헤더로 실제 200을 반환하는지(무의미 404/308 계약 방지)."""
    _login_admin(client)
    for i in range(4):
        _seed_order(i)
    resp = _fragment_get(client)
    assert resp.status_code == 200, f"/erp/history/ fragment -> {resp.status_code}"


def test_history_dashboard_no_n_plus_one(client):
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


def test_history_main_row_exposes_side_sheet_source(client):
    """B2 렌더 스모크: 이력 데스크톱 테이블 본행이 태블릿 side-sheet 위임 소스
    (history-main-row + data-order-id)를 실제로 렌더한다(200 + 본행 소스). 확장행/chevron
    확장 UX 는 무변경(회귀 방지 동반 확인)."""
    _login_admin(client)
    oid = _seed_order(0)
    resp = _fragment_get(client)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="history-main-row"' in body
    assert f'data-order-id="{oid}"' in body
    # 본행이 읽기전용 스냅샷 시트를 명시 지정(편집 fragment 폴백 차단 — gap1).
    assert f"/erp/history/tablet-sheet/{oid}" in body
    # 확장행/chevron 보존.
    assert 'class="history-detail-row"' in body
    assert "history-chevron" in body


def test_history_tablet_sheet_renders_readonly_snapshot(client):
    """gap1: 이력 본행 탭 → 읽기전용 스냅샷 시트 라우트가 200 + 편집 입력 없이 렌더된다.
    편집 fragment(<input>/<textarea>/<select>)가 아니라 읽기전용 스냅샷이어야 하며, 수정은
    '원 주문 열기' 점프로만 가능하다. 완료일(시공일)·요약·정산 스냅샷을 파생 렌더한다."""
    _login_admin(client)
    order = Order(
        received_date="2026-06-01",
        customer_name="스냅샷고객",
        phone="010-7777-0001",
        address="서울시 감사구 1",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "parties": {"customer": {"name": "스냅샷고객", "phone": "010-7777-0001"}},
            "schedule": {"construction": {"date": "2026-06-20"}},
            "items": [
                {"product_name": "붙박이장", "width": "2400", "depth": "600",
                 "height": "2400", "color": "화이트"}
            ],
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/history/tablet-sheet/{order.id}")
    assert resp.status_code == 200, f"sheet -> {resp.status_code}"
    body = resp.get_data(as_text=True)
    # 읽기전용 스냅샷 마커 + 파생 필드.
    assert "읽기전용" in body
    assert "스냅샷고객" in body
    assert "붙박이장" in body
    assert "2026-06-20" in body  # 완료일 = 시공일 파생
    # 원 주문 점프(수정은 여기서만) + 헤드 #id.
    assert "원 주문 열기" in body
    assert f"#{order.id}" in body
    # 편집 입력 금지(읽기전용 — 편집 fragment 아님).
    assert "<input" not in body
    assert "<textarea" not in body
    assert "<select" not in body


def test_history_tablet_sheet_clamps_balance_when_only_deposit_present(client):
    """품목금액 0 · 예약금만 있는 주문의 이력 시트 잔금은 0원이다(음수 표기 금지).

    네이버 승격 주문은 실결제 총액을 예약금에만 담고 항목금액은 비운다 → 출고가 0.
    클램프가 없으면 정산 카드에 ``-1,229,000원`` 이 뜬다(서버 파생식
    structured_form_projection.recompute_totals 의 max(0, ...) 이 정본).
    """
    _login_admin(client)
    order = Order(
        received_date="2026-06-01",
        customer_name="예약금만고객",
        phone="010-7777-0002",
        address="서울시 감사구 2",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "parties": {"customer": {"name": "예약금만고객", "phone": "010-7777-0002"}},
            "schedule": {"construction": {"date": "2026-06-20"}},
            "items": [{"product_name": "붙박이장", "price": 0}],
            "payment": {"deposit": 1229000},
            "totals": {"items_total": 0},
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/history/tablet-sheet/{order.id}")
    assert resp.status_code == 200, f"sheet -> {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert "1,229,000원" in body  # 예약금은 그대로 보인다
    assert "-1,229,000원" not in body  # 음수 잔금 금지
    assert "<dt>잔금</dt><dd>0원</dd>" in body


def test_history_tablet_sheet_names_the_overpayment(client):
    """**과입금이 이력 시트에도 남는다** (2026-08-26 CEO L-1).

    잔금은 ``max(0, …)`` 이라 예약금이 출고가를 넘으면 "잔금 0원"만 남고 넘친 금액은
    어디에도 안 나온다 — 돌려줄 돈이 있다는 사실이 화면에서 사라진다.
    """
    _login_admin(client)
    order = Order(
        received_date="2026-06-01",
        customer_name="더낸고객",
        phone="010-7777-0009",
        address="서울시 감사구 9",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "parties": {"customer": {"name": "더낸고객", "phone": "010-7777-0009"}},
            "schedule": {"construction": {"date": "2026-06-20"}},
            "items": [{"product_name": "붙박이장", "price": 5000000}],
            "payment": {"deposit": 6000000},
            "totals": {"items_total": 5000000},
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/history/tablet-sheet/{order.id}")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<dt>잔금</dt><dd>0원</dd>" in body, "잔금 클램프 규칙은 그대로다"
    assert "과입금" in body and "1,000,000원" in body, "넘친 금액이 화면에서 사라졌다"


def test_history_tablet_sheet_does_not_call_measure_pending_overpaid(client):
    """실측 전 주문(출고가 0 · 예약금 N)은 과입금이 아니다 — 총액 미확정이다."""
    _login_admin(client)
    order = Order(
        received_date="2026-06-01",
        customer_name="실측전고객",
        phone="010-7777-0010",
        address="서울시 감사구 10",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "parties": {"customer": {"name": "실측전고객", "phone": "010-7777-0010"}},
            "schedule": {"construction": {"date": "2026-06-20"}},
            "items": [{"product_name": "붙박이장", "price": 0}],
            "payment": {"deposit": 1229000},
            "totals": {"items_total": 0},
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/history/tablet-sheet/{order.id}")

    assert resp.status_code == 200
    assert "과입금" not in resp.get_data(as_text=True), "총액 미확정을 과입금이라 불렀다"


def test_history_tablet_sheet_keeps_balance_for_priced_items(client):
    """회귀 방지: 품목금액이 있는 주문의 이력 시트 잔금은 출고가 − 예약금 그대로."""
    _login_admin(client)
    order = Order(
        received_date="2026-06-01",
        customer_name="정상금액고객",
        phone="010-7777-0003",
        address="서울시 감사구 3",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        structured_data={
            "parties": {"customer": {"name": "정상금액고객", "phone": "010-7777-0003"}},
            "schedule": {"construction": {"date": "2026-06-20"}},
            "items": [{"product_name": "붙박이장", "price": 5000000}],
            "payment": {"deposit": 1000000},
            "totals": {"items_total": 5000000},
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(f"/erp/history/tablet-sheet/{order.id}")
    assert resp.status_code == 200, f"sheet -> {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert "<dt>출고가</dt><dd>5,000,000원</dd>" in body
    assert "<dt>잔금</dt><dd>4,000,000원</dd>" in body


def test_history_search_finds_long_completed_order(client):
    """회귀 차단: 완료된 지 60일 넘은 주문도 이력 검색에 나온다.

    8ffc9c4a에서 history 스코프가 dashboard_active_filter(days=60)로 바뀌어, 완료
    (erp_stage_code=COMPLETED)+erp_stage_updated_at이 60일 이전인 주문이 이력 검색에서만
    사라졌다(운영 '성봉희' 사례 — 전체 주문 목록에서는 검색됨). 스코프는 active_filter(전기간).
    """
    _login_admin(client)
    old = datetime.datetime.now() - datetime.timedelta(days=180)
    order = Order(
        received_date="2026-01-05",
        customer_name="옛완료고객",
        phone="010-8888-0001",
        address="서울시 이력구 99",
        product="붙박이장",
        status="COMPLETED",
        manager_name="이력담당",
        is_erp_order=True,
        erp_stage_code="COMPLETED",
        erp_stage_updated_at=old,
        created_at=old,
        structured_data={
            "workflow": {"stage": "COMPLETED"},
            "parties": {"customer": {"name": "옛완료고객", "phone": "010-8888-0001"}},
        },
    )
    db_session.add(order)
    db_session.commit()

    resp = client.get(
        "/erp/history/?view=fragment&q=옛완료고객",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f'data-order-id="{order.id}"' in body, "60일 초과 완료 주문이 이력 검색에서 누락됨"


def test_history_tablet_sheet_document_nav_redirects_to_edit(client):
    """주소창/새 탭 직접 진입(Sec-Fetch-Dest=document)은 비스타일 partial 노출 대신
    정본 edit 페이지로 302 (dashboard tablet-sheet 전례)."""
    _login_admin(client)
    oid = _seed_order(0)
    resp = client.get(
        f"/erp/history/tablet-sheet/{oid}",
        headers={"Sec-Fetch-Dest": "document"},
    )
    assert resp.status_code in (301, 302)
    assert f"/order" in resp.headers.get("Location", "") or "edit" in resp.headers.get("Location", "")
