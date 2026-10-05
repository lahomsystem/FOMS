"""초안 표식 규칙 — 단계·상태를 쓰는 5길은 승격 전 초안을 409 로 거절한다.

규칙(``foms/services/orders/draft_guard.py``): ``meta.draft`` 가 참인 ERP 주문의 status 는
DRAFT 또는 DELETED 뿐이다. 2026-10-05 조사(``docs/plans/2026-10-05-hidden-draft-flag-orders-
investigation.md`` §4)에서 단계 강제 변경·일반 상태 변경이 초안에 200 을 주고 ``('RECEIVED',
표식 참)`` 숨은 모양을 만들었다. 이 파일은 그 재현 값을 실패 값으로 고정한다.

각 길마다 **음성 대조군**(같은 내용의 승격된 주문)이 지금처럼 통과하는지 함께 본다 — 가드가
너무 넓어 정상 주문까지 막으면 대조군이 빨개진다. 초안 모양은 두 가지를 다 쓴다:
``status_draft``(DRAFT + 표식, 자동저장이 만드는 정상 초안)와 ``flag_only``(실제 단계 + 표식,
이미 숨은 모양 — 쓰기로 "세탁"되지도 않아야 한다).
"""

from __future__ import annotations

import hashlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.draft_guard import (
    DRAFT_NOT_PROMOTED_CODE,
    DraftNotPromotedError,
    violates_draft_flag_rule,
)
from foms.services.orders.order_transition_service import transition_order
from models import Order, OrderEvent, User

_DRAFT_SHAPES = ("status_draft", "flag_only")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _login(client, username: str, *, role: str = "ADMIN", team: str = "CS") -> int:
    """사용자를 만들고 세션에 로그인한 뒤 id 를 돌려준다."""
    user = User(
        username=username, password=generate_password_hash("pw"), role=role, team=team,
        name=username, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = int(user.id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
    return user_id


def _received_quest() -> dict:
    """RECEIVED 단계 CS 팀 승인 퀘스트(최종 승인 시 MEASURE 로 전이)."""
    return {
        "stage": "RECEIVED", "title": "RECEIVED quest", "description": "",
        "owner_team": "CS", "owner_person": "", "status": "OPEN",
        "required_approvals": ["CS"],
        "team_approvals": {"CS": {"approved": False, "approved_by": None, "approved_at": None}},
        "approval_mode": "team", "assignee_approval": None,
        "created_at": "2026-10-05T00:00:00", "updated_at": "2026-10-05T00:00:00",
    }


def _make_order(shape: str) -> int:
    """``status_draft`` · ``flag_only`` · ``promoted``(대조군) 모양의 ERP 주문 1건."""
    is_draft = shape != "promoted"
    meta = {"draft": True, "created_via": "ADD_ORDER_AUTOSAVE"} if is_draft else {
        "draft": False, "finalized_at": "2026-10-05T00:00:00"}
    order = Order(
        received_date="2026-10-05", customer_name="초안규칙-고객", phone="010-1111-2222",
        address="서울 역삼로 45", product="붙박이장",
        status="DRAFT" if shape == "status_draft" else "RECEIVED",
        is_erp_order=True, erp_stage_code="RECEIVED",
        structured_data={
            "meta": meta,
            "workflow": {"stage": "RECEIVED"},
            "parties": {"customer": {"name": "초안규칙-고객", "phone": "010-1111-2222"}},
            "quests": [_received_quest()],
        },
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _snapshot(order_id: int) -> tuple:
    """쓰기 거절 뒤 '그대로'를 비교할 값(status·표식·단계·버전·퀘스트)."""
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data or {}
    return (
        order.status,
        (sd.get("meta") or {}).get("draft"),
        (sd.get("workflow") or {}).get("stage"),
        order.erp_stage_code,
        int(order.mutation_version or 0),
        repr(sd.get("quests")),
    )


def _event_count(order_id: int, *types: str) -> int:
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type.in_(types))
        .count()
    )


def _hidden_ids() -> set[int]:
    """규칙을 어긴 행 번호 전부(표식 참인데 status 가 DRAFT·DELETED 아님)."""
    db_session.expire_all()
    return {int(o.id) for o in db_session.query(Order).all() if violates_draft_flag_rule(o)}


def _make_draft(shape: str) -> int:
    return _make_order(shape)


def _state(order_id: int) -> tuple:
    """거절 전 상태 — 그 주문의 값과 그때의 숨은 모양 행 집합."""
    return _snapshot(order_id), _hidden_ids()


def _assert_rejected(resp, order_id: int, before: tuple) -> None:
    """409 DRAFT_NOT_PROMOTED · 주문 값 그대로 · 숨은 모양 행이 새로 생기지 않음(규칙 훑기)."""
    snapshot_before, hidden_before = before
    assert resp.status_code == 409, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["code"] == DRAFT_NOT_PROMOTED_CODE
    assert _snapshot(order_id) == snapshot_before
    assert _hidden_ids() <= hidden_before


# --------------------------------------------------------------------------- #
# 1. 단계 강제 변경 — 단건(메인·AS·완료·삭제 목표 모두 갈래 전에 막힌다)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", _DRAFT_SHAPES)
def test_stage_override_rejects_unpromoted_draft(client, shape):
    _login(client, f"dg_so_{shape}", role="MANAGER")
    order_id = _make_draft(shape)
    before = _state(order_id)

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"confirm": True, "to_stage": "MEASURE", "reason": "초안 단계 변경 시도"},
    )

    _assert_rejected(resp, order_id, before)
    assert _event_count(order_id, "STAGE_OVERRIDE") == 0


