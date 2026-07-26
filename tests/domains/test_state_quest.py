"""STATE-QUEST-01 — quest 승인 → stage 전이 오케스트레이션 (service-direct).

quest 최종 승인이 stage 전이를 유발하는 정본 경로를 **서비스 직접 호출**로 고정한다(HTTP route
호출·request monkeypatch 금지, §5.2·report line 320,330-331):

* RECEIVED/MEASURE 최종 승인 → order_transition_service 경유 다음 stage 전이(version/receipt/event).
* CUSTOMER_CONFIRM adapter 는 CONFIRM quest 를 같은 tx 에서 완료(stage 는 CONFIRM 유지).
* PRODUCTION/CONSTRUCTION/CS quest 승인은 prerequisite-only → stage advance 없음.
* DRAWING/CONFIRM standalone quest 승인 전이는 STAGE_COMMAND_REQUIRED 로 거부.

전이 엔진은 SQLite 도메인 레인에서 동작한다(STATE-PROD 선례). ``session.commit()`` 은 테스트가
소유한다(REV-00). 실 PostgreSQL 다중세션 원자성·FOR UPDATE 직렬화는
``tests/postgres/test_order_transition_service.py`` 가 별도로 고정한다.
"""
from __future__ import annotations

from db import db_session
from foms.services.orders.quest_transition_service import (
    QuestIncompleteError,
    StandaloneStageAdvanceError,
    advance_stage_on_quest_completion,
    complete_confirm_quest,
)
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    User,
)

_H = "b" * 64  # scope/request hash 자리(내용 무관, 64-hex)


def _make_actor() -> User:
    from werkzeug.security import generate_password_hash

    user = User(
        username="quest-actor",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="CS",
        name="작업자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _complete_team_quest(stage_code: str, teams: list[str]) -> dict:
    """team-mode quest 로, 지정 팀 전원이 승인 완료된 상태."""
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "status": "IN_PROGRESS",
        "required_approvals": list(teams),
        "team_approvals": {
            t: {"approved": True, "approved_by": 1, "approved_at": "2026-07-24T00:00:00"}
            for t in teams
        },
        "approval_mode": "team",
        "assignee_approval": None,
    }


def _open_team_quest(stage_code: str, teams: list[str]) -> dict:
    """team-mode quest 로, 아직 아무도 승인하지 않은 상태(미완)."""
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "status": "OPEN",
        "required_approvals": list(teams),
        "team_approvals": {},
        "approval_mode": "team",
        "assignee_approval": None,
    }


def _approved_assignee_quest(stage_code: str) -> dict:
    """assignee-mode quest 로, 담당자 승인 완료된 상태."""
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "status": "IN_PROGRESS",
        "required_approvals": ["SALES"],
        "team_approvals": {},
        "approval_mode": "assignee",
        "assignee_approval": {
            "approved": True,
            "approved_by": 1,
            "approved_by_name": "영업",
            "approved_at": "2026-07-24T00:00:00",
        },
    }


def _open_confirm_quest() -> dict:
    """CONFIRM assignee-mode quest, 미승인(OPEN)."""
    return {
        "stage": "CONFIRM",
        "title": "CONFIRM quest",
        "status": "OPEN",
        "required_approvals": ["SALES"],
        "team_approvals": {},
        "approval_mode": "assignee",
        "assignee_approval": {
            "approved": False,
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
        },
    }


def _make_order(*, stage: str, quests: list[dict]) -> Order:
    order = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
        is_erp_order=True,
        status=stage,
        erp_stage_code=stage,
        structured_data={"workflow": {"stage": stage}, "quests": quests},
    )
    db_session.add(order)
    db_session.commit()
    return order


# --------------------------------------------------------------------------- #
# RECEIVED 최종 승인 → MEASURE 전이 (version/receipt/event + fresh MEASURE quest)
# --------------------------------------------------------------------------- #
def test_received_final_approval_transitions_to_measure(app):
    actor = _make_actor()
    order = _make_order(stage="RECEIVED", quests=[_complete_team_quest("RECEIVED", ["CS"])])
    order_id, base_version = order.id, order.mutation_version

    result = advance_stage_on_quest_completion(
        db_session,
        order_id=order_id,
        actor_user_id=actor.id,
        scope_hash=_H,
        request_hash=_H,
    )
    db_session.commit()

    assert result is not None and not result.replayed
    assert result.event_type == "MEASUREMENT_REQUESTED"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    assert saved.erp_stage_code == "MEASURE"
    # version bump (엔진 소유).
    assert saved.mutation_version == base_version + 1
    # receipt 기록.
    assert result.mutation.read_receipt_id
    assert (
        db_session.query(OrderMutationReceipt)
        .filter(OrderMutationReceipt.read_receipt_id == result.mutation.read_receipt_id)
        .count()
        == 1
    )
    # legacy OrderEvent parity + tx내 outbox.
    ev = db_session.query(OrderEvent).filter(OrderEvent.id == result.event_id).one()
    assert ev.event_type == "MEASUREMENT_REQUESTED"
    assert (
        db_session.query(DomainSideEffectOutbox)
        .filter(DomainSideEffectOutbox.order_event_id == result.event_id)
        .count()
        == 1
    )
    # fresh MEASURE quest 생성(report line 330).
    stages = [q.get("stage") for q in saved.structured_data.get("quests", [])]
    assert "MEASURE" in stages


