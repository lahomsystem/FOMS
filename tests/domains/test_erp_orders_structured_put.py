import copy
import io
from pathlib import Path

from werkzeug.security import generate_password_hash

from foms.api import erp_orders_structured
from db import db_session
from models import ChannelDeliveryLog, Order, OrderAttachment, User


def _login_as_admin(client, username="erp-structured-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Structured Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _structured_payload(address: str) -> dict:
    return {
        "workflow": {"stage": "RECEIVED"},
        "shipment": {},
        "parties": {
            "customer": {
                "name": "홍길동",
                "phone": "010-1234-5678",
            }
        },
        "items": [{"product_name": "붙박이장"}],
        "site": {
            "address_full": address,
            "address_main": address,
            "address_detail": "",
        },
    }


def _create_order(*, address="서울 테헤란로 123", structured_data=None) -> Order:
    order = Order(
        received_date="2026-04-11",
        customer_name="홍길동",
        phone="010-1234-5678",
        address=address,
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else _structured_payload(address),
        lat=37.5,
        lng=127.0,
        geocode_status="success",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_structured_put_skips_channel_side_effects_when_structured_data_missing(client, monkeypatch):
    _login_as_admin(client)
    order = _create_order()
    order_id = order.id
    original_structured = order.structured_data

    mark_calls = []
    geocode_calls = []

    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_geocode_order_address",
        lambda order_id: geocode_calls.append(order_id),
    )

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"notes": "structured data 없이 메모만 수정"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert mark_calls == []
    assert geocode_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.notes == "structured data 없이 메모만 수정"
    assert saved_order.structured_data == original_structured


def test_structured_put_clears_order_notes_when_notes_empty_string(client, monkeypatch):
    """ERP 비고 필드: 빈 문자열을 보내면 order.notes가 None으로 비워져야 한다 (JSON에서 키 생략 금지)."""
    _login_as_admin(client, username="erp-notes-clear")
    order = _create_order()
    order_id = order.id
    order.notes = "기존 비고"
    db_session.commit()

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    sd = copy.deepcopy(order.structured_data)
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": sd,
            "structured_schema_version": 1,
            "notes": "",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.notes is None


def test_structured_get_put_round_trips_regional_and_self_measurement_flags(client, monkeypatch):
    """ERP Order 저장은 지방주문/자가실측 플래그를 대시보드 필터 컬럼에 반영해야 한다."""
    _login_as_admin(client, username="erp-regional-flags")
    order = _create_order()
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    sd = copy.deepcopy(order.structured_data)
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": sd,
            "structured_schema_version": 1,
            "is_regional": True,
            "is_self_measurement": True,
            "construction_type": "협력사 시공",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.is_regional is True
    assert saved_order.is_self_measurement is True
    assert saved_order.construction_type == "협력사 시공"

    get_response = client.get(f"/api/orders/{order_id}/structured")
    assert get_response.status_code == 200
    payload = get_response.get_json()
    assert payload["is_regional"] is True
    assert payload["is_self_measurement"] is True
    assert payload["construction_type"] == "협력사 시공"

    from foms.web.orders.edit import _build_erp_order_bootstrap

    bootstrap = _build_erp_order_bootstrap(saved_order)
    assert bootstrap["is_regional"] is True
    assert bootstrap["is_self_measurement"] is True
    assert bootstrap["construction_type"] == "협력사 시공"

    regional_dashboard = client.get(
        "/regional_dashboard", query_string={"search_query": str(order_id)}
    )
    assert regional_dashboard.status_code == 200
    regional_body = regional_dashboard.get_data(as_text=True)
    assert "홍길동" in regional_body
    assert 'data-construction-type="협력사 시공"' in regional_body

    self_dashboard = client.get(
        "/self_measurement_dashboard", query_string={"search_query": str(order_id)}
    )
    assert self_dashboard.status_code == 200
    assert "홍길동" in self_dashboard.get_data(as_text=True)


def test_structured_put_syncs_erp_dates_to_legacy_mirrors(client, monkeypatch):
    """Full ERP Order save must keep regional/legacy date columns in sync."""
    _login_as_admin(client, username="erp-structured-date-sync")
    order = _create_order(
        structured_data={
            **_structured_payload("서울 테헤란로 123"),
            "schedule": {
                "measurement": {"date": "2026-07-01"},
                "construction": {"date": "2026-07-02"},
            },
        }
    )
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    sd = copy.deepcopy(order.structured_data)
    sd["schedule"]["measurement"]["date"] = "2026-07-13"
    sd["schedule"]["construction"]["date"] = "2026-07-21"

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.erp_measurement_date == "2026-07-13"
    assert saved_order.erp_construction_date == "2026-07-21"
    assert saved_order.measurement_date == "2026-07-13"
    assert saved_order.scheduled_date == "2026-07-21"


def test_structured_put_requires_construction_type_for_regional_order(client, monkeypatch):
    """지방주문 저장은 하우드/협력사 구분 없이는 대시보드 매칭을 만들 수 없다."""
    _login_as_admin(client, username="erp-regional-type-required")
    order = _create_order()

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)

    response = client.put(
        f"/api/orders/{order.id}/structured",
        json={
            "structured_data": copy.deepcopy(order.structured_data),
            "structured_schema_version": 1,
            "is_regional": True,
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "지방주문 구분" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.is_regional is False
    assert saved_order.construction_type is None


def test_structured_put_rejects_partial_clear_for_existing_regional_order(client):
    """기존 지방주문은 partial PUT으로 시공 구분을 빈 값으로 지울 수 없다."""
    _login_as_admin(client, username="erp-regional-type-partial-clear")
    order = _create_order()
    order.is_regional = True
    order.construction_type = "하우드 시공"
    db_session.commit()
    order_id = order.id

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"construction_type": ""},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "지방주문 구분" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.is_regional is True
    assert saved_order.construction_type == "하우드 시공"


def test_structured_put_rejects_unknown_regional_construction_type(client):
    """ERP PUT도 대시보드 필터가 모르는 시공 구분 값을 거부한다."""
    _login_as_admin(client, username="erp-regional-type-invalid")
    order = _create_order()

    response = client.put(
        f"/api/orders/{order.id}/structured",
        json={
            "structured_data": copy.deepcopy(order.structured_data),
            "structured_schema_version": 1,
            "is_regional": True,
            "construction_type": "기타",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "하우드 또는 협력사" in payload["message"]


def test_structured_put_allows_construction_type_clear_for_non_regional_order(client):
    """비지방 주문은 stale 시공 구분 값을 partial PUT으로 정리할 수 있다."""
    _login_as_admin(client, username="erp-non-regional-type-clear")
    order = _create_order()
    order.is_regional = False
    order.construction_type = "하우드 시공"
    db_session.commit()
    order_id = order.id

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"construction_type": ""},
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.is_regional is False
    assert saved_order.construction_type is None


def test_structured_put_rejects_construction_type_for_non_regional_order(client):
    """비지방 주문은 지방 대시보드용 시공 구분 값을 새로 저장할 수 없다."""
    _login_as_admin(client, username="erp-non-regional-type-set")
    order = _create_order()

    response = client.put(
        f"/api/orders/{order.id}/structured",
        json={"construction_type": "하우드 시공"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "비지방 주문" in payload["message"]


def test_structured_put_preserves_shipment_construction_workers_when_missing(client, monkeypatch):
    _login_as_admin(client, username="erp-workers-preserve")
    original_sd = _structured_payload("서울 테헤란로 123")
    original_sd["shipment"] = {
        "construction_workers": ["김시공", "박시공"],
        "as_content": "AS 내용",
    }
    order = _create_order(structured_data=original_sd)
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)

    next_sd = _structured_payload("서울 테헤란로 123")
    next_sd.pop("shipment")
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": next_sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["construction_workers"] == ["김시공", "박시공"]


def test_structured_put_preserves_drawing_operational_state_from_form_payload(client, monkeypatch):
    """ERP 주문 폼 저장은 전용 도면 API가 관리하는 이력/담당자/파일 상태를 지우면 안 된다."""
    _login_as_admin(client, username="erp-drawing-state-preserve")
    original_sd = _structured_payload("서울 테헤란로 123")
    original_sd.update(
        {
            "workflow": {
                "stage": "DRAWING",
                "history": [
                    {
                        "stage": "DRAWING",
                        "updated_at": "2026-06-22T09:00:00",
                        "updated_by": "도면팀",
                        "note": "도면 담당자 지정",
                    }
                ],
                "stage_updated_at": "2026-06-22T09:00:00",
                "stage_updated_by": "도면팀",
            },
            "assignments": {
                "drawing_assignee_user_ids": [41],
                "owner_team": "DRAWING",
            },
            "drawing_assignees": [{"id": 41, "name": "도면담당", "team": "DRAWING"}],
            "shipment": {
                "drawing_managers": ["도면담당"],
                "construction_workers": ["시공담당"],
                "as_content": "보존할 AS 내용",
            },
            "drawing_status": "RETURNED",
            "drawing_transferred": True,
            "drawing_current_files": [
                {
                    "key": "orders/1/drawing/revised.png",
                    "filename": "revised.png",
                    "view_url": "/api/files/view/orders/1/drawing/revised.png",
                }
            ],
            "drawing_transfer_history": [
                {
                    "action": "REQUEST_REVISION",
                    "at": "2026-06-22 09:10:00",
                    "by_user_name": "영업담당",
                    "note": "손잡이 위치 수정",
                }
            ],
            "last_drawing_transfer": {
                "action": "TRANSFER",
                "transferred_at": "2026-06-22 09:20:00",
                "by_user_name": "도면담당",
            },
        }
    )
    order = _create_order(structured_data=original_sd)
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    form_sd = _structured_payload("서울 테헤란로 123")
    form_sd["workflow"] = {"stage": "DRAWING"}
    form_sd["shipment"] = {}
    form_sd.pop("assignments", None)

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": form_sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    saved_sd = saved_order.structured_data
    assert saved_sd["workflow"]["history"] == original_sd["workflow"]["history"]
    assert saved_sd["workflow"]["stage_updated_at"] == "2026-06-22T09:00:00"
    assert saved_sd["assignments"]["drawing_assignee_user_ids"] == [41]
    assert saved_sd["drawing_assignees"] == original_sd["drawing_assignees"]
    assert saved_sd["shipment"]["drawing_managers"] == ["도면담당"]
    assert saved_sd["shipment"]["as_content"] == "보존할 AS 내용"
    assert saved_sd["drawing_status"] == "RETURNED"
    assert saved_sd["drawing_current_files"] == original_sd["drawing_current_files"]
    assert saved_sd["drawing_transfer_history"] == original_sd["drawing_transfer_history"]
    assert saved_sd["last_drawing_transfer"] == original_sd["last_drawing_transfer"]


def test_structured_put_preserves_channeltalk_push_history_from_form_payload(client, monkeypatch):
    """ERP 주문 폼 저장은 채널톡 수동 푸시 이력을 지우면 안 된다."""
    _login_as_admin(client, username="erp-channel-push-preserve")
    push_history = {
        "pushed": True,
        "message_id": "msg-keep-1",
        "change_log": [{"note": "손잡이 정정", "message_id": "msg-keep-1"}],
    }
    original_sd = _structured_payload("서울 강남구")
    original_sd["channeltalk_push"] = push_history
    original_sd["channeltalk_push_drawing"] = {"pushed": True, "message_id": "draw-1"}
    original_sd["channeltalk_push_estimate"] = {"pushed": True, "message_id": "est-1"}
    order = _create_order(structured_data=original_sd)
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    form_sd = _structured_payload("서울 강남구")

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": form_sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200

    db_session.expire_all()
    saved_sd = db_session.get(Order, order_id).structured_data
    assert saved_sd["channeltalk_push"] == push_history
    assert saved_sd["channeltalk_push_drawing"] == {"pushed": True, "message_id": "draw-1"}
    assert saved_sd["channeltalk_push_estimate"] == {"pushed": True, "message_id": "est-1"}


def test_erp_order_construction_worker_input_contract_is_wired():
    root = Path(__file__).resolve().parents[2]
    tpl = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    js = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")

    assert 'id="erp-construction-workers"' in tpl
    assert "erpNormalizeConstructionWorkers" in js
    assert "structured.shipment.construction_workers" in js
    assert "erpConfirmConstructionWorkerOverwrite" in js
    assert "현재 출고 대시보드 시공자:" in js


def test_erp_order_party_workflow_notes_layout_is_two_rows():
    root = Path(__file__).resolve().parents[2]
    tpl = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    mobile_tpl = (
        root / "templates/orders/partials/erp_order_tab_mobile.html"
    ).read_text(encoding="utf-8")

    orderer_idx = tpl.index('id="erp-orderer-select"')
    manager_idx = tpl.index('id="erp-manager"')
    construction_idx = tpl.index('id="erp-construction-workers"')
    stage_idx = tpl.index('id="erp-workflow-stage"')
    notes_idx = tpl.index('id="erp-notes"')

    assert orderer_idx < manager_idx < construction_idx < stage_idx < notes_idx
    assert '<div class="col-md-4">\n                            <label class="form-label mb-1">담당자</label>' in tpl
    assert '<div class="col-md-4">\n                            <label class="form-label mb-1">시공 담당자</label>' in tpl
    assert 'for="erp-workflow-stage">본공정 단계</label>' in tpl
    assert 'for="erp-workflow-stage">본공정 단계</label>' in mobile_tpl
    assert 'data-erp-as-status="{{ order.status }}">AS: {{ erp_as_status_label }}' in tpl
    assert 'data-erp-as-status="{{ order.status }}">AS: {{ erp_as_status_label }}' in mobile_tpl
    assert "data-erp-as-reregister-open" in tpl
    assert "data-erp-as-reregister-open" in mobile_tpl
    assert '<div class="col-md-8">\n                            <label class="form-label mb-1">비고</label>' in tpl


def test_erp_order_edit_displays_main_stage_and_as_status_separately(client):
    _login_as_admin(client, username="erp-as-stage-display-admin")
    structured_data = _structured_payload("서울 테헤란로 123")
    structured_data["workflow"]["stage"] = "MEASURE"
    order = _create_order(structured_data=structured_data)
    order.status = "AS_RECEIVED"
    order_id = order.id
    db_session.commit()

    response = client.get(f"/edit/{order_id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "본공정 단계" in body
    assert 'data-erp-as-status="AS_RECEIVED"' in body
    assert "AS: 접수" in body
    assert "data-erp-as-reregister-open" in body

    completed = db_session.get(Order, order_id)
    completed.status = "AS_COMPLETED"
    db_session.commit()

    completed_response = client.get(f"/edit/{order_id}")
    completed_body = completed_response.get_data(as_text=True)
    assert 'data-erp-as-status="AS_COMPLETED"' in completed_body
    assert "AS: 완료" in completed_body
    assert "data-erp-as-reregister-open" not in completed_body


def test_structured_put_rejects_address_clear_before_geocode_reset(client, monkeypatch):
    _login_as_admin(client, username="erp-structured-address-clear")
    order = _create_order()
    order_id = order.id

    geocode_calls = []
    push_calls = []
    reset_calls = []

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *args, **kwargs: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *args, **kwargs: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *args, **kwargs: None)

    original_reset = erp_orders_structured.reset_order_geocode_on_address_change

    def _capture_reset(order_obj, new_address):
        reset_calls.append(new_address)
        return original_reset(order_obj, new_address)

    monkeypatch.setattr(erp_orders_structured, "reset_order_geocode_on_address_change", _capture_reset)
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_geocode_order_address",
        lambda order_id: geocode_calls.append(order_id),
    )

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": _structured_payload(""),
            "structured_schema_version": 1,
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "주소" in data["message"]
    assert reset_calls == []
    assert geocode_calls == []
    assert push_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.address == "서울 테헤란로 123"
    assert saved_order.lat == 37.5
    assert saved_order.lng == 127.0
    assert saved_order.geocode_status == "success"
    assert (saved_order.structured_data or {}).get("site", {}).get("address_full") == "서울 테헤란로 123"


def test_structured_put_never_enqueues_channel_auto_push(client, monkeypatch):
    """ERP structured 저장은 자동 ChannelTalk 푸시 없음 (수동 푸쉬만)."""
    _login_as_admin(client, username="erp-structured-no-channel")
    order = _create_order()
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)

    sd = copy.deepcopy(order.structured_data)
    sd.setdefault("workflow", {})["stage"] = "MEASURE"
    sd.setdefault("site", {})["address_full"] = "부산 해운대구 테스트로 99"
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200
    assert (
        db_session.query(ChannelDeliveryLog)
        .filter(ChannelDeliveryLog.order_id == order_id)
        .count()
        == 0
    )


def test_erp_draft_create_is_hidden_from_active_orders_and_reused(client):
    _login_as_admin(client, username="erp-draft-hidden")

    response = client.post("/api/orders/erp/draft")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["reused"] is False

    order_id = data["order_id"]
    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft is not None
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    assert draft not in db_session.query(Order).filter(Order.active_filter()).all()

    reused = client.post("/api/orders/erp/draft")

    assert reused.status_code == 200
    reused_data = reused.get_json()
    assert reused_data["success"] is True
    assert reused_data["reused"] is True
    assert reused_data["order_id"] == order_id


def test_erp_draft_create_reuses_same_browser_token_without_session_key(client):
    """Concurrent draft requests can arrive before the session cookie receives the draft id."""
    _login_as_admin(client, username="erp-draft-token-reuse")
    draft_token = "draft-token-same-page"

    response = client.post("/api/orders/erp/draft", json={"draft_token": draft_token})

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    order_id = data["order_id"]

    with client.session_transaction() as sess:
        sess.pop("erp_draft_order_id", None)

    reused = client.post("/api/orders/erp/draft", json={"draft_token": draft_token})

    assert reused.status_code == 200
    reused_data = reused.get_json()
    assert reused_data["success"] is True
    assert reused_data["reused"] is True
    assert reused_data["order_id"] == order_id

    db_session.expire_all()
    token_drafts = []
    for order in db_session.query(Order).filter(Order.status == "DRAFT").all():
        structured_data = order.structured_data if isinstance(order.structured_data, dict) else {}
        meta = structured_data.get("meta") if isinstance(structured_data.get("meta"), dict) else {}
        if meta.get("draft_token") == draft_token:
            token_drafts.append(order)
    assert [order.id for order in token_drafts] == [order_id]


def test_erp_draft_status_is_hidden_even_without_meta_marker(client):
    _login_as_admin(client, username="erp-draft-status-hidden")
    structured = _structured_payload("서울 테헤란로 123")
    structured["meta"] = {"draft": False}
    order = _create_order(structured_data=structured)
    order.status = "DRAFT"
    db_session.commit()

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved in db_session.query(Order).filter(Order.erp_draft_filter()).all()
    assert saved not in db_session.query(Order).filter(Order.active_filter()).all()


def test_structured_put_rejects_incomplete_draft_and_keeps_it_hidden(client):
    _login_as_admin(client, username="erp-draft-incomplete")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": {
                "workflow": {"stage": "RECEIVED"},
                "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
                "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123"},
                "items": [{"product_name": ""}],
            },
            "structured_schema_version": 1,
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "제품명" in data["message"]

    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft is not None
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    assert draft not in db_session.query(Order).filter(Order.active_filter()).all()