@pytest.mark.parametrize("to_stage", ["AS_RECEIVED", "COMPLETED", "DELETED"])
def test_stage_override_extended_targets_reject_draft_even_with_admin_override(client, to_stage):
    """관리자 뚫기로도 못 넘는다 — AS·완료·삭제 갈래로 가르기 전에 막힌다."""
    _login(client, f"dg_so_ext_{to_stage}", role="ADMIN")
    order_id = _make_draft("status_draft")
    before = _state(order_id)

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"confirm": True, "to_stage": to_stage, "reason": "초안 확장 목표 시도",
              "admin_override": True, "override_reason": "관리자 강제 진행 시도"},
    )

    _assert_rejected(resp, order_id, before)
    assert _event_count(order_id, "ADMIN_OVERRIDE_USED", "STAGE_OVERRIDE") == 0


def test_stage_override_negative_control_promoted_order_passes(client):
    """음성 대조군 — 승격된 같은 내용 주문은 지금처럼 200, 단계가 바뀐다."""
    _login(client, "dg_so_control", role="MANAGER")
    order_id = _make_order("promoted")

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"confirm": True, "to_stage": "MEASURE", "reason": "정상 주문 단계 변경"},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _snapshot(order_id)[0] == "MEASURE"
    assert _event_count(order_id, "STAGE_OVERRIDE") == 1


# --------------------------------------------------------------------------- #
# 2. 단계 강제 변경 — 일괄(초안만 빼고 나머지는 바뀐다)
# --------------------------------------------------------------------------- #
def test_bulk_stage_override_skips_draft_and_changes_promoted(client):
    _login(client, "dg_so_bulk", role="MANAGER")
    draft_id = _make_draft("status_draft")
    promoted_id = _make_order("promoted")
    draft_before = _snapshot(draft_id)
    hidden_before = _hidden_ids()

    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={"confirm": True, "to_stage": "MEASURE", "reason": "일괄 변경",
              "order_ids": [draft_id, promoted_id]},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["skipped_draft"] == [draft_id]
    assert [item["order_id"] for item in data["results"]] == [promoted_id]
    assert _snapshot(draft_id) == draft_before
    assert _snapshot(promoted_id)[0] == "MEASURE"
    assert _hidden_ids() <= hidden_before


def test_bulk_stage_override_only_drafts_is_409(client):
    _login(client, "dg_so_bulk_only", role="MANAGER")
    draft_id = _make_draft("flag_only")
    before = _state(draft_id)

    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={"confirm": True, "to_stage": "MEASURE", "reason": "일괄 변경",
              "order_ids": [draft_id]},
    )

    _assert_rejected(resp, draft_id, before)


# --------------------------------------------------------------------------- #
# 3. 일반 상태 변경 — 단건·관리자 뚫기·일괄
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", _DRAFT_SHAPES)
def test_update_order_status_rejects_unpromoted_draft(client, shape):
    _login(client, f"dg_st_{shape}")
    order_id = _make_draft(shape)
    before = _state(order_id)

    resp = client.post("/api/update_order_status", json={"order_id": order_id, "status": "MEASURE"})

    _assert_rejected(resp, order_id, before)
    assert _event_count(order_id, "STAGE_CHANGED") == 0


def test_update_order_status_admin_override_cannot_bypass_draft(client):
    _login(client, "dg_st_override", role="ADMIN")
    order_id = _make_draft("status_draft")
    before = _state(order_id)

    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "DRAWING",
              "admin_override": True, "override_reason": "초안 강제 진행 시도"},
    )

    _assert_rejected(resp, order_id, before)
    assert _event_count(order_id, "ADMIN_OVERRIDE_USED") == 0


