"""지방 직접 완료: 화면·API·최종 상태·감사 및 일반 주문과의 경계."""
import uuid

import pytest

from db import db_session
from models import Order, OrderConstructionAttempt, OrderEvent, OrderMutationReceipt, SecurityLog
from tests.domains.test_cs_complete_from_measure_board import (
    _cs_quest, _cta, _login, _make_order, _make_user,
)


def _regional(stage: str = "PRODUCTION", *, sd: dict | None = None) -> Order:
    """설치 예정 지방 ERP 주문을 만든다. 반환값은 저장된 주문이다."""
    order = _make_order(stage, status="SCHEDULED", structured_data=sd or _cs_quest(False))
    order.is_regional = True
    db_session.commit()
    return order


@pytest.mark.parametrize("stage", ["RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION", "CS"])
def test_regional_active_stage_completes_without_cs_approval(client, stage):
    user = _make_user("regional_done")
    _login(client, user)
    order = _regional(stage)
    oid = order.id
    cta = _cta(order, user)
    assert cta["enabled"] and cta["endpoint"] == "cs_complete"
    response = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert response.status_code == 200, response.get_json()
    assert "지방" in response.get_json()["message"]
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.status == saved.erp_stage_code == saved.structured_data["workflow"]["stage"] == "COMPLETED"
    assert saved.structured_data["quests"][0]["team_approvals"]["CS"]["approved"] is False
    assert "지방 주문 완료" in saved.structured_data["workflow"]["history"][-1]["note"]
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="REGIONAL_ORDER_COMPLETED").count() == 1


@pytest.mark.parametrize("kind,expected", [("hold", "HOLD_ACTIVE"), ("as", "AS_ACTIVE"), ("draft", "DRAFT_NOT_PROMOTED")])
def test_regional_completion_keeps_other_gates(client, kind, expected):
    user = _make_user("regional_block")
    _login(client, user)
    sd = _cs_quest(False)
    if kind == "hold":
        sd["workflow"] = {"hold": {"active": True}}
    elif kind == "as":
        sd["as_lifecycle"] = {"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1"}]}
    order = _regional(sd=sd)
    if kind == "draft":
        order.status = "DRAFT"
        db_session.commit()
    oid = order.id
    assert not _cta(order, user)["enabled"]
    response = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["code"] == expected
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="REGIONAL_ORDER_COMPLETED").count() == 0


def test_body_cannot_turn_normal_order_into_regional_order(client):
    user = _make_user("regional_forge")
    _login(client, user)
    order = _make_order("PRODUCTION", status="SCHEDULED")
    assert not _cta(order, user)["enabled"]
    response = client.post(f"/api/orders/{order.id}/cs/complete", json={"is_regional": True})
    assert response.status_code == 409 and response.get_json()["code"] == "INVALID_STAGE"


def test_regional_completion_permission_and_field_update_boundary(client):
    user = _make_user("regional_no_permission", team="DRAWING")
    order = _regional()
    oid = order.id
    _login(client, user)
    assert not _cta(order, user)["enabled"]
    assert client.post(f"/api/orders/{oid}/cs/complete", json={}).status_code == 403
    _login(client, _make_user("regional_field"))
    response = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "COMPLETED"})
    assert response.status_code == 409 and response.get_json()["code"] == "USE_CS_COMPLETE"


def test_regional_receipt_replay_does_not_duplicate_completion(client):
    user = _make_user("regional_replay")
    _login(client, user)
    order = _regional()
    oid = order.id
    attempt = OrderConstructionAttempt(id=str(uuid.uuid4()), order_id=oid, status="READY", is_current=True)
    db_session.add(attempt)
    db_session.commit()
    attempt_id = attempt.id
    key = str(uuid.uuid4())
    url = f"/api/orders/{oid}/cs/complete"
    for _ in range(2):
        response = client.post(url, json={}, headers={"Idempotency-Key": key})
        assert response.status_code == 200, response.get_json()
    conflict = client.post(url, json={"different": True}, headers={"Idempotency-Key": key})
    assert conflict.status_code == 409 and conflict.get_json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    db_session.expire_all()
    saved_attempt = db_session.get(OrderConstructionAttempt, attempt_id)
    assert saved_attempt.status == "COMPLETED" and not saved_attempt.is_current and saved_attempt.completed_at
    assert db_session.query(OrderEvent).filter_by(order_id=oid, event_type="REGIONAL_ORDER_COMPLETED").count() == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_REGIONAL_COMPLETE", idempotency_key=key).count() == 1
    assert db_session.query(SecurityLog).filter(SecurityLog.message == f"주문 #{oid} 지방 주문 완료 -> 최종 완료").count() == 1