# --------------------------------------------------------------------------- #
# MEASURE 최종 승인 → DRAWING 전이 (DRAWING quest 미생성)
# --------------------------------------------------------------------------- #
def test_measure_final_approval_transitions_to_drawing(app):
    actor = _make_actor()
    order = _make_order(stage="MEASURE", quests=[_approved_assignee_quest("MEASURE")])
    order_id = order.id

    result = advance_stage_on_quest_completion(
        db_session,
        order_id=order_id,
        actor_user_id=actor.id,
        scope_hash=_H,
        request_hash=_H,
    )
    db_session.commit()

    assert result is not None and result.event_type == "MEASUREMENT_COMPLETED"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.erp_stage_code == "DRAWING"
    # DRAWING quest 미생성(report line 331) — DRAWING 은 command 전용.
    stages = [q.get("stage") for q in saved.structured_data.get("quests", [])]
    assert "DRAWING" not in stages


# --------------------------------------------------------------------------- #
# CUSTOMER_CONFIRM adapter → CONFIRM quest 한 tx 완료 (stage 는 CONFIRM 유지)
# --------------------------------------------------------------------------- #
def test_customer_confirm_completes_confirm_quest_in_one_tx(app):
    actor = _make_actor()
    order = _make_order(stage="CONFIRM", quests=[_open_confirm_quest()])
    order_id, base_version = order.id, order.mutation_version

    changed = complete_confirm_quest(
        order, actor_user_id=actor.id, actor_name="영업", approving_team="SALES"
    )
    db_session.commit()

    assert changed is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    quest = saved.structured_data["quests"][0]
    # quest 완료 처리 + actor approval 기록.
    assert quest["status"] == "COMPLETED"
    assert quest["completed_at"]
    assert quest["assignee_approval"]["approved"] is True
    assert quest["assignee_approval"]["approved_by"] == actor.id
    # stage 는 CONFIRM 유지(CONFIRM→PRODUCTION 은 PRODUCTION_START 소관) · version 불변(전이 아님).
    assert saved.structured_data["workflow"]["stage"] == "CONFIRM"
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.mutation_version == base_version


# --------------------------------------------------------------------------- #
# prerequisite-only stage(PRODUCTION 등) → stage advance 없음
# --------------------------------------------------------------------------- #
def test_prerequisite_only_stage_does_not_advance(app):
    actor = _make_actor()
    order = _make_order(
        stage="PRODUCTION", quests=[_complete_team_quest("PRODUCTION", ["PRODUCTION"])]
    )
    order_id, base_version = order.id, order.mutation_version

    result = advance_stage_on_quest_completion(
        db_session,
        order_id=order_id,
        actor_user_id=actor.id,
        scope_hash=_H,
        request_hash=_H,
    )
    db_session.commit()

    # prerequisite-only: 전이 없음(None), stage/version 불변, 새 전이 event 0.
    assert result is None
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"
    assert saved.mutation_version == base_version
    assert (
        db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).count() == 0
    )


# --------------------------------------------------------------------------- #
# standalone DRAWING/CONFIRM stage advance 거부 (STAGE_COMMAND_REQUIRED)
# --------------------------------------------------------------------------- #
def test_standalone_drawing_advance_rejected(app):
    actor = _make_actor()
    order = _make_order(stage="DRAWING", quests=[_approved_assignee_quest("DRAWING")])
    order_id, base_version = order.id, order.mutation_version

    try:
        advance_stage_on_quest_completion(
            db_session,
            order_id=order_id,
            actor_user_id=actor.id,
            scope_hash=_H,
            request_hash=_H,
        )
        raised = None
    except StandaloneStageAdvanceError as exc:
        raised = exc
    db_session.rollback()

    assert raised is not None
    assert raised.error_code == "STAGE_COMMAND_REQUIRED"
    assert raised.status_code == 409
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.mutation_version == base_version


def test_standalone_confirm_advance_rejected(app):
    actor = _make_actor()
    order = _make_order(stage="CONFIRM", quests=[_approved_assignee_quest("CONFIRM")])
    order_id = order.id

    try:
        advance_stage_on_quest_completion(
            db_session,
            order_id=order_id,
            actor_user_id=actor.id,
            scope_hash=_H,
            request_hash=_H,
        )
        raised = None
    except StandaloneStageAdvanceError as exc:
        raised = exc
    db_session.rollback()

    assert raised is not None
    assert raised.error_code == "STAGE_COMMAND_REQUIRED"
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["workflow"]["stage"] == "CONFIRM"


# --------------------------------------------------------------------------- #
# 미완 quest 는 전이하지 않는다 (최종 승인 게이트)
# --------------------------------------------------------------------------- #
def test_incomplete_quest_blocks_transition(app):
    actor = _make_actor()
    order = _make_order(stage="RECEIVED", quests=[_open_team_quest("RECEIVED", ["CS"])])
    order_id, base_version = order.id, order.mutation_version

    try:
        advance_stage_on_quest_completion(
            db_session,
            order_id=order_id,
            actor_user_id=actor.id,
            scope_hash=_H,
            request_hash=_H,
        )
        raised = None
    except QuestIncompleteError as exc:
        raised = exc
    db_session.rollback()

    assert raised is not None
    assert raised.error_code == "QUEST_INCOMPLETE"
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["stage"] == "RECEIVED"
    assert saved.mutation_version == base_version