def test_update_order_status_negative_control_promoted_order_passes(client):
    _login(client, "dg_st_control")
    order_id = _make_order("promoted")

    resp = client.post("/api/update_order_status", json={"order_id": order_id, "status": "MEASURE"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _snapshot(order_id)[0] == "MEASURE"


def test_bulk_update_order_status_blocks_draft_and_updates_promoted(client):
    _login(client, "dg_st_bulk")
    draft_id = _make_draft("status_draft")
    promoted_id = _make_order("promoted")
    draft_before = _snapshot(draft_id)
    hidden_before = _hidden_ids()

    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [draft_id, promoted_id], "status": "MEASURE"},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["blocked_unpromoted_draft"] == [draft_id]
    assert body["updated"] == 1
    assert _snapshot(draft_id) == draft_before
    assert _snapshot(promoted_id)[0] == "MEASURE"
    assert _hidden_ids() <= hidden_before


def test_bulk_update_order_status_only_drafts_is_409(client):
    _login(client, "dg_st_bulk_only")
    draft_id = _make_draft("flag_only")
    before = _state(draft_id)

    resp = client.post(
        "/api/bulk_update_order_status", json={"order_ids": [draft_id], "status": "MEASURE"},
    )

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["blocked_unpromoted_draft"] == [draft_id]
    assert (_snapshot(draft_id), _hidden_ids()) == before


# --------------------------------------------------------------------------- #
# 4. 칸 수정의 status — 조사서 표에 없던 길
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", _DRAFT_SHAPES)
def test_update_order_field_status_rejects_unpromoted_draft(client, shape):
    _login(client, f"dg_fu_{shape}")
    order_id = _make_draft(shape)
    before = _state(order_id)

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "MEASURE"},
    )

    _assert_rejected(resp, order_id, before)


def test_update_order_field_other_field_on_draft_still_allowed(client):
    """대조군 — 거절 범위는 status 칸뿐이다(초안 작성 중 담당자 등 다른 칸은 그대로)."""
    _login(client, "dg_fu_notes")
    order_id = _make_draft("status_draft")

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "manager_name", "value": "초안 담당자"},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, order_id).manager_name == "초안 담당자"
    assert _snapshot(order_id)[:2] == ("DRAFT", True)


def test_update_order_field_status_negative_control_promoted_order_passes(client):
    _login(client, "dg_fu_control")
    order_id = _make_order("promoted")

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "MEASURE"},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _snapshot(order_id)[0] == "MEASURE"


# --------------------------------------------------------------------------- #
# 5. 퀘스트 승인 — 승인 기록부터 쓰므로 라우트에서 먼저 막아야 한다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", _DRAFT_SHAPES)
def test_quest_approve_rejects_unpromoted_draft(client, shape):
    _login(client, f"dg_qa_{shape}", role="STAFF", team="CS")
    order_id = _make_draft(shape)
    before = _state(order_id)

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})

    _assert_rejected(resp, order_id, before)  # 퀘스트 승인 기록(quests repr)도 그대로
    assert _event_count(order_id, "QUEST_APPROVAL_CHANGED", "MEASUREMENT_REQUESTED") == 0


def test_quest_approve_negative_control_promoted_order_transitions(client):
    _login(client, "dg_qa_control", role="STAFF", team="CS")
    order_id = _make_order("promoted")

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "CS"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["auto_transitioned"] is True
    assert _snapshot(order_id)[2] == "MEASURE"


# --------------------------------------------------------------------------- #
# 6. 정본 전이 transition_order — 잠금 아래 백스톱
# --------------------------------------------------------------------------- #
def _transition(order_id: int, actor_id: int):
    digest = hashlib.sha256(f"dg-transition:{order_id}".encode("utf-8")).hexdigest()
    return transition_order(
        db_session, command_id="SET_MAIN_STAGE", order_id=order_id, actor_user_id=actor_id,
        expected_from="RECEIVED", target_value="MEASURE", scope_hash=digest, request_hash=digest,
    )


@pytest.mark.parametrize("shape", _DRAFT_SHAPES)
def test_transition_order_raises_for_unpromoted_draft(client, shape):
    actor_id = _login(client, f"dg_tr_{shape}")
    order_id = _make_draft(shape)
    before = _state(order_id)

    with pytest.raises(DraftNotPromotedError) as excinfo:
        _transition(order_id, actor_id)
    db_session.rollback()

    assert excinfo.value.status_code == 409
    assert excinfo.value.error_code == DRAFT_NOT_PROMOTED_CODE
    snapshot_before, hidden_before = before
    assert _snapshot(order_id) == snapshot_before
    assert _hidden_ids() <= hidden_before


def test_transition_order_negative_control_promoted_order_succeeds(client):
    actor_id = _login(client, "dg_tr_control")
    order_id = _make_order("promoted")

    result = _transition(order_id, actor_id)
    db_session.commit()

    assert result.replayed is False
    assert _snapshot(order_id)[2] == "MEASURE"