def test_regional_completion_respects_if_match_and_deleted_order(client):
    user = _make_user("regional_revision")
    _login(client, user)
    order = _regional()
    oid = order.id
    response = client.post(f"/api/orders/{oid}/cs/complete", json={}, headers={"If-Match": '"999"'})
    assert response.status_code == 409 and response.get_json()["code"] == "REVISION_CONFLICT"
    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert order.structured_data["workflow"]["stage"] == "PRODUCTION"
    order.status = "DELETED"
    db_session.commit()
    assert client.post(f"/api/orders/{oid}/cs/complete", json={}).status_code == 404


def test_regional_idempotency_key_is_bound_to_order(client):
    _login(client, _make_user("regional_receipt_scope"))
    first_id, second_id = _regional().id, _regional().id
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    assert client.post(f"/api/orders/{first_id}/cs/complete", json={}, headers=headers).status_code == 200
    response = client.post(f"/api/orders/{second_id}/cs/complete", json={}, headers=headers)
    assert response.status_code == 409 and response.get_json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    db_session.expire_all()
    assert db_session.get(Order, second_id).erp_stage_code == "PRODUCTION"
    assert db_session.query(OrderEvent).filter_by(order_id=second_id).count() == 0


def test_regional_rejects_other_order_receipt_from_concurrent_winner(client, monkeypatch):
    from types import SimpleNamespace
    from foms.services.orders import cs_complete_service as service

    _login(client, _make_user("regional_receipt_race"))
    oid = _regional().id
    winner = SimpleNamespace(replayed=True, mutation=SimpleNamespace(body={"resources": [{"order_id": oid + 1}]}))
    monkeypatch.setattr(service, "transition_order", lambda *args, **kwargs: winner)
    response = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert response.status_code == 409 and response.get_json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "PRODUCTION"


@pytest.mark.parametrize("stage", ["UNKNOWN", "COMPLETED"])
def test_regional_invalid_main_stage_has_no_enabled_button(client, stage):
    user = _make_user("regional_bad_stage")
    _login(client, user)
    order = _regional(stage)
    assert not _cta(order, user)["enabled"]
    response = client.post(f"/api/orders/{order.id}/cs/complete", json={})
    assert response.status_code == 409


def test_regional_completion_preserves_completed_as_overlay(client):
    _login(client, _make_user("regional_as_history"))
    cycle = {"cycle_id": "c1", "transitions": [{"to": "COMPLETED"}], "completed_at": "2026-10-01T10:00:00"}
    order = _regional(sd={"as_lifecycle": {"current_cycle_id": "c1", "cycles": [cycle]}})
    oid = order.id
    response = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert response.status_code == 200, response.get_json()
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.erp_stage_code == "COMPLETED" and saved.status == "AS_COMPLETED"
    assert saved.structured_data["as_lifecycle"]["cycles"] == [cycle]


def test_regional_dashboard_button_and_completed_section_match(client):
    from bs4 import BeautifulSoup

    user = _make_user("regional_screen", role="ADMIN")
    _login(client, user)
    oid = _regional().id
    page = BeautifulSoup(client.get("/regional_dashboard").data, "html.parser")
    button = page.select_one(f'#section-scheduled .js-complete-order[data-order-id="{oid}"]')
    assert button and button.get("data-complete-endpoint") == "cs_complete"
    assert not button.has_attr("disabled")
    assert client.post(f"/api/orders/{oid}/cs/complete", json={}).status_code == 200
    page = BeautifulSoup(client.get("/regional_dashboard").data, "html.parser")
    assert not page.select_one(f'#section-scheduled tr[data-order-id="{oid}"]')
    assert any(row.find("td").get_text(strip=True) == str(oid)
               for row in page.select("#section-completed tbody tr"))


def test_regional_completion_closes_canonical_logistics_and_keeps_other_data(client):
    from foms.services.orders.state_axes import legacy_status_projection, read_state_axes

    _login(client, _make_user("regional_logistics"))
    order = _regional(sd={"shipment": {"logistics_status": "SCHEDULED", "memo": "keep"},
                          "drawing_current_files": [{"key": "unchanged"}]})
    oid = order.id
    assert client.post(f"/api/orders/{oid}/cs/complete", json={}).status_code == 200
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["shipment"]["logistics_status"] == "NONE"
    assert saved.structured_data["shipment"]["memo"] == "keep"
    assert saved.structured_data["drawing_current_files"] == [{"key": "unchanged"}]
    assert legacy_status_projection(read_state_axes(saved)) == saved.status == "COMPLETED"


def test_regional_completion_rolls_back_all_axes_on_followup_failure(client, monkeypatch):
    from foms.services.orders import cs_complete_service as service
    from foms.services.orders.revision import RevisionError

    user = _make_user("regional_atomic")
    _login(client, user)
    oid = _regional().id
    finish = service._finish_regional_logistics

    def fail_after_logistics(db, order, actor_id):
        finish(db, order, actor_id)
        raise RevisionError("rollback check")

    monkeypatch.setattr(service, "_finish_regional_logistics", fail_after_logistics)
    response = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert response.status_code == 409
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.status == "SCHEDULED" and saved.erp_stage_code == "PRODUCTION"
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
