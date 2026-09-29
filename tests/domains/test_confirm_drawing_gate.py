"""2a-2 C21 도면 게이트 — 고객컨펌 승인·제작 시작·결합 회귀·입구 전수 가드.

도면이 "영업이 수령 확정한 최신본"(``drawing_status == 'CONFIRMED'``)이 아니면 정식 경로로는
고객컨펌 → 생산으로 넘어가지 않는다(허용 목록 — M3). 관리자(ADMIN)만 ``admin_override``(사유)로
뚫고, 그 기록과 그 순간의 도면 상태가 남는다. MANAGER 의 ``emergency_override``(권한 축)는
이 게이트를 풀지 못한다. 일반 상태 쓰기·M16·캐시·화면 payload 는 ``test_confirm_drawing_gate_paths.py``,
전이 엔진 방어선은 ``test_confirm_drawing_gate_engine.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from db import db_session
from foms.services.orders import structured_form_projection as projection
from foms.services.orders.order_transition_service import COMMAND_REGISTRY
from tests.support.confirm_seed import (
    confirmed_drawing_sd,
    login_as,
    order_events,
    reload_order,
    seed_erp_order,
    seed_user,
)
from tests.support.quest_seed import confirm_quest_completed, confirm_quest_open

_ROOT = Path(__file__).resolve().parents[2]
_OVERRIDE = {"admin_override": True, "override_reason": "고객이 전화로 최종 컨펌 — 도면 경미 수정은 현장 반영"}


def _pair(tag: str):
    return seed_user(f"g_s_{tag}", team="SALES"), seed_user(f"g_d_{tag}", team="DRAWING")


def _approve(client, order_id: int, body: dict | None = None):
    return client.post(f"/api/orders/{order_id}/quest/approve", json=body or {})


def _assert_blocked_at_confirm(order_id: int, resp) -> None:
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["code"] == "DRAWING_STATUS"
    saved = reload_order(order_id)
    assert saved.erp_stage_code == "CONFIRM"
    assert not ((saved.structured_data or {}).get("blueprint") or {}).get("customer_confirmed")
    assert order_events(order_id, "CUSTOMER_CONFIRMED") == []


# --------------------------------------------------------------------------- #
# 고객컨펌 승인 — 허용 목록(M3)·한글 단계·옛 중첩 상태
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("tag", "sd_extra", "expected_status", "reason_word"),
    [
        ("transferred", {"drawing_status": "TRANSFERRED"}, "TRANSFERRED", "수령 확정하지 않았습니다"),
        ("pending", {"drawing_status": "PENDING"}, "PENDING", "수령 확정 기록이 없습니다"),
        ("nokey", {}, "NONE", "수령 확정 기록이 없습니다"),
        ("returned", {"drawing_status": "RETURNED"}, "RETURNED", "수정 요청이 진행 중"),
    ],
    ids=["transferred", "pending", "no-key", "returned"],
)
def test_confirm_approve_blocked_unless_drawing_confirmed(client, tag, sd_extra, expected_status, reason_word):
    sales, drafter = _pair(tag)
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, quests=[confirm_quest_open()], **sd_extra)
    login_as(client, sales)

    resp = _approve(client, oid)

    _assert_blocked_at_confirm(oid, resp)
    body = resp.get_json()
    assert body["drawing_status"] == expected_status
    assert reason_word in body["message"]


def test_korean_confirm_stage_returned_approve_is_blocked(client):
    """리뷰 프로브를 옮김 — ``workflow.stage='고객컨펌'`` 원문이어도 게이트가 정규화해 막는다."""
    sales, drafter = _pair("ko")
    oid = seed_erp_order("고객컨펌", erp_stage="CONFIRM", sales=sales, drafter=drafter,
                         drawing_status="RETURNED", quests=[confirm_quest_open(stage="고객컨펌")])
    login_as(client, sales)

    resp = _approve(client, oid)

    _assert_blocked_at_confirm(oid, resp)
    assert (reload_order(oid).structured_data["workflow"]).get("stage") == "고객컨펌"


def test_legacy_nested_confirmed_only_order_passes(client):
    """최상위 키가 없고 옛 중첩 ``drawing.status='CONFIRMED'`` 만 있는 주문은 통과(판정 정본 폴백)."""
    sales, drafter = _pair("nested")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing={"status": "CONFIRMED"},
                         quests=[confirm_quest_open()])
    login_as(client, sales)

    resp = _approve(client, oid)

    assert resp.status_code == 200, resp.get_json()
    assert reload_order(oid).erp_stage_code == "PRODUCTION"


def test_admin_override_punches_drawing_gate_and_records_snapshot(client):
    sales, drafter = _pair("adm")
    admin = seed_user("g_admin_adm", role="ADMIN", team="SALES")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="RETURNED",
                         quests=[confirm_quest_open()])
    login_as(client, admin)

    resp = _approve(client, oid, _OVERRIDE)

    assert resp.status_code == 200, resp.get_json()
    saved = reload_order(oid)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.structured_data["drawing_status"] == "RETURNED"
    events = order_events(oid, "ADMIN_OVERRIDE_USED")
    assert len(events) == 1
    assert "DRAWING_STATUS" in events[0].payload["gates"]
    assert events[0].payload["axis"] == "QUEST"
    assert events[0].payload["drawing_status"] == "RETURNED"
    assert len(order_events(oid, "CUSTOMER_CONFIRMED")) == 1


def test_manager_emergency_override_does_not_unlock_drawing_gate(client):
    sales, drafter = _pair("mgr")
    manager = seed_user("g_mgr", role="MANAGER", team="SALES")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="TRANSFERRED",
                         quests=[confirm_quest_open()])
    login_as(client, manager)

    resp = _approve(client, oid, {"emergency_override": True, "override_reason": "급함"})

    _assert_blocked_at_confirm(oid, resp)


def test_retransition_of_completed_confirm_quest_is_blocked_too(client):
    sales, drafter = _pair("retr")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="RETURNED",
                         quests=[confirm_quest_completed()])
    login_as(client, sales)

    _assert_blocked_at_confirm(oid, _approve(client, oid))


# --------------------------------------------------------------------------- #
# 제작 시작 — (b) CONFIRM 호환 · (a) 생산 대기 run 시작(Q2) · 제작 완료는 막지 않음
# --------------------------------------------------------------------------- #
def _start(client, order_id: int, body: dict | None = None):
    return client.post(f"/api/orders/{order_id}/production/start", json=body or {})


def test_production_start_compat_blocked_unless_confirmed(client):
    sales, drafter = _pair("pb")
    prod = seed_user("g_prod_pb", team="PRODUCTION")
    oid = seed_erp_order("CONFIRM", sales=sales, drafter=drafter, drawing_status="PENDING",
                         quests=[confirm_quest_completed()])
    login_as(client, prod)

    resp = _start(client, oid)

    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["code"] == "DRAWING_STATUS"
    assert "도면 수령 확정 기록이 없어" in body["message"] and sales.name in body["message"]
    assert reload_order(oid).erp_stage_code == "CONFIRM"


def test_production_run_start_blocked_while_revision_in_flight(client):
    sales, drafter = _pair("pa")
    prod = seed_user("g_prod_pa", team="PRODUCTION")
    oid = seed_erp_order("PRODUCTION", sales=sales, drafter=drafter, drawing_status="RETURNED")
    login_as(client, prod)

    resp = _start(client, oid)

    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["code"] == "DRAWING_STATUS" and body["drawing_status"] == "RETURNED"
    assert "도면을 고치는 중" in body["message"] and f"영업 담당({sales.name})" in body["message"]
    assert order_events(oid, "PRODUCTION_STARTED") == []


def test_production_run_start_passes_when_confirmed_and_admin_can_punch(client):
    sales, drafter = _pair("pa2")
    prod = seed_user("g_prod_pa2", team="PRODUCTION")
    admin = seed_user("g_admin_pa2", role="ADMIN", team="PRODUCTION")
    ok_id = seed_erp_order("PRODUCTION", sales=sales, drafter=drafter, **confirmed_drawing_sd())
    returned_id = seed_erp_order("PRODUCTION", sales=sales, drafter=drafter, drawing_status="TRANSFERRED")

    login_as(client, prod)
    assert _start(client, ok_id).status_code == 200
    login_as(client, admin)
    resp = _start(client, returned_id, _OVERRIDE)

    assert resp.status_code == 200, resp.get_json()
    events = order_events(returned_id, "ADMIN_OVERRIDE_USED")
    assert events and "DRAWING_STATUS" in events[0].payload["gates"]
    assert events[0].payload["drawing_status"] == "TRANSFERRED"


def test_production_complete_is_not_blocked_by_revision(client):
    """이미 만드는 중이면 막지 않는다 — 제작 완료는 RETURNED 여도 그대로(알림형 설계 유지)."""
    sales, drafter = _pair("pc")
    prod = seed_user("g_prod_pc", team="PRODUCTION")
    oid = seed_erp_order("PRODUCTION", sales=sales, drafter=drafter, **confirmed_drawing_sd())
    login_as(client, prod)
    assert _start(client, oid).status_code == 200
    saved = reload_order(oid)
    sd = dict(saved.structured_data)
    sd["drawing_status"] = "RETURNED"
    saved.structured_data = sd
    db_session.commit()

    resp = client.post(f"/api/orders/{oid}/production/complete", json={})

    assert resp.status_code == 200, resp.get_json()
    assert reload_order(oid).erp_stage_code == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 결합 회귀 — M4(C8-X 로 옛 도면이 1번인 채 CONFIRMED) · M1(오래된 폼 저장 뒤 승인)
# --------------------------------------------------------------------------- #
def _key(order_id: int, name: str) -> str:
    return f"orders/{order_id}/drawing_wizard/exports/{name}"


def _walk_confirmed(client, tag: str):
    sales, drafter = _pair(tag)
    oid = seed_erp_order("DRAWING", sales=sales, drafter=drafter)
    login_as(client, drafter)
    assert client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": _key(oid, "v1.png"), "filename": "v1.png"}]}).status_code == 200
    login_as(client, sales)
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200
    return oid, sales, drafter


def test_m4_revision_retransfer_receipt_then_approve_uses_new_drawing(client):
    """프로브 P4 — CONFIRM 수정요청 → 반영 체크 → 재전달 → 수령 확정 → 승인은 새 도면으로만 통과."""
    oid, sales, drafter = _walk_confirmed(client, "m4")
    assert client.post(f"/api/orders/{oid}/request-revision", json={"note": "손잡이"}).status_code == 200
    login_as(client, sales)
    blocked = _approve(client, oid)
    assert blocked.status_code == 409 and blocked.get_json()["code"] == "DRAWING_STATUS"

    req = [h for h in reload_order(oid).structured_data["drawing_transfer_history"]
           if h.get("action") == "REQUEST_REVISION"][-1]
    login_as(client, drafter)
    assert client.post(f"/api/orders/{oid}/request-revision-check",
                       json={"request_at": req["at"], "by_user_id": req["by_user_id"], "checked": True}).status_code == 200
    v2 = _key(oid, "v2.png")
    sent = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"files": [{"key": v2}], "mode": "APPEND", "is_retransfer": True})
    assert sent.status_code == 200, sent.get_json()
    login_as(client, sales)
    assert _approve(client, oid).status_code == 409  # TRANSFERRED — 아직 수령 확정 전
    assert client.post(f"/api/orders/{oid}/confirm-drawing-receipt", json={}).status_code == 200

    resp = _approve(client, oid)

    assert resp.status_code == 200, resp.get_json()
    saved = reload_order(oid)
    assert saved.erp_stage_code == "PRODUCTION"
    assert [f["key"] for f in saved.structured_data["drawing_current_files"]] == [v2]


@pytest.mark.skipif(
    not hasattr(projection, "lock_server_owned_keys"),
    reason="2a-1①(서버 소유 키 잠금)과 합친 뒤에만 성립 — 그 전에는 오래된 폼이 도면 상태를 되돌린다",
)
def test_m1_stale_form_put_then_approve_still_blocked(client):
    oid, sales, _drafter = _walk_confirmed(client, "m1")
    snap = client.get(f"/api/orders/{oid}/structured").get_json()
    assert client.post(f"/api/orders/{oid}/request-revision", json={"note": "색"}).status_code == 200
    client.put(f"/api/orders/{oid}/structured", json={"structured_data": snap["structured_data"]})

    resp = _approve(client, oid)

    _assert_blocked_at_confirm(oid, resp)


# --------------------------------------------------------------------------- #
# 입구 전수 가드 — 생산으로 들어가는 command·raw 단계 쓰기 파일이 늘면 빨개진다
# --------------------------------------------------------------------------- #
_PRODUCTION_ENTRY_TABLE = {
    "CUSTOMER_CONFIRM": "도면 게이트(라우트 + 엔진 방어선)",
    "PRODUCTION_START": "도면 게이트(라우트 + 엔진 방어선)",
    "SET_MAIN_STAGE": "라우트 COMMAND_REQUIRED(인접) · OVERRIDE_BLOCK(비인접)",
    "PRODUCTION_UNCOMPLETE": "관리자 뚫기 허용 목록(ADMIN_OVERRIDE 에 도면 상태 기록)",
    "CONSTRUCTION_REWORK": "관리자 뚫기 허용 목록(ADMIN_OVERRIDE 에 도면 상태 기록)",
}

_MAIN_RAW_WRITER_FILES = {
    "foms/api/erp_orders_structured.py",
    "foms/api/orders/field_update.py",
    "foms/api/orders/status.py",
    "foms/api/production/orders.py",
    "foms/services/erp_sync_columns.py",
    "foms/services/orders/as_cycle_service.py",
    "foms/services/orders/order_create.py",
    "foms/services/orders/order_transition_service.py",
    "foms/services/orders/repair_order_state_axes.py",
    "foms/services/orders/stage_override.py",
    "foms/services/orders/trash_mirror.py",
    "foms/web/orders/listing.py",
    "foms/web/orders/trash.py",
}


def test_every_command_entering_production_is_in_the_gate_table(app):
    import app as _app  # noqa: F401  # 모든 blueprint 가 registry 에 additive 등록을 마친 상태

    entering = {cid for cid, cmd in COMMAND_REGISTRY.items() if "PRODUCTION" in cmd.to_values}

    assert entering == set(_PRODUCTION_ENTRY_TABLE), (
        "생산 단계로 들어가는 command 가 바뀌었다 — 도면 게이트를 달거나 표에 사유를 적어라: "
        f"{sorted(entering ^ set(_PRODUCTION_ENTRY_TABLE))}"
    )


def test_main_axis_raw_stage_writer_files_are_pinned():
    inventory = json.loads((_ROOT / "docs/harness/foms_state_writer_inventory.json").read_text(encoding="utf-8"))
    files = {w["path"] for w in inventory["writers"] if w["axis"] == "MAIN"}

    assert files == _MAIN_RAW_WRITER_FILES, (
        "MAIN 축 raw 단계 쓰기 파일이 바뀌었다 — 새 파일이면 도면 게이트(confirm_drawing_gate)를 검토: "
        f"{sorted(files ^ _MAIN_RAW_WRITER_FILES)}"
    )
