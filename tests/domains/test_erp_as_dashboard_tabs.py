import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _as_surface_src():
    """AS 대시보드 표면(프래그먼트 템플릿 + 추출된 static 모듈) 합본.

    Batch 5에서 inline JS가 static/js/cs/as-dashboard.js로 이동했다. 동작 계약 토큰은
    템플릿과 모듈 어느 쪽에 있든 'AS 표면'에 존재하면 충족이므로 둘을 합쳐 검사한다.
    """
    root = Path(__file__).resolve().parents[2]
    return (
        (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
        + "\n"
        + (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    )


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


def test_as_dashboard_scopes_by_as_axis_not_status():
    """AS-AXIS-01: 모집단·탭 술어가 status 가 아니라 AS 축 투영을 본다.

    status 는 overlay projection 이라 외부 write 한 번에 AS 목록이 통째로 사라졌다
    (2026-08-14 사고 55건). 이 계약이 그 술어로 되돌아가는 회귀를 잡는다.
    (구 계약: status IN ('AS','AS_RECEIVED','AS_COMPLETED') + status == 'AS' 리터럴 요구)
    """
    root = Path(__file__).resolve().parents[2]
    route_src = (root / "foms/web/cs/as_dashboard.py").read_text(encoding="utf-8")
    helper_src = (root / "foms/services/as_dashboard_helpers.py").read_text(encoding="utf-8")

    assert "erp_as_scope_condition()" in route_src
    assert "Order.as_axis_status.isnot(None)" in helper_src
    assert "Order.as_axis_status == 'RECEIVED'" in helper_src
    # 모집단 게이트가 status 로 되돌아가면 red (docstring 언급은 허용).
    assert "base_query.filter(Order.status.in_" not in route_src


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

    body = body + "\n" + _as_surface_src()

    for token in (
        "editable-date-as",
        "as-pending-btn",
        "as-blueprint-checkbox",
        "as-photos-btn",
    ):
        assert token in body
        assert token in mobile_card
    # T9: 내용 셀·모바일 카드는 타임라인 매크로가 담당한다(content-tabs 퇴역)
    assert "render_as_timeline_cell" in body
    assert "as-tl-item" in card_macros
    assert "render_as_timeline" in mobile_card
    assert "?open=erp-order" in mobile_card


def test_as_dashboard_script_runs_after_erp_shell_fragment_swap():
    """AS fragment 재삽입 뒤에도 날짜/일정찾기 이벤트가 다시 붙어야 한다."""
    template = (
        Path(__file__).resolve().parents[2] / "templates/cs/partials/as_dashboard_body.html"
    ).read_text(encoding="utf-8")
    # 프래그먼트는 외부 모듈을 src로 참조 → erp-shell activateScripts가 swap마다 재실행한다.
    assert "js/cs/as-dashboard.js" in template
    src = _as_surface_src()

    assert "function initAsDashboard()" in src
    # static defer 모듈: 풀페이지 로드는 DOMContentLoaded 대기(다른 defer 전역 준비), swap('complete')은 즉시 init
    assert "document.readyState === 'complete'" in src
    assert "initAsDashboard();" in src
    assert "DOMContentLoaded', initAsDashboard" in src
    assert "DOMContentLoaded', function" not in src
    assert "window.__fomsAsDashboardAbortController" in src
    assert "addAsDashboardListener(document.body, 'click', async function (e) {" in src
    assert "e.target.closest('.find-schedule-btn')" in src


def test_as_dashboard_construction_worker_contract_is_wired():
    src = _as_surface_src()

    # 열 폭은 2026-07-28 부터 colgroup+CSS 소유(구 <th style="width:"> 인라인 폐지).
    # 이 계약이 지키려던 것은 "시공자 열이 실재한다" 이므로 새 훅으로 갱신한다.
    assert '<th data-col-key="workers">시공자' in src
    assert '<col data-col-key="workers">' in src
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
    src = _as_surface_src()

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
    src = _as_surface_src()

    assert re.search(
        r"input\.style\.backgroundColor = '#fff3cd';\s+syncDateFieldVisuals\(orderId, fieldName, value\);",
        src,
    )
    assert "syncDateFieldInputs(orderId, fieldName, state.savedValue || '');" in src


def test_as_dashboard_renders_legacy_contents_in_timeline(client):
    """T9: 1/2 탭 에디터 퇴역. 두 탭의 기존 내용은 legacy 항목으로 타임라인에 보존된다.

    PC 셀은 앵커 1줄 요약(=legacy 첫 항목)만 실으므로 두 항목 모두 확인하려면
    전체 타임라인을 렌더하는 표면(레거시 모바일 카드·확장 fragment)이어야 한다.
    """
    _login_as_admin(client)
    _create_as_order()

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-as-tab-target="1"' not in body
    assert 'data-field-name="as_content"' not in body
    assert "1번 내용" in body
    assert "2번 내용" in body
    assert "as-tl-item--legacy" in body


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


def test_update_order_field_rejects_secondary_as_content(client):
    """구 2번 탭 저장 경로는 퇴역했다 — as_content_2 는 허용 필드가 아니다(T12).

    원래는 이 필드의 저장을 고정하던 테스트였다. 신규 AS 기록은 as_log(POST /as/log)
    한 곳으로만 들어오고, as_content/as_content_2 는 읽기 전용 legacy 로만 남는다.
    거부가 기존 값을 건드리지 않는 것까지 함께 고정한다.
    """
    _login_as_admin(client)
    order = _create_as_order()
    order_id = order.id

    response = client.post(
        "/api/update_order_field",
        json={
            "order_id": order_id,
            "field_name": "as_content_2",
            "new_value": "<div>두번째<br>AS 내용</div>",
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["as_content_2"] == "<div>2번 내용</div>"


def test_as_dashboard_notes_fallback_retired_with_content_tabs(client):
    """주문 비고(notes) 를 2번 탭에 대신 띄우던 화면 폴백은 타임라인 전환과 함께 사라진다.

    타임라인은 AS 도메인 기록(as_log·as_content legacy)만 싣는다 — 비고를 legacy 앵커로
    끌어오면 '이전 기록(탭2)'로 둔갑해 없던 AS 기록이 생긴다(T8 결정,
    test_dashboard_legacy_anchor_ignores_notes_fallback 이 고정).

    T10: 비고 자체는 사라지지 않는다. 목록에는 안 싣고, 확장 fragment·모바일 상세에서
    별도 '비고' 블록으로 읽는다(test_timeline_fragment_shows_order_notes_block).
    """
    _login_as_admin(client)
    _create_as_order(notes="아일랜드 서랍 마이다 불량\n조명 색상변경", as_content_2=None)

    response = client.get("/erp/as")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "아일랜드 서랍 마이다 불량" not in body
    assert "1번 내용" in body  # AS 기록 자체는 타임라인에 그대로


def test_as_dashboard_does_not_restore_notes_after_secondary_tab_is_cleared(client):
    """빈 문자열로 지운 2번 탭이 비고로 되살아나지 않는다(목록 표면 기준)."""
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


def test_dashboard_rows_carry_as_cycle_projection(client):
    """행 보강이 AS 건(cycle) 표식 5키를 싣는다 — 투영 SSOT = orders/as_cycle_view.

    완료된 1번째 건 + 열린 2번째 건(재발)을 심고, 행이 건 번호·건 상태·재발·이력불명·
    지난 건 요약을 그대로 들고 나오는지 본다(PC 표·모바일 카드가 같은 행을 쓴다).
    as_cycle_status 는 완료일 삭제 팝업 3케이스 분기의 근거라 반드시 실려야 한다.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from foms.services.as_dashboard_display import apply_as_dashboard_row_display_fields

    order = _create_as_order(customer_name="AS 건 투영 고객")
    sd = dict(order.structured_data or {})
    sd["as_lifecycle"] = {
        "current_cycle_id": "cyc-2",
        "cycles": [
            {
                "cycle_id": "cyc-1",
                "received_date": "2026-05-01",
                "completed_date": "2026-05-09",
                "billing_snapshot": {"type": "paid", "confirmed": True, "amount": 30000},
                # cycle transition 의 to 는 AS 축 값(RECEIVED/COMPLETED) — status_constants 의
                # legacy AS_* projection 문자열이 아니다(state_axes 규약).
                "transitions": [{"seq": 1, "to": "COMPLETED"}],
            },
            {
                "cycle_id": "cyc-2",
                "received_date": "2026-08-20",
                "recurrence": True,
                "transitions": [{"seq": 1, "to": "RECEIVED"}],
            },
        ],
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id

    db_session.expire_all()
    row = db_session.get(Order, order_id)
    apply_as_dashboard_row_display_fields([row], db_session, mobile_v2_active=False)

    assert row.as_cycle_no == 2
    assert row.as_cycle_status == "RECEIVED"
    assert row.as_recurrence is True
    assert row.as_history_unknown is False
    prev = row.as_prev_cycle
    assert prev["ordinal"] == 1 and prev["completed_date"] == "2026-05-09"
    assert prev["billing_text"].startswith("유상 확정")
