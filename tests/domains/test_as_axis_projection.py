"""AS-AXIS-01 1단 계약: AS 축 플랫 투영(``orders.as_axis_status``).

목록 술어를 status 컬럼에서 떼어내기 위한 투영값이다. 계약 3종:

1. 유도 규칙 — as_lifecycle 우선, 없으면 legacy(status/완료일/접수일) 폴백
2. 동기화 — AS 쓰기 경로가 지나가면 컬럼이 canonical 축과 일치
3. 드리프트 0 — 저장된 컬럼값 == 유도값

술어 교체(2단)는 별도 배포다 — 이 파일은 "컬럼이 정확히 채워지는가"까지만 잠근다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.state_axes import derive_as_axis_status, read_as_status


def _order(**kwargs) -> Order:
    """테스트용 ERP 주문(기본은 AS 이력 없음)."""
    defaults = dict(
        received_date="2026-08-01", customer_name="axis-고객", phone="010-0000-0000",
        address="Seoul", product="붙박이장", status="MEASURE", manager_name="Mgr",
        is_erp_order=True, structured_data={"workflow": {"stage": "MEASURE"}},
    )
    defaults.update(kwargs)
    order = Order(**defaults)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username: str) -> User:
    """AS API 호출용 ADMIN 로그인."""
    user = User(username=username, password=generate_password_hash("pw"), role="ADMIN",
                team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_derive_prefers_as_lifecycle(client):
    """as_lifecycle 이 있으면 그 현재 cycle 상태가 이긴다(legacy status 와 달라도)."""
    lifecycle = {
        "current_cycle_id": "c1",
        "cycles": [{"cycle_id": "c1", "transitions": [
            {"seq": 1, "to": "RECEIVED"}, {"seq": 2, "to": "COMPLETED"}]}],
    }
    order = _order(status="AS_RECEIVED",
                   structured_data={"workflow": {"stage": "MEASURE"}, "as_lifecycle": lifecycle})
    assert read_as_status(order) == "COMPLETED"
    assert derive_as_axis_status(order) == "COMPLETED"


def test_derive_legacy_fallbacks(client):
    """lifecycle 이 없는 레거시 주문도 유도된다(운영 566건 중 506건이 이 경우)."""
    assert derive_as_axis_status(_order(status="AS_RECEIVED")) == "RECEIVED"
    assert derive_as_axis_status(_order(status="AS")) == "IN_PROGRESS"
    assert derive_as_axis_status(_order(status="AS_COMPLETED")) == "COMPLETED"
    # status 는 이미 덮였지만 legacy 날짜 흔적이 남은 경우(2026-08-14 사고 형태)
    assert derive_as_axis_status(_order(status="COMPLETED", as_completed_date="2026-08-10")) == "COMPLETED"
    assert derive_as_axis_status(_order(status="COMPLETED", as_received_date="2026-08-10")) == "RECEIVED"


def test_derive_none_when_no_as_history(client):
    """AS 이력이 없으면 None — 부분 인덱스에 안 들어간다."""
    assert derive_as_axis_status(_order(status="COMPLETED")) is None
    assert derive_as_axis_status(_order(status="MEASURE", as_received_date="")) is None


def test_derive_uses_explicit_structured_data(client):
    """쓰기 경로가 ORM 배정 전 dict 를 넘겨도 최신 lifecycle 로 판정한다."""
    order = _order(status="MEASURE")
    fresh = {"workflow": {"stage": "MEASURE"},
             "as_lifecycle": {"current_cycle_id": "c9",
                              "cycles": [{"cycle_id": "c9", "transitions": [{"seq": 1, "to": "RECEIVED"}]}]}}
    assert derive_as_axis_status(order, fresh) == "RECEIVED"


def test_sync_erp_flat_columns_fills_projection(client):
    """플랫 동기화 한 번이면 컬럼이 채워진다(모든 AS 쓰기 경로가 이 함수를 지난다)."""
    order = _order(status="AS_RECEIVED", as_received_date="2026-08-14")
    sync_erp_flat_columns(order, order.structured_data)
    assert order.as_axis_status == "RECEIVED"


def test_as_register_api_sets_projection(client):
    """AS 접수 API 를 타면 컬럼이 canonical 축과 같아진다."""
    _login(client, "axis_admin")
    order = _order(status="CS", structured_data={"workflow": {"stage": "CS"}})
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "도어 교체 요청"})
    assert resp.status_code in (200, 201), resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.as_axis_status == read_as_status(saved)
    assert saved.as_axis_status == "RECEIVED"


def test_projection_survives_status_overwrite(client):
    """**사고 재현 회귀** — status 를 COMPLETED 로 덮어도 AS 축 투영은 살아 있다.

    2026-08-14 사고에서 사라진 것은 status 술어로 조회한 목록이었다. 투영 컬럼은
    as_lifecycle/legacy 흔적 기반이라 status 를 덮어도 값이 남고, 2단에서 목록 술어가
    이 컬럼으로 바뀌면 목록 자체가 안 흔들린다.
    """
    _login(client, "axis_admin2")
    order = _order(status="CS", structured_data={"workflow": {"stage": "CS"}})
    order_id = order.id
    client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "AS 접수"})

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    saved.status = "COMPLETED"  # 사고 형태: 외부 write 가 overlay projection 을 덮음
    db_session.commit()

    db_session.expire_all()
    after = db_session.get(Order, order_id)
    assert after.status == "COMPLETED"
    assert after.as_axis_status == "RECEIVED"  # AS 축은 그대로
    assert derive_as_axis_status(after) == "RECEIVED"
