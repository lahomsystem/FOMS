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


def test_derive_legacy_status_fallback(client):
    """lifecycle 이 없는 레거시 주문은 status 로 유도된다(운영 566건 중 506건이 이 경우)."""
    assert derive_as_axis_status(_order(status="AS_RECEIVED")) == "RECEIVED"
    assert derive_as_axis_status(_order(status="AS")) == "IN_PROGRESS"
    assert derive_as_axis_status(_order(status="AS_COMPLETED")) == "COMPLETED"


def test_derive_ignores_date_only_traces(client):
    """날짜 흔적만 있는 레거시 주문은 AS 축으로 보지 않는다(화면 무변동 계약).

    ``as_received_date`` 만 남고 status 는 완료로 운영되던 옛 주문이 운영에 18건 있다.
    날짜로 유도하면 그 시절 종결된 건이 AS 대시보드에 되살아난다(2026-08-17 결정).
    """
    assert derive_as_axis_status(_order(status="COMPLETED", as_received_date="2026-04-13")) is None
    assert derive_as_axis_status(_order(status="COMPLETED", as_completed_date="2026-04-16")) is None


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


def test_sync_never_clears_existing_projection(client):
    """레거시 AS 주문(as_lifecycle 없음)의 status 를 덮어도 투영은 지워지지 않는다.

    2026-08-18 스테이징 실측에서 잡은 구멍: 일괄 상태변경이 ``sync_erp_flat_columns`` 를
    지나는데, lifecycle 없는 행은 유도 근거가 status 뿐이라 재유도하면 None 이 되어
    투영까지 지워졌다(= 사고 재현). AS 축은 한번 생기면 사라지지 않는다.
    """
    order = _order(status="AS_COMPLETED", as_completed_date="2026-06-24")
    sync_erp_flat_columns(order, order.structured_data)
    assert order.as_axis_status == "COMPLETED"

    order.status = "COMPLETED"  # 사고 형태의 외부 write
    sync_erp_flat_columns(order, order.structured_data)
    assert order.as_axis_status == "COMPLETED", "투영이 암묵적으로 지워지면 AS 목록이 증발한다"


def test_as_dashboard_still_lists_order_after_status_overwrite(client):
    """**2단 스위치 회귀** — status 를 덮어도 AS 대시보드 목록에 그대로 남는다.

    2026-08-14 사고의 결과(목록 증발)를 화면 레벨에서 잠근다. 술어가 status 로 되돌아가면
    이 테스트가 red 다.
    """
    _login(client, "axis_admin3")
    order = _order(status="CS", customer_name="AXISKEEP 고객",
                   structured_data={"workflow": {"stage": "CS"}})
    order_id = order.id
    client.post(f"/api/orders/{order_id}/as/register", json={"as_content": "AS 접수"})

    before_body = client.get("/erp/as").get_data(as_text=True)
    assert "AXISKEEP" in before_body

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    saved.status = "COMPLETED"  # 사고 재현: overlay projection 만 덮인다
    db_session.commit()

    after_body = client.get("/erp/as").get_data(as_text=True)
    assert "AXISKEEP" in after_body, "status 를 덮었다고 AS 대시보드에서 사라지면 안 된다"


def test_legacy_as_order_survives_bulk_complete_api(client):
    """**2026-08-14 사고 전체 재현** — lifecycle 없는 레거시 AS 주문을 일괄 완료해도 남는다.

    가드(AS 제외)를 명시로 우회(``include_as``)해 status 를 덮는, 사고와 동일한 경로다.
    술어·투영·동기화 셋 중 하나라도 되돌아가면 red.
    """
    _login(client, "axis_admin4")
    order = _order(status="AS_COMPLETED", customer_name="AXISLEGACY 고객",
                   as_received_date="2026-06-01", as_completed_date="2026-06-24",
                   structured_data={"workflow": {"stage": "CS"}})  # CS→COMPLETED = advance
    order_id = order.id

    completed_before = client.get("/erp/as?tab=completed").get_data(as_text=True)
    assert "AXISLEGACY" in completed_before

    resp = client.post("/api/bulk_update_order_status",
                       json={"order_ids": [order_id], "status": "COMPLETED", "include_as": True})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["updated"] == 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "COMPLETED"
    assert saved.as_axis_status == "COMPLETED"

    completed_after = client.get("/erp/as?tab=completed").get_data(as_text=True)
    assert "AXISLEGACY" in completed_after, "레거시 AS 주문이 일괄 완료로 목록에서 사라졌다"