def test_structured_put_finalizes_draft_without_incoming_meta(client, monkeypatch):
    _login_as_admin(client, username="erp-draft-finalize")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": _structured_payload("서울 테헤란로 123"),
            "structured_schema_version": 1,
            "received_date": "2026-04-27",
            "received_time": "09:30",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["draft_cleared"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved is not None
    assert saved.status == "RECEIVED"
    assert saved.customer_name == "홍길동"
    assert saved.phone == "010-1234-5678"
    assert saved.address == "서울 테헤란로 123"
    assert saved.product == "붙박이장"
    assert (saved.structured_data or {}).get("meta", {}).get("draft") is False
    assert saved in db_session.query(Order).filter(Order.active_filter()).all()

    with client.session_transaction() as sess:
        assert "erp_draft_order_id" not in sess


def test_payment_confirm_rejects_unfinalized_draft(client):
    _login_as_admin(client, username="erp-draft-payment")
    created = client.post("/api/orders/erp/draft").get_json()

    response = client.post(
        f"/api/orders/{created['order_id']}/payment-confirm",
        json={"type": "deposit", "confirmed": True},
    )

    assert response.status_code == 404


def test_erp_draft_accepts_legacy_attachment_upload_before_final_save(client, monkeypatch):
    _login_as_admin(client, username="erp-draft-legacy-attachment")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    class DummyStorage:
        def upload_file(self, file_obj, filename, folder):
            return {"success": True, "key": f"{folder}/{filename}"}

        def get_file_type(self, filename):
            return "image"

    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())

    response = client.post(
        f"/api/orders/{order_id}/attachments",
        data={
            "category": "measurement",
            "file": (io.BytesIO(b"fake image"), "draft-photo.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    attachment = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id)
        .one()
    )
    assert attachment.filename == "draft-photo.jpg"
    assert attachment.category == "measurement"


def test_erp_draft_accepts_direct_attachment_complete_before_final_save(client, monkeypatch):
    _login_as_admin(client, username="erp-draft-direct-attachment")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    class DummyStorage:
        storage_type = "local"

        def object_exists(self, key):
            return True

        def get_file_type(self, filename):
            return "image"

    monkeypatch.setattr("foms.api.files.direct_upload.get_storage", lambda: DummyStorage())

    response = client.post(
        f"/api/orders/{order_id}/attachments/complete",
        json={
            "key": f"orders/{order_id}/measurement/draft-direct.jpg",
            "filename": "draft-direct.jpg",
            "category": "measurement",
            "item_index": 0,
            "size": 12,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    attachment = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order_id)
        .one()
    )
    assert attachment.filename == "draft-direct.jpg"
    assert attachment.item_index == 0


def test_direct_upload_batch_echoes_client_id_and_keeps_duplicate_filenames_distinct(client, monkeypatch):
    """Batch presigned sessions use client_id for frontend matching, not filename."""
    _login_as_admin(client, username="erp-direct-batch-client-id")

    class DummyStorage:
        storage_type = "r2"

        def __init__(self):
            self.count = 0

        def generate_direct_upload_key(self, filename, folder):
            self.count += 1
            return f"{folder}/{self.count}_{filename}"

        def _get_content_type(self, filename):
            return "image/jpeg"

        def generate_presigned_put_url(self, key, ct, expires_in=900):
            return f"https://r2.example.test/{key}?ct={ct}&ttl={expires_in}"

    dummy = DummyStorage()
    monkeypatch.setattr("foms.api.files.direct_upload.get_storage", lambda: dummy)

    response = client.post(
        "/api/upload/session/batch",
        json={
            "folder": "orders/123/attachments",
            "category": "measurement",
            "files": [
                {"client_id": "local-a", "filename": "same.jpg", "size": 1000},
                {"client_id": "local-b", "filename": "same.jpg", "size": 1000},
                {"client_id": "x" * 129, "filename": "toolong.jpg", "size": 1000},
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    sessions = data["sessions"]
    assert len(sessions) == 3
    assert sessions[0]["client_id"] == "local-a"
    assert sessions[1]["client_id"] == "local-b"
    assert "client_id" not in sessions[2]
    assert sessions[0]["key"] != sessions[1]["key"]


def test_structured_put_blocks_accidental_stage_regression_drawing_to_measure(client, monkeypatch):
    """stale form stage MEASURE must not overwrite server DRAWING (도면→실측 사고)."""
    _login_as_admin(client, username="erp-stage-regress-guard")
    original_sd = _structured_payload("서울 테헤란로 123")
    original_sd["workflow"] = {"stage": "DRAWING", "stage_updated_at": "2026-07-15T10:00:00"}
    original_sd["drawing"] = {"status": "IN_PROGRESS"}
    original_sd["drawing_transfer_history"] = [
        {"action": "ERP_ORDER_CHANGED", "note": "치수 변경", "at": "2026-07-15 10:01:00"}
    ]
    order = _create_order(structured_data=original_sd)
    order.status = "DRAWING"
    order.erp_stage_code = "DRAWING"
    db_session.commit()
    order_id = order.id

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_emit_drawing_order_change_if_needed", lambda *a, **k: (None, False))

    form_sd = _structured_payload("서울 테헤란로 123")
    form_sd["workflow"] = {"stage": "MEASURE"}
    form_sd["items"] = [{"product_name": "붙박이장", "width": "1300"}]
    form_sd["drawing_transfer_history"] = []  # stale empty — must not wipe

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": form_sd, "structured_schema_version": 1},
    )
    assert response.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    saved_sd = saved.structured_data or {}
    assert (saved_sd.get("workflow") or {}).get("stage") == "DRAWING"
    hist = saved_sd.get("drawing_transfer_history") or []
    assert len(hist) >= 1
    assert hist[0].get("action") == "ERP_ORDER_CHANGED"


def _mute_structured_side_effects(monkeypatch):
    """PUT 낙관 잠금 테스트에서 저장 부수효과(이벤트/알림/지오코딩)를 제거한다."""
    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)


def test_structured_put_stale_if_match_returns_409_not_500(client, monkeypatch):
    """stale If-Match 는 500(generic 예외)이 아니라 409 VERSION_CONFLICT + 서버 현재 버전."""
    _login_as_admin(client, username="erp-ifmatch-conflict")
    _mute_structured_side_effects(monkeypatch)
    order = _create_order()
    order_id = order.id
    sd = copy.deepcopy(order.structured_data)

    first = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert first.status_code == 200
    current_version = first.get_json()["mutation_version"]
    assert isinstance(current_version, int)

    stale = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
        headers={"If-Match": str(current_version - 1)},
    )

    assert stale.status_code == 409, stale.get_data(as_text=True)
    payload = stale.get_json()
    assert payload["success"] is False
    assert payload["error"] == "VERSION_CONFLICT"
    assert payload["current"]["mutation_version"] == current_version

    db_session.expire_all()
    assert db_session.get(Order, order_id).mutation_version == current_version


def test_structured_put_matching_if_match_bumps_mutation_version(client, monkeypatch):
    """올바른 If-Match 는 200 + 요청한 값보다 큰 mutation_version 을 돌려준다."""
    _login_as_admin(client, username="erp-ifmatch-ok")
    _mute_structured_side_effects(monkeypatch)
    order = _create_order()
    order_id = order.id
    sd = copy.deepcopy(order.structured_data)

    expected = client.get(f"/api/orders/{order_id}/structured").get_json()["mutation_version"]
    assert isinstance(expected, int)

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
        headers={"If-Match": str(expected)},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["mutation_version"] > expected


def test_structured_put_without_if_match_still_saves(client, monkeypatch):
    """하위 호환: If-Match 미전송 저장은 그대로 200(전역 강제는 REV_IF_MATCH_ENFORCED 몫)."""
    _login_as_admin(client, username="erp-ifmatch-absent")
    _mute_structured_side_effects(monkeypatch)
    order = _create_order()
    order_id = order.id

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": copy.deepcopy(order.structured_data),
            "structured_schema_version": 1,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_erp_order_bootstrap_exposes_mutation_version(client):
    """bootstrap payload 는 GET /structured 와 동일하게 If-Match 토큰을 포함해야 한다."""
    from foms.web.orders.edit import _build_erp_order_bootstrap

    _login_as_admin(client, username="erp-bootstrap-ifmatch")
    order = _create_order()

    bootstrap = _build_erp_order_bootstrap(order)
    assert bootstrap["mutation_version"] == order.mutation_version
    assert isinstance(bootstrap["mutation_version"], int)


def test_pin_form_stage_to_server_unit():
    """STATE-FORM-01: 폼 payload 의 stage 는 방향 무관 서버 단계로 고정된다(전이 0)."""
    from foms.api.erp_orders_structured import _pin_form_stage_to_server

    old = {"workflow": {"stage": "DRAWING"}}

    # 역행 시도 → 서버 단계 유지.
    regress = {"workflow": {"stage": "MEASURE"}}
    _pin_form_stage_to_server(old, regress)
    assert regress["workflow"]["stage"] == "DRAWING"

    # 인접 전진 시도도 폼으로는 불가 → 서버 단계 유지(암묵 전이 금지).
    forward = {"workflow": {"stage": "CONFIRM"}}
    _pin_form_stage_to_server(old, forward)
    assert forward["workflow"]["stage"] == "DRAWING"

    # 건너뛰기 시도 → 서버 단계 유지.
    skip = {"workflow": {"stage": "PRODUCTION"}}
    _pin_form_stage_to_server({"workflow": {"stage": "MEASURE"}}, skip)
    assert skip["workflow"]["stage"] == "MEASURE"

    # workflow 누락 payload 에도 서버 단계를 심는다.
    empty: dict = {}
    _pin_form_stage_to_server(old, empty)
    assert empty["workflow"]["stage"] == "DRAWING"


# --------------------------------------------------------------------------- #
# 신원 flat 컬럼 정합 (2026-09-02)
#
# 이 경로는 sync_erp_flat_columns 만 불렀는데 그 함수는 erp_phone_digits 만 쓴다.
# flat phone 을 쓰는 유일한 구문이 draft 승격 분기 안에 있어 **기존 주문 저장에서는
# 통째로 스킵**됐고, 전화를 바꾸면 digits 만 새 값이 되고 phone 컬럼은 옛 값으로 남았다
# (운영 활성 주문 130건). 네이버 자동 매칭이 그 두 컬럼을 축으로 쓰다 사고가 났다 —
# docs/incidents/2026-09-01-naver-triage-auto-match-miss.md
# --------------------------------------------------------------------------- #
def test_structured_put_syncs_flat_phone_column_for_existing_order(client):
    """전화를 바꾸면 flat ``phone`` 컬럼도 함께 움직인다(승격 주문이 아니어도)."""
    _login_as_admin(client, username="erp-flat-phone")
    order = _create_order()
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["customer"]["phone"] = "010-9621-5670"
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.phone == "010-9621-5670"
    assert saved.erp_phone_digits == "01096215670"


def test_structured_put_syncs_flat_customer_name_column(client):
    """고객명도 같은 축이다 — 자동 매칭의 이름 축은 이 컬럼을 정확일치로 본다."""
    _login_as_admin(client, username="erp-flat-name")
    order = _create_order()
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["customer"]["name"] = "문기범"
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    db_session.expire_all()
    assert db_session.get(Order, order_id).customer_name == "문기범"


def test_structured_put_rejects_empty_identity_and_leaves_flat_columns_intact(client):
    """이름·전화를 빈 값으로 보내는 저장은 애초에 막힌다 — flat 도 그대로 남는다.

    (flat 동기가 정본을 따라가게 됐으므로, 빈 값이 통과했다면 컬럼까지 지워졌을 것이다.
    막는 자리는 저장 검증이고, 이 테스트는 그 순서를 못박는다.)
    """
    _login_as_admin(client, username="erp-flat-empty")
    order = _create_order()
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["customer"]["phone"] = ""
    sd["parties"]["customer"]["name"] = ""
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 400, response.get_data(as_text=True)[:400]
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.phone == "010-1234-5678"
    assert saved.customer_name == "홍길동"


def test_identity_flat_sync_helper_keeps_existing_value_when_structured_lacks_it():
    """헬퍼 단위 계약: 정본에 값이 없으면 flat 을 **건드리지 않는다**."""
    from foms.api.erp_orders_structured import _sync_identity_flat_columns

    order = Order(customer_name="홍길동", phone="010-1234-5678")
    _sync_identity_flat_columns(order, {"parties": {"customer": {}}})
    assert (order.customer_name, order.phone) == ("홍길동", "010-1234-5678")

    _sync_identity_flat_columns(order, {})
    assert (order.customer_name, order.phone) == ("홍길동", "010-1234-5678")

    # 자리표시자 전화는 실제 값을 덮지 않는다. 문자열 한 값만 막으면 변형이 통과한다 —
    # 운영 주문 #4648 의 정본에 실제로 ``000000000`` 이 들어가 있었다.
    for placeholder in ("000-0000-0000", "000000000", "0000000000000", "010-", ""):
        _sync_identity_flat_columns(
            order, {"parties": {"customer": {"phone": placeholder}}}
        )
        assert order.phone == "010-1234-5678", placeholder

    # 실제 번호는 통과해야 한다(시내번호·안심번호 포함).
    for real in ("02-123-4567", "0502-2681-1527", "010-9621-5670"):
        _sync_identity_flat_columns(order, {"parties": {"customer": {"phone": real}}})
        assert order.phone == real
