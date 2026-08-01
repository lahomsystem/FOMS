"""생산 start/complete 전이 배선 계약 (STATE-PROD-01, SSOT §2.3·§5.2).

production start/complete 를 order_transition_service(STATE-CORE-00) 엔진으로 재배선한 뒤
다음을 고정한다:

* 정상 전이 CONFIRM→PRODUCTION(start)·PRODUCTION→CONSTRUCTION(complete) — mutation_version++,
  idempotency receipt, legacy OrderEvent parity(PRODUCTION_STARTED/PRODUCTION_COMPLETED),
  같은 tx outbox(STAGE_NOTIFICATION), production run 정합(발급/종결).
* production quest gate: 현재 stage quest 가 미완이면 전이 거부(상태 불변), 완료면 통과.
* team-wide: CS/SALES/PRODUCTION 200, 무관 팀 403.
* same-key(idempotency) 재요청은 전이 1회(replay) — version/event/run 중복 0.
* 5-step 하드 게이트: 존재·stage·보류·quest 전제 미충족 각각 거부.
* 357d8803 드리프트 가드(hold 해제·rework 완료 표식) 흡수 후 기존 동작 보존.

fixture/클라이언트 패턴은 test_production_transition_guard_api.py 를 준용한다(SQLite domain
lane; transition_order 의 FOR UPDATE 는 SQLite 에서 no-op, 실 PostgreSQL 경합은 PGTEST-00
lane). PG dev env 에서 실행 시에도 동일 계약이 성립한다(DSN 은 env-only).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    ProductionRun,
    User,
)


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage_code: str, *, structured_data: dict | None = None) -> Order:
    """지정 erp_stage_code 로 ERP 주문 1건 생성(workflow.stage 동기화, 추가 sd 병합)."""
    sd = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="전이 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _current_run(order_id: int) -> ProductionRun | None:
    return (
        db_session.query(ProductionRun)
        .filter(ProductionRun.order_id == order_id, ProductionRun.is_current.is_(True))
        .first()
    )


def _mint_run(order_id: int) -> ProductionRun:
    run = ProductionRun(order_id=order_id, status="IN_PROGRESS", steps=[], defects=[], is_current=True)
    db_session.add(run)
    db_session.commit()
    return run


# --------------------------------------------------------------------------- #
# 1. 정상 전이 — start: version++/receipt/event/outbox/run 발급
# --------------------------------------------------------------------------- #
def test_start_routes_through_transition_engine(client):
    """CONFIRM→PRODUCTION: transition_order 경유(version++·receipt·PRODUCTION_STARTED·outbox·run 발급)."""
    _login(client, _make_user("sp_start", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION" and saved.status == "PRODUCTION"
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"
    # mutation_version 은 전이 엔진이 1회 bump(1→2).
    assert saved.mutation_version == 2

    # legacy OrderEvent parity: transition 이 PRODUCTION_STARTED 1건을 남긴다.
    started = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STARTED").all()
    assert len(started) == 1
    assert started[0].payload["command"] == "PRODUCTION_START"
    assert started[0].payload["from"] == "CONFIRM" and started[0].payload["to"] == "PRODUCTION"

    # receipt(REV-00 helper) 1건.
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_PRODUCTION_START").count() == 1
    # 같은 tx outbox(STAGE_NOTIFICATION) 1건, ORDER_EVENT source.
    outbox = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STAGE_NOTIFICATION").all()
    assert len(outbox) == 1 and outbox[0].source_domain == "ORDER_EVENT"
    assert outbox[0].order_event_id == started[0].id
    # history 이력 append.
    assert saved.structured_data["workflow"]["history"][-1]["note"] == "제작 시작"
    # current IN_PROGRESS run 발급(run 정합).
    run = _current_run(order_id)
    assert run is not None and run.status == "IN_PROGRESS"


# --------------------------------------------------------------------------- #
# 2. 정상 전이 — complete: PRODUCTION→CONSTRUCTION, run 종결
# --------------------------------------------------------------------------- #
def test_complete_routes_through_transition_engine_and_closes_run(client):
    """PRODUCTION→CONSTRUCTION: 전이·PRODUCTION_COMPLETED·outbox + current run 을 COMPLETED 로 종결."""
    _login(client, _make_user("sp_complete", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("PRODUCTION").id
    _mint_run(order_id)  # backfill 이 발급했을 current IN_PROGRESS run.

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "CONSTRUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION" and saved.status == "CONSTRUCTION"
    assert saved.mutation_version == 2

    completed = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_COMPLETED").all()
    assert len(completed) == 1
    assert completed[0].payload["to"] == "CONSTRUCTION"
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_PRODUCTION_COMPLETE").count() == 1
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STAGE_NOTIFICATION").count() == 1

    # run 정합: current run 이 COMPLETED + is_current=False 로 종결된다.
    assert _current_run(order_id) is None
    closed = db_session.query(ProductionRun).filter_by(order_id=order_id).all()
    assert len(closed) == 1 and closed[0].status == "COMPLETED" and closed[0].is_current is False


# --------------------------------------------------------------------------- #
# 3. production quest gate — 미완 거부(상태 불변), 완료 통과
# --------------------------------------------------------------------------- #
def _quest(stage: str, approved: bool) -> dict:
    return {
        "stage": stage,
        "status": "OPEN",
        "required_approvals": [stage],
        "team_approvals": {stage: {"approved": approved, "approved_by": None, "approved_at": None}},
    }


def test_complete_blocked_when_production_quest_incomplete(client):
    """PRODUCTION quest 미완 → complete 409 QUEST_INCOMPLETE, 전이·상태 불변."""
    _login(client, _make_user("sp_q1", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("PRODUCTION", structured_data={"quests": [_quest("PRODUCTION", approved=False)]}).id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False and data["code"] == "QUEST_INCOMPLETE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 미발생
    assert saved.mutation_version == 1  # bump 없음
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_COMPLETED").count() == 0


def test_complete_succeeds_when_production_quest_complete(client):
    """PRODUCTION quest 완료 → complete 200(게이트 통과)."""
    _login(client, _make_user("sp_q2", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("PRODUCTION", structured_data={"quests": [_quest("PRODUCTION", approved=True)]}).id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONSTRUCTION"


def test_start_blocked_when_confirm_quest_incomplete(client):
    """CONFIRM quest 미완 → start 409 QUEST_INCOMPLETE, 상태 불변(start 도 quest 게이트)."""
    _login(client, _make_user("sp_q3", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("CONFIRM", structured_data={"quests": [_quest("CONFIRM", approved=False)]}).id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "QUEST_INCOMPLETE"

    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONFIRM"


# --------------------------------------------------------------------------- #
# 4. team-wide — CS/SALES/PRODUCTION 200, 무관 팀 403
# --------------------------------------------------------------------------- #
def test_team_wide_allows_cs_sales_production(client):
    """CS·SALES·PRODUCTION STAFF 모두 start 200(P0-9 team-wide, erp_edit_required 복구 금지)."""
    for i, team in enumerate(("CS", "SALES", "PRODUCTION")):
        _login(client, _make_user(f"sp_tw_{team}", role="STAFF", team=team))
        order_id = _make_order("CONFIRM").id
        resp = client.post(f"/api/orders/{order_id}/production/start", json={})
        assert resp.status_code == 200, (team, resp.get_data(as_text=True))


def test_unrelated_team_denied(client):
    """DRAWING 팀 STAFF → start 403(생산 team-wide 밖)."""
    _login(client, _make_user("sp_draw", role="STAFF", team="DRAWING"))
    order_id = _make_order("CONFIRM").id
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# 5. same-key replay — 중복 start 는 전이 1회(version/event/run 중복 0)
# --------------------------------------------------------------------------- #
def test_same_key_replay_transitions_once(client):
    """같은 idempotency key 로 start 재요청 → 200 replay, 전이/event/run 중복 0."""
    _login(client, _make_user("sp_idem", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("CONFIRM").id
    body = {"idempotency_key": "sp-replay-key-0001"}

    r1 = client.post(f"/api/orders/{order_id}/production/start", json=body)
    assert r1.status_code == 200

    r2 = client.post(f"/api/orders/{order_id}/production/start", json=body)
    assert r2.status_code == 200  # stage 가 이미 PRODUCTION 이어도 replay 로 성공

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.mutation_version == 2  # 단 1회 bump
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STARTED").count() == 1
    assert db_session.query(ProductionRun).filter_by(order_id=order_id).count() == 1  # run 중복 발급 0


# --------------------------------------------------------------------------- #
# 6. 5-step 하드 게이트 — 전제 미충족 각각 거부
# --------------------------------------------------------------------------- #
def test_gate_not_found(client):
    """존재하지 않는 주문 → 404."""
    _login(client, _make_user("sp_g0", role="STAFF", team="PRODUCTION"))
    assert client.post("/api/orders/999999/production/start", json={}).status_code == 404


def test_gate_wrong_stage(client):
    """제작대기 아님(PRODUCTION 에서 start) → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("sp_g1", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("PRODUCTION").id
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "INVALID_STAGE"
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"


def test_gate_hold_active(client):
    """보류 active → 409 HOLD_ACTIVE, 전이 미발생."""
    _login(client, _make_user("sp_g2", role="STAFF", team="PRODUCTION"))
    order_id = _make_order(
        "CONFIRM",
        structured_data={"production": {"hold": {"active": True, "reason": "자재 지연"}}},
    ).id
    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409 and resp.get_json()["code"] == "HOLD_ACTIVE"
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "CONFIRM"


# --------------------------------------------------------------------------- #
# 7. 드리프트 가드 흡수 후 기존 동작 보존
# --------------------------------------------------------------------------- #
def test_release_hold_absorbed_into_atomic_transition(client):
    """보류 + release_hold → 전이·hold 해제·토글 이벤트가 same-tx 로 커밋(드리프트 흡수)."""
    _login(client, _make_user("sp_rh", role="STAFF", team="PRODUCTION"))
    order_id = _make_order(
        "CONFIRM",
        structured_data={"production": {"hold": {"active": True, "reason": "자재 지연"}}},
    ).id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={"release_hold": True})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 발생
    assert saved.structured_data["production"]["hold"]["active"] is False  # hold 해제
    toggles = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_HOLD_TOGGLED").all()
    assert len(toggles) == 1 and toggles[0].payload["via"] == "release_on_start"
    # 전이 event 도 같은 tx: PRODUCTION_STARTED 1건.
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STARTED").count() == 1


def test_rework_completion_preserves_legacy_event_payload(client):
    """rework 상태 완료 → PRODUCTION_COMPLETED 1건에 rework=True 보존, active 해제·count 보존."""
    _login(client, _make_user("sp_rw", role="STAFF", team="PRODUCTION"))
    order_id = _make_order(
        "PRODUCTION",
        structured_data={"production": {"rework": {"active": True, "count": 2, "reason": "치수"}}},
    ).id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False and rework["count"] == 2  # active 만 해제, count 보존
    assert saved.structured_data["workflow"]["history"][-1]["note"] == "제작 완료 (재제작)"
    completed = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_COMPLETED").all()
    assert len(completed) == 1 and completed[0].payload.get("rework") is True