def _open_as_lifecycle(cycle_id: str = "n1") -> dict:
    """LEGACY_BRIDGE 로 열린 AS cycle 1개(RECEIVED) — 운영 비ERP AS 주문의 실제 형태."""
    return {
        "current_cycle_id": cycle_id,
        "cycles": [{
            "cycle_id": cycle_id,
            "origin": "LEGACY_BRIDGE",
            "opened_at": "2026-08-05T00:00:00",
            "transitions": [{
                "seq": 1, "from": "NONE", "to": "RECEIVED",
                "at": "2026-08-05T00:00:00", "command": "AS_LEGACY_BRIDGE",
            }],
        }],
    }


def test_sync_fills_projection_for_non_erp_order(client):
    """**비ERP 드리프트 회귀** — is_erp_order=False 여도 AS 축 투영이 갱신된다.

    운영 실측(2026-09-03): status='AS_COMPLETED' + 완료일 있음 + as_axis_status='RECEIVED'
    인 주문 3건(#1315·#1119·#1706)이 모두 is_erp_order=False 였다.
    ``sync_erp_flat_columns`` 의 ERP 게이트가 AS 축 갱신보다 앞에 있어, 완료 커맨드가
    status 는 쓰고 축은 못 써서 미완료 탭에 남았다. AS 축은 ERP 여부와 직교한다.
    """
    lifecycle = _open_as_lifecycle("n_sync")
    lifecycle["cycles"][0]["transitions"].append({
        "seq": 2, "from": "RECEIVED", "to": "COMPLETED",
        "at": "2026-08-24T00:00:00", "command": "AS_COMPLETE",
    })
    order = _order(is_erp_order=False, status="AS_COMPLETED",
                   as_received_date="2026-08-05", as_completed_date="2026-08-24",
                   as_axis_status="RECEIVED", structured_data={"as_lifecycle": lifecycle})

    sync_erp_flat_columns(order, order.structured_data)

    assert order.as_axis_status == "COMPLETED", "비ERP 주문의 AS 축이 stale 로 남으면 미완료 탭에 갇힌다"


def test_sync_still_skips_erp_only_columns_for_non_erp_order(client):
    """비ERP 주문에서 ERP 전용 플랫 컬럼은 여전히 안 건드린다(게이트 축소 범위 계약)."""
    order = _order(is_erp_order=False, status="AS_RECEIVED", manager_name="원래담당",
                   as_axis_status="RECEIVED",
                   structured_data={"as_lifecycle": _open_as_lifecycle("n_scope"),
                                    "parties": {"manager": {"name": "새담당"}},
                                    "workflow": {"stage": "CS"}})

    sync_erp_flat_columns(order, order.structured_data)

    assert order.manager_name == "원래담당", "비ERP 주문에 ERP 전용 동기화가 새어들면 안 된다"
    assert order.erp_stage_code is None
    assert order.as_axis_status == "RECEIVED"


def test_non_erp_as_complete_moves_out_of_incomplete_tab(client):
    """**운영 사고 재현** — 비ERP AS 주문을 완료 처리하면 미완료 탭에서 빠진다.

    경로는 운영과 동일하다: AS 대시보드 완료 버튼 → ``/api/update_order_field``
    ``as_completed_date`` 브리지 → ``complete_as_cycle``(legacy_bridge). 이 경로가
    status 만 쓰고 as_axis_status 를 못 쓰면 초록 'AS완료' 뱃지를 단 채 미완료 탭에 남는다.
    """
    _login(client, "axis_admin_nonerp")
    order = _order(is_erp_order=False, status="AS_RECEIVED", customer_name="AXISNONERP 고객",
                   as_received_date="2026-08-05", as_axis_status="RECEIVED",
                   structured_data={"as_lifecycle": _open_as_lifecycle("n_e2e")})
    order_id = order.id

    assert "AXISNONERP" in client.get("/erp/as").get_data(as_text=True)

    resp = client.post("/api/update_order_field", json={
        "order_id": order_id, "field": "as_completed_date", "value": "2026-08-24"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.as_completed_date == "2026-08-24"
    assert saved.as_axis_status == "COMPLETED", "축이 안 따라오면 탭 술어가 계속 미완료로 본다"

    assert "AXISNONERP" not in client.get("/erp/as").get_data(as_text=True), \
        "완료 처리했는데 미완료 탭에 남아 있다(운영 #1315·#1119·#1706)"
    assert "AXISNONERP" in client.get("/erp/as?tab=completed").get_data(as_text=True)
