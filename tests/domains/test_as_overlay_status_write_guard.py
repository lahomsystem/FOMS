"""AS overlay 가 물류 축 status 쓰기를 이기는 계약 (2026-09-03 운영 사고).

지방 대시보드 체크리스트 자동 승격(`checkAllCompleted`)이 `/api/update_order_field`
로 `status='SCHEDULED'` 를 쏘면, 서버가 열린 AS 건을 보지 않고 `order.status` 를
날것으로 덮었다. 지방 AS 섹션 술어(`o.status == 'AS_RECEIVED'`)와 ERP 주문 화면의
'AS: 접수' 뱃지가 둘 다 그 컬럼을 읽으므로, 체크박스 한 번에 AS 접수 건이 화면에서
통째로 사라졌다(운영 #4796 권디모데 · #4816 배종성 — 지방 AS 활성 건 전부).

읽기 SSOT `legacy_status_projection` 의 우선순위는 이미
DELETED > ON_HOLD > AS_* > logistics > main 이다. 이 계약은 그 우선순위를 **쓰기
경로에도** 적용한다: 열린 AS 건이 있으면 물류 축 목표(MEASURED/REGIONAL_MEASURED/
SCHEDULED/SHIPPED_PENDING)는 status 를 덮지 않는다.

거부(403)가 아니라 무시다 — 실패 배너는 .alert 5초 자동닫힘에 지워져 무음 실패가
되고, 체크리스트 저장 자체는 정상 업무이기 때문이다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _order(**kwargs) -> Order:
    """지방 ERP 주문 픽스처."""
    defaults = dict(
        received_date="2026-09-01", customer_name="가드 QA", phone="010-0000-0000",
        address="충남 천안시 테스트로 1", product="붙박이장", status="MEASURED",
        is_erp_order=True, is_regional=True, measurement_completed=True,
        structured_data={"workflow": {"stage": "MEASURE"}},
    )
    defaults.update(kwargs)
    order = Order(**defaults)
    db_session.add(order)
    db_session.commit()
    return order


def _open_as(cycle_id: str) -> dict:
    """RECEIVED 로 열린 AS cycle 1개."""
    return {
        "current_cycle_id": cycle_id,
        "cycles": [{
            "cycle_id": cycle_id,
            "opened_at": "2026-09-01T00:00:00",
            "transitions": [{
                "seq": 1, "from": "NONE", "to": "RECEIVED",
                "at": "2026-09-01T00:00:00", "command": "AS_REGISTER",
            }],
        }],
    }


def _login(client, username: str) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role="ADMIN",
                team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


@pytest.mark.parametrize("target", ["SCHEDULED", "MEASURED", "SHIPPED_PENDING", "REGIONAL_MEASURED"])
def test_field_update_keeps_as_status_against_logistics_write(client, target):
    """열린 AS 건이면 물류 축 status 쓰기가 AS 투영을 못 덮는다(field_update 경로)."""
    _login(client, f"guard_fu_{target.lower()}")
    order = _order(status="AS_RECEIVED", as_received_date="2026-09-01",
                   structured_data={"workflow": {"stage": "MEASURE"},
                                    "as_lifecycle": _open_as(f"g_{target}")})
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": target})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "AS_RECEIVED", f"{target} 쓰기가 AS 투영을 덮었다(지방 AS 섹션 증발)"
    assert resp.get_json()["status"] == "AS_RECEIVED", "응답이 저장되지 않은 값을 사실처럼 알린다"


def test_update_order_status_keeps_as_status_against_logistics_write(client):
    """단건 상태 변경 엔드포인트에도 같은 가드가 대칭으로 있어야 한다."""
    _login(client, "guard_status_single")
    order = _order(status="AS_RECEIVED", as_received_date="2026-09-01",
                   structured_data={"workflow": {"stage": "MEASURE"},
                                    "as_lifecycle": _open_as("g_single")})
    order_id = order.id

    resp = client.post("/api/update_order_status",
                       json={"order_id": order_id, "status": "SCHEDULED"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "AS_RECEIVED"


def test_legacy_as_order_without_lifecycle_is_also_protected(client):
    """as_lifecycle 이 없는 레거시 AS 주문(운영 다수)도 status 로 판정돼 보호된다."""
    _login(client, "guard_legacy_as")
    order = _order(status="AS_RECEIVED", as_received_date="2026-09-01")
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": "SCHEDULED"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "AS_RECEIVED"


def test_non_as_order_still_gets_logistics_promotion(client):
    """**음성 대조군** — AS 축이 없는 주문은 예전처럼 물류 승격이 그대로 된다."""
    _login(client, "guard_control_plain")
    order = _order(status="MEASURED")
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": "SCHEDULED"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "SCHEDULED", "가드가 일반 주문까지 막았다"


def test_completed_as_order_is_not_blocked(client):
    """닫힌 AS 건(COMPLETED)은 가드 대상이 아니다 — 열린 건만 막는다."""
    _login(client, "guard_control_closed")
    lifecycle = _open_as("g_closed")
    lifecycle["cycles"][0]["transitions"].append({
        "seq": 2, "from": "RECEIVED", "to": "COMPLETED",
        "at": "2026-09-02T00:00:00", "command": "AS_COMPLETE",
    })
    order = _order(status="AS_COMPLETED", as_received_date="2026-09-01",
                   as_completed_date="2026-09-02",
                   structured_data={"workflow": {"stage": "MEASURE"}, "as_lifecycle": lifecycle})
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": "SCHEDULED"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "SCHEDULED"


def test_deliberate_main_stage_change_is_not_blocked(client):
    """의도적인 본공정 전이는 계속 통과한다 — 가드는 물류 축 자동 승격만 막는다."""
    _login(client, "guard_control_main")
    order = _order(status="AS_RECEIVED", as_received_date="2026-09-01",
                   structured_data={"workflow": {"stage": "MEASURE"},
                                    "as_lifecycle": _open_as("g_main")})
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": "ON_HOLD"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "ON_HOLD"


def test_regional_dashboard_checklist_excludes_as_rows():
    """클라 지혈 계약 — 체크리스트 자동 승격이 AS 행 3종 표식을 전부 제외한다.

    행 클래스가 섹션마다 다르다: AS 전용 섹션은 ``as-order-row``, 상차 예정 알림
    섹션의 AS 행은 ``regional-as-shipping-row``(+ ``data-as-shipping-schedule``).
    운영 사고를 낸 쪽은 후자이므로 ``as-order-row`` 만 봐서는 안 걸린다.
    """
    from pathlib import Path

    source = Path("templates/measurement/regional_dashboard.html").read_text(encoding="utf-8")
    start = source.index("function checkAllCompleted")
    body = source[start:source.index("function syncStatusToShippingDate")]

    assert "as-order-row" in body
    assert "regional-as-shipping-row" in body
    assert "asShippingSchedule" in body or "data-as-shipping-schedule" in body
