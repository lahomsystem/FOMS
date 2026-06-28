import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client):
    user = User(
        username="erp_as_tabs_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP AS Tabs Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(
    *,
    notes=None,
    as_content_2="<div>2번 내용</div>",
    status="AS_RECEIVED",
    as_completed_date=None,
    shipment_extra=None,
    schedule_extra=None,
    customer_name="AS 탭 고객",
):
    today = date.today().strftime("%Y-%m-%d")
    shipment = {
        "as_content": "<div>1번 내용</div>",
    }
    if as_content_2 is not None:
        shipment["as_content_2"] = as_content_2
    if shipment_extra:
        shipment.update(shipment_extra)
    structured_data = {"shipment": shipment}
    if schedule_extra:
        structured_data["schedule"] = schedule_extra
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today,
        as_completed_date=as_completed_date,
        is_erp_order=True,
        notes=notes,
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_dashboard_base_query_includes_pure_as_status():
    """후속 계획: ERP AS 대시보드가 status=AS 주문도 목록에 포함한다.

    Batch 5: AS 미완료/완료 탭 조건이 foms/services/as_dashboard_helpers.py로 이전됨
    → 라우트 + helpers 두 파일을 합쳐 검사(AS 상태 처리 SSOT 유지).
    """
    root = Path(__file__).resolve().parents[2]
    src = (root / "foms/web/cs/as_dashboard.py").read_text(encoding="utf-8")
    src += (root / "foms/services/as_dashboard_helpers.py").read_text(encoding="utf-8")
    assert "Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED'])" in src
    assert "Order.status == 'AS'" in src


def test_as_pc_and_mobile_workflow_affordances_are_present():
    root = Path(__file__).resolve().parents[2]
    body = (root / "templates/cs/partials/as_dashboard_body.html").read_text(
        encoding="utf-8"
    )
    mobile_card = (root / "templates/cs/partials/as_mobile_order_card.html").read_text(
        encoding="utf-8"
    )
    card_macros = (root / "templates/cs/partials/as_card_macros.html").read_text(
        encoding="utf-8"
    )

    for token in (
        "editable-date-as",
        "as-pending-btn",
        "as-blueprint-checkbox",
        "as-photos-btn",
    ):
        assert token in body
        assert token in mobile_card
    assert "as-content-tab-btn" in body
    assert "as-content-tab-btn" in card_macros
    assert "render_as_content_tabs" in mobile_card
    assert "?open=erp-order" in mobile_card


def test_as_dashboard_script_runs_after_erp_shell_fragment_swap():
    """AS fragment 재삽입 뒤에도 날짜/일정찾기 이벤트가 다시 붙어야 한다."""
    src = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")

    assert "function initAsDashboard()" in src
    assert "document.readyState === 'loading'" in src
    assert "initAsDashboard();" in src
    assert "DOMContentLoaded', function" not in src
    assert "window.__fomsAsDashboardAbortController" in src
    assert "addAsDashboardListener(document.body, 'click', async function (e) {" in src
    assert "e.target.closest('.find-schedule-btn')" in src


def test_as_dashboard_construction_worker_contract_is_wired():
    src = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")

    assert "<th style=\"width: 140px;\">시공자</th>" in src
    assert "as-construction-worker-list" in src
    assert "as-construction-worker-row" in src
    assert "as-construction-worker-view" in src
    assert "as-construction-worker-input" in src
    assert "as-btn-add-construction-worker" in src
    assert "as-btn-remove-construction-worker" in src
    assert "data-field=\"construction_workers\"" in src
    assert "saveOrderFieldDirect(orderId, 'construction_workers', nextWorkers)" in src
    assert "현재 출고 대시보드 시공자:" in src
    assert "datalist-construction-workers" in src
    # PC 테이블: 주문→…→담당→시공자(6)→고객(7); 미결 하이라이트는 고객 열을 가리켜야 함
    assert "querySelector('td:nth-child(7)')" in src


def test_as_dashboard_add_listener_keeps_capture_when_abort_controller_active():
    """blur는 버블링되지 않음 — document 위임 시 capture:true 필수. options가 true일 때 signal만 붙이면 저장 안 됨."""
    src = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")

    assert "if (options === true || options === false)" in src
    assert "listenerOptions = { capture: options };" in src


def test_as_dashboard_construction_worker_css_uses_compact_edit_mode():
    src = (
        Path(__file__).resolve().parents[2] / "static/css/contexts/cs/as-dashboard-body.css"
    ).read_text(encoding="utf-8")

    assert ".as-construction-worker-row.has-value .as-construction-worker-view" in src
    assert ".as-construction-worker-row.editing .as-construction-worker-edit" in src
    assert ".as-construction-worker-action-stack" in src
    assert "flex-direction: column;" in src
    assert "min-height: 28px;" in src
    assert ".as-construction-worker-list:hover .as-construction-worker-actions-row" in src


def test_as_visit_date_visual_state_updates_optimistically():
    """AS 방문일 입력 즉시 방문일 cell 색상이 바뀌고 실패 시 저장값으로 복구해야 한다."""
    src = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")

    assert re.search(
        r"input\.style\.backgroundColor = '#fff3cd';\s+syncDateFieldVisuals\(orderId, fieldName, value\);",
        src,
    )
    assert "syncDateFieldInputs(orderId, fieldName, state.savedValue || '');" in src


