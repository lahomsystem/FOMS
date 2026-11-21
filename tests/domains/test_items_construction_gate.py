"""CS · 완료 문지기 — 판정 · 전이 엔진 · CS 완료 정본 · 관리자 강제 변경 (제품마다 '시공 끝' 2단계 7절 · N4).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md``. 자료 셋(부분 시공 중 · 나눠 시공 아님 ·
다 끝남)과 스위치 끔(``FOMS_ITEM_CONSTRUCTION_DONE_ENABLED=0``)을 길마다 견준다(``tests/support/item_construction_seed``).
관리자 강제 변경만 ``close_remaining_items: true`` + 사유로 남은 제품을 ``admin_override`` 로 찍고 넘긴다.
엔진 밖 옛 쓰기 · 일괄 도구 · 협력사 AS 는 ``test_items_construction_gate_legacy.py``.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.orders import item_construction_done as icd
from foms.services.orders.items_construction_gate import (
    ITEMS_CONSTRUCTION_OPEN,
    ItemsConstructionOpen,
    closing_stage_code,
    items_gate_blocks,
    items_gate_message,
)
from foms.services.orders.order_transition_service import (
    ItemsConstructionOpenError,
    TransitionError,
    transition_order,
)
from models import Order, OrderEvent, SecurityLog
from tests.support.item_construction_seed import (
    BLOCKED, FLAG, UID_A, UID_B, login, saved, seed_order, seed_sd, seed_user,
)


# ── 판정 ────────────────────────────────────────────────────────────────────

def test_gate_table(monkeypatch) -> None:
    partial, plain, done = seed_sd("CONSTRUCTION", "partial"), seed_sd("CONSTRUCTION", "plain"), seed_sd("CS", "all_done")
    assert [closing_stage_code(t) for t in ("CS", "COMPLETED", "완료", "시공", "AS_COMPLETED", "", None)] == [
        "CS", "COMPLETED", "COMPLETED", None, None, None, None]
    for target in ("CS", "COMPLETED", "완료"):
        assert items_gate_blocks(partial, target) is True, target
        assert items_gate_blocks(plain, target) is False, target
        assert items_gate_blocks(done, target) is False, target
    for target in ("CONSTRUCTION", "PRODUCTION", "SCHEDULED", "AS_COMPLETED"):
        assert items_gate_blocks(partial, target) is False, target
    assert items_gate_message(partial, "CONSTRUCTION", "CS") == BLOCKED
    assert items_gate_message(partial, "CS", "CS") is None          # 제자리 전이는 막지 않는다
    monkeypatch.setenv(FLAG, "0")
    assert items_gate_blocks(partial, "CS") is False
    assert items_gate_message(partial, "CONSTRUCTION", "CS") is None


# ── 1. 전이 엔진(도면 문 옆) ─────────────────────────────────────────────────

_ENGINE_CASES = [
    ("CONSTRUCTION_COMPLETE", "CONSTRUCTION", "CS"),
    ("SET_MAIN_STAGE", "CONSTRUCTION", "CS"),
    ("SET_MAIN_STAGE", "PRODUCTION", "COMPLETED"),
    ("CS_COMPLETE", "CS", "COMPLETED"),
    ("REGIONAL_COMPLETE", "PRODUCTION", "COMPLETED"),   # 지방 완료는 생산에서 곧장 완료로 간다
]


def _engine(order_id: int, actor_id: int, command: str, frm: str, to: str, **kw):
    return transition_order(db_session, command_id=command, order_id=order_id, actor_user_id=actor_id,
                            expected_from=frm, target_value=to, scope_hash="0" * 64, request_hash="1" * 64,
                            **kw)


@pytest.mark.parametrize("command,frm,to", _ENGINE_CASES)
def test_engine_blocks_partial_open_even_with_emergency_override(app, command, frm, to) -> None:
    actor = seed_user()
    oid = seed_order(frm)
    for kw in ({}, {"emergency_override": True, "reason": "관리자 뚫기"}):
        with pytest.raises(ItemsConstructionOpenError) as exc:
            _engine(oid, actor.id, command, frm, to, **kw)
        db_session.rollback()
        assert isinstance(exc.value, TransitionError) and isinstance(exc.value, ItemsConstructionOpen)
        assert (exc.value.error_code, exc.value.status_code, str(exc.value)) == (ITEMS_CONSTRUCTION_OPEN, 409, BLOCKED)
    assert saved(oid)[1] == frm


@pytest.mark.parametrize("command,frm,to", _ENGINE_CASES)
@pytest.mark.parametrize("kind,flag", [("plain", "1"), ("all_done", "1"), ("partial", "0")])
def test_engine_passes_controls_and_flag_off(app, monkeypatch, command, frm, to, kind, flag) -> None:
    monkeypatch.setenv(FLAG, flag)
    actor = seed_user()
    oid = seed_order(frm, kind)
    result = _engine(oid, actor.id, command, frm, to)
    db_session.commit()
    assert not result.replayed and saved(oid)[1] == to


def test_engine_does_not_gate_other_targets(app) -> None:
    """대조군 — 생산 → 시공 같은 본 흐름 전이는 남은 제품과 상관없다."""
    actor = seed_user()
    oid = seed_order("PRODUCTION")
    _engine(oid, actor.id, "SET_MAIN_STAGE", "PRODUCTION", "CONSTRUCTION")
    db_session.commit()
    assert saved(oid)[1] == "CONSTRUCTION"


# ── 2. CS 완료 정본(둘째 자리) · cs/complete 라우트 ───────────────────────────

def test_cs_complete_route_blocks_partial_open_even_for_admin_override(client) -> None:
    login(client)
    oid = seed_order("CS")
    for extra in ({}, {"admin_override": True, "override_reason": "관리자 뚫기"}):
        resp = client.post(f"/api/orders/{oid}/cs/complete", json=dict(extra))
        assert resp.status_code == 409, resp.get_data(as_text=True)
        body = resp.get_json()
        assert (body["success"], body["code"], body["message"], body["error"]) == (
            False, ITEMS_CONSTRUCTION_OPEN, BLOCKED, BLOCKED)
    assert saved(oid)[1] == "CS"


@pytest.mark.parametrize("kind,flag", [("plain", "1"), ("all_done", "1"), ("partial", "0")])
def test_cs_complete_route_controls(client, monkeypatch, kind, flag) -> None:
    monkeypatch.setenv(FLAG, flag)
    login(client)
    oid = seed_order("CS", kind)
    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert saved(oid)[:2] == ("COMPLETED", "COMPLETED")


def test_quest_cs_approve_keeps_approval_and_reports_items_open(app) -> None:
    """CS 최종 승인 뒤 자동 완료는 보류 · AS 처럼 막고 사유를 돌려준다(승인은 남는다)."""
    from foms.api.quest import _complete_cs_after_approve

    user = seed_user()
    oid = seed_order("CS")
    order = db_session.get(Order, oid)
    with app.test_request_context():
        completed, blocked, failed = _complete_cs_after_approve(db_session, order, user, user.id, {})
    assert (completed, failed) == (False, None)
    assert blocked["code"] == ITEMS_CONSTRUCTION_OPEN and "11/17 부엌가구" in blocked["message"]
    db_session.rollback()
    assert saved(oid)[1] == "CS"


# ── 3. 관리자 강제 단계 변경(N4) ───────────────────────────────────────────────

def _override(client, oid: int, to: str, **extra):
    body = {"to_stage": to, "reason": "남은 제품은 지난주에 끝냈음", "confirm": True, **extra}
    return client.post(f"/api/orders/{oid}/workflow/stage-override", json=body)


def test_stage_override_cs_blocks_then_closes_remaining_items(client) -> None:
    manager = login(client, role="MANAGER")
    manager_id, manager_name = manager.id, manager.name
    oid = seed_order("CONSTRUCTION")

    resp = _override(client, oid, "CS")
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert (body["code"], body["error"], body["data"]["remaining_summary"]) == (
        ITEMS_CONSTRUCTION_OPEN, BLOCKED, "11/17 부엌가구")
    assert saved(oid)[1] == "CONSTRUCTION"

    resp = _override(client, oid, "CS", close_remaining_items=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    status, stage, marks = saved(oid)
    assert (status, stage) == ("CS", "CS")
    assert marks[UID_A]["source"] == icd.SOURCE_VISIT                      # 먼저 찍은 기록은 그대로
    assert marks[UID_B]["source"] == icd.SOURCE_ADMIN_OVERRIDE
    assert marks[UID_B]["by_user_id"] == manager_id and marks[UID_B]["by_name"] == manager_name
    event = (db_session.query(OrderEvent)
             .filter(OrderEvent.order_id == oid, OrderEvent.event_type == "STAGE_OVERRIDE").one())
    assert event.payload["items_closed"] == [UID_B]
    logs = [row.message for row in db_session.query(SecurityLog).all()]
    assert any(f"주문 #{oid} 남은 제품 시공 끝 처리" in m and "부엌가구" in m for m in logs), logs


@pytest.mark.parametrize("kind,flag", [("plain", "1"), ("all_done", "1"), ("partial", "0")])
def test_stage_override_cs_controls(client, monkeypatch, kind, flag) -> None:
    monkeypatch.setenv(FLAG, flag)
    login(client, role="MANAGER")
    oid = seed_order("CONSTRUCTION", kind)
    resp = _override(client, oid, "CS")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    status, stage, marks = saved(oid)
    assert (status, stage) == ("CS", "CS")
    assert all(m["source"] == icd.SOURCE_VISIT for m in marks.values())   # 아무것도 새로 찍지 않는다


def test_stage_override_completed_manager_blocks_without_admin_hint_then_closes(client) -> None:
    login(client, role="MANAGER")
    oid = seed_order("CS")
    resp = _override(client, oid, "COMPLETED")
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["code"] == ITEMS_CONSTRUCTION_OPEN and body["message"] == BLOCKED   # 관리자 안내를 붙이지 않는다
    assert saved(oid)[1] == "CS"

    resp = _override(client, oid, "COMPLETED", close_remaining_items=True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    status, stage, marks = saved(oid)
    assert (status, stage) == ("COMPLETED", "COMPLETED")
    assert marks[UID_B]["source"] == icd.SOURCE_ADMIN_OVERRIDE


def test_stage_override_completed_admin_override_cannot_punch_but_close_passes(client) -> None:
    login(client, role="ADMIN")
    oid = seed_order("CONSTRUCTION")
    punch = {"admin_override": True, "override_reason": "관리자 뚫기"}
    resp = _override(client, oid, "COMPLETED", **punch)
    assert resp.status_code == 409 and resp.get_json()["code"] == ITEMS_CONSTRUCTION_OPEN
    assert saved(oid)[1] == "CONSTRUCTION"
    assert not saved(oid)[2].get(UID_B), "거부된 완료에 찍기만 남으면 안 된다"

    resp = _override(client, oid, "COMPLETED", close_remaining_items=True, **punch)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert saved(oid)[1] == "COMPLETED" and saved(oid)[2][UID_B]["source"] == icd.SOURCE_ADMIN_OVERRIDE


def test_stage_override_completed_close_requires_reason(client) -> None:
    """사유가 비면 찍지 않는다 — 빈 사유는 먼저 400 으로 끊긴다(기존 계약)."""
    login(client, role="MANAGER")
    oid = seed_order("CS")
    resp = client.post(f"/api/orders/{oid}/workflow/stage-override",
                       json={"to_stage": "COMPLETED", "reason": " ", "confirm": True, "close_remaining_items": True})
    assert resp.status_code == 400
    assert saved(oid)[1] == "CS" and UID_B not in saved(oid)[2]


@pytest.mark.parametrize("to,stage", [("CS", "CONSTRUCTION"), ("COMPLETED", "CS")])
def test_bulk_stage_override_is_all_or_nothing_then_closes(client, to, stage) -> None:
    login(client, role="MANAGER")
    partial, plain = seed_order(stage), seed_order(stage, "plain")
    body = {"order_ids": [partial, plain], "to_stage": to, "reason": "일괄 정리", "confirm": True}

    resp = client.post("/api/orders/workflow/stage-override/bulk", json=body)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["code"] == ITEMS_CONSTRUCTION_OPEN and data["error"] == f"#{partial} {BLOCKED}"
    assert saved(partial)[1] == stage and saved(plain)[1] == stage       # 한 건도 바뀌지 않는다

    resp = client.post("/api/orders/workflow/stage-override/bulk", json={**body, "close_remaining_items": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert saved(partial)[1] == to and saved(plain)[1] == to
    assert saved(partial)[2][UID_B]["source"] == icd.SOURCE_ADMIN_OVERRIDE


def test_apply_stage_override_service_backstop(app) -> None:
    """서비스가 직접 불려도(운영 도구 등) 같은 문이 걸린다 — 잠금 아래 백스톱."""
    from foms.services.orders.stage_override import apply_stage_override

    user = seed_user(role="MANAGER")
    oid = seed_order("CONSTRUCTION")
    order = db_session.get(Order, oid)
    with pytest.raises(ItemsConstructionOpen) as exc:
        apply_stage_override(order=order, to_stage="CS", reason="시험", user_id=user.id, db=db_session)
    db_session.rollback()
    assert (exc.value.order_id, str(exc.value), exc.value.remaining) == (oid, BLOCKED, "11/17 부엌가구")
    order = db_session.get(Order, oid)
    payload = apply_stage_override(order=order, to_stage="MEASURE", reason="되돌림", user_id=user.id, db=db_session)
    db_session.commit()
    assert payload["to"] == "MEASURE" and "items_closed" not in payload      # 대조군 — CS · 완료가 아니다