def test_as_dashboard_renders_primary_and_secondary_tabs(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_as_admin(client)
    _create_as_order()

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-as-tab-target="1"' in body
    assert 'data-as-tab-target="2"' in body
    assert 'data-field-name="as_content"' in body
    assert 'data-field-name="as_content_2"' in body
    assert "2번 내용" in body


def test_as_dashboard_renders_construction_workers_column(client):
    _login_as_admin(client)
    _create_as_order(shipment_extra={"construction_workers": ["김시공", "박시공"]})

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert ">시공자<" in body
    assert 'class="as-construction-worker-list mb-0"' in body
    assert 'class="as-construction-worker-view">김시공</span>' in body
    assert 'class="as-construction-worker-view">박시공</span>' in body
    assert 'class="as-construction-worker-row has-value"' in body
    assert 'data-saved-value="김시공, 박시공"' in body
    assert 'class="form-control form-control-sm as-construction-worker-input"' in body
    assert 'value="김시공"' in body
    assert 'value="박시공"' in body


def test_as_pending_cleared_when_visit_then_received_cleared(client):
    """미결 해제는 접수일·방문일이 모두 소거된 뒤(ERP) 서버 저장 시에 적용된다."""
    _login_as_admin(client)
    as_day = date.today().strftime("%Y-%m-%d")
    order = _create_as_order(
        shipment_extra={"as_pending": True},
        schedule_extra={"as_visit": {"date": as_day}},
    )

    r1 = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "as_visit_date", "value": ""},
    )
    assert r1.status_code == 200
    assert r1.get_json()["as_pending"] is True

    r2 = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "as_received_date", "value": ""},
    )
    assert r2.status_code == 200
    assert r2.get_json()["as_pending"] is False

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved is not None
    assert (saved.structured_data.get("shipment") or {}).get("as_pending") is not True


def test_as_pending_cleared_when_received_then_visit_cleared(client):
    _login_as_admin(client)
    as_day = date.today().strftime("%Y-%m-%d")
    order = _create_as_order(
        shipment_extra={"as_pending": True},
        schedule_extra={"as_visit": {"date": as_day}},
    )

    r1 = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "as_received_date", "value": ""},
    )
    assert r1.status_code == 200
    assert r1.get_json()["as_pending"] is True

    r2 = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "as_visit_date", "value": ""},
    )
    assert r2.status_code == 200
    assert r2.get_json()["as_pending"] is False

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved is not None
    assert (saved.structured_data.get("shipment") or {}).get("as_pending") is not True


def test_update_order_field_saves_construction_workers(client):
    _login_as_admin(client)
    order = _create_as_order(shipment_extra={"construction_workers": ["기존시공"]})

    response = client.post(
        "/api/update_order_field",
        json={
            "order_id": order.id,
            "field_name": "construction_workers",
            "new_value": ["신규시공", "보조시공"],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["construction_workers"] == ["신규시공", "보조시공"]
    assert data["normalized_value"] == ["신규시공", "보조시공"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["construction_workers"] == ["신규시공", "보조시공"]


def test_update_order_field_saves_secondary_as_content(client):
    _login_as_admin(client)
    order = _create_as_order()

    response = client.post(
        "/api/update_order_field",
        json={
            "order_id": order.id,
            "field_name": "as_content_2",
            "new_value": "<div>두번째<br>AS 내용</div>",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "두번째" in data["normalized_value"]
    assert "AS 내용" in data["normalized_value"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["as_content_2"] == data["normalized_value"]


def test_as_dashboard_falls_back_to_order_notes_for_secondary_tab(client):
    _login_as_admin(client)
    _create_as_order(notes="아일랜드 서랍 마이다 불량\n조명 색상변경", as_content_2=None)

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "아일랜드 서랍 마이다 불량" in body
    assert "조명 색상변경" in body


def test_as_dashboard_does_not_restore_notes_after_secondary_tab_is_cleared(client):
    _login_as_admin(client)
    _create_as_order(notes="복구되면 안 되는 기존 메모", as_content_2="")

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "복구되면 안 되는 기존 메모" not in body


def test_as_dashboard_renders_tab_counts_and_incomplete_summary(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_as_admin(client)
    today = date.today().strftime("%Y-%m-%d")

    _create_as_order(
        customer_name="방문 확정",
        schedule_extra={"as_visit": {"date": today}},
    )
    _create_as_order(
        customer_name="미결",
        shipment_extra={"as_pending": True},
    )
    _create_as_order(customer_name="미정")
    _create_as_order(
        customer_name="영업택배",
        shipment_extra={"sales_delivery": True},
    )
    _create_as_order(
        customer_name="완료",
        status="AS_COMPLETED",
        as_completed_date=today,
    )

    response = client.get("/erp/as?tab=incomplete")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert re.search(r'data-as-tab-key="sales_delivery"[^>]*data-as-tab-count="1"', body)
    assert re.search(r'data-as-tab-key="incomplete"[^>]*data-as-tab-count="3"', body)
    assert re.search(r'data-as-tab-key="completed"[^>]*data-as-tab-count="1"', body)
    assert re.search(r'data-as-incomplete-summary="total"[^>]*data-count="3"', body)
    assert re.search(r'data-as-incomplete-summary="visit_confirmed"[^>]*data-count="1"', body)
    assert re.search(r'data-as-incomplete-summary="pending"[^>]*data-count="1"', body)
    assert re.search(r'data-as-incomplete-summary="unassigned"[^>]*data-count="1"', body)
