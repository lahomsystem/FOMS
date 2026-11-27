"""생산 전이 전제조건 가드 계약 (P1).

- 제작 시작(POST /api/orders/<id>/production/start): 제작대기에서만 허용 — 고객컨펌/CONFIRM(호환
  경로, CONFIRM→PRODUCTION 전이) 또는 PRODUCTION 인데 current run 이 없는 주문(2026-09-17,
  단계는 그대로 두고 run 만 발급). 그 외 → 409 + code=INVALID_STAGE, message 키, 상태 불변.
- 제작 취소: PRODUCTION + current run 이 있을 때만. 단계는 PRODUCTION 에 남고 run 만 SUPERSEDED.
- 제작 완료(POST /api/orders/<id>/production/complete): 제작중(생산/PRODUCTION)에서만 허용 + 검수까지(공정 4칸)
  끝나야 한다(2026-11-21, STEPS_INCOMPLETE 409 — 전용 시험 test_production_complete_requires_inspect.py).
- 레거시 한글 stage 값('생산' 등)도 허용 목록에 포함.
- 시트 풋터 조건 렌더: stage/is_sales_approved 분기(제작중 → 생산 완료, 제작대기 미승인 → 고객 컨펌 전).

fixture/클라이언트 패턴은 test_production_hold_api.py 를 준용한다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, ProductionRun, User
from tests.support.quest_seed import confirm_quest_completed
from tests.support.confirm_seed import drawing_for_stage
from tests.support.production_steps_seed import mark_order_inspected

_CONFIRM_STAGES = ("CONFIRM", "고객컨펌")


def _default_quests(stage_code: str, quests: list[dict] | None) -> list[dict] | None:
    """quests 가 None 이고 단계가 CONFIRM(한글 포함)이면 승인 완료 CONFIRM quest 를 자동 시드한다.

    2026-09-20 F2 부터 생산 시작의 CONFIRM 호환 경로는 quest 없음도 409 라, 이 파일의 CONFIRM
    픽스처는 기본으로 quest 를 갖는다. 한글 단계면 quest stage 도 한글로 저장해 별칭 경로를 탄다.
    """
    if quests is not None:
        return quests
    if stage_code in _CONFIRM_STAGES:
        return [confirm_quest_completed(stage=stage_code)]
    return None


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


def _make_order(stage_code: str, *, quests: list[dict] | None = None) -> Order:
    """지정한 erp_stage_code 로 ERP 주문 1건 생성. workflow.stage 도 동기화.

    ``quests`` 가 None 이면 CONFIRM 단계에 한해 승인 완료 quest 를 자동 시드한다(``_default_quests``).
    """
    sd: dict = {"workflow": {"stage": stage_code}, **drawing_for_stage(stage_code)}
    seeded = _default_quests(stage_code, quests)
    if seeded is not None:
        sd["quests"] = seeded
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


def _make_order_with_hold(stage_code: str, *, reason: str = "자재 입고 지연", quests: list[dict] | None = None) -> Order:
    """보류(hold active) 상태의 ERP 주문 생성. workflow.stage 도 동기화(CONFIRM 이면 quest 자동 시드)."""
    sd_extra: dict = {}
    seeded = _default_quests(stage_code, quests)
    if seeded is not None:
        sd_extra["quests"] = seeded
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="보류 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            **sd_extra,
            **drawing_for_stage(stage_code),
            "workflow": {"stage": stage_code},
            "production": {
                "hold": {
                    "active": True,
                    "reason": reason,
                    "at": "2026-07-24T00:00:00",
                    "by_name": "Bob",
                }
            },
        },
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mint_run(order_id: int) -> ProductionRun:
    """current IN_PROGRESS run 1건 시드(test_state_prod._mint_run 형)."""
    run = ProductionRun(order_id=order_id, status="IN_PROGRESS", steps=[], defects=[], is_current=True)
    db_session.add(run)
    db_session.commit()
    return run


def _runs(order_id: int) -> list[ProductionRun]:
    return (
        db_session.query(ProductionRun)
        .filter(ProductionRun.order_id == order_id)
        .order_by(ProductionRun.created_at.asc())
        .all()
    )


# --- 완료 가드 -----------------------------------------------------------------


def test_complete_blocked_when_not_production(client):
    """제작대기(CONFIRM) 주문 완료 시도 → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_c1"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"
    assert "message" in data  # 에러 키 = message (error 아님)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"
    assert saved.status == "CONFIRM"


def test_complete_succeeds_from_production(client):
    """제작중(PRODUCTION) + 검수까지(공정 4칸) 끝 → success, CONSTRUCTION 전이.

    2026-11-21 계약 변경: 예전엔 공정 칸 없이도 완료됐다. 이제 검수 전이면 409 STEPS_INCOMPLETE 다
    (``tests/domains/test_production_complete_requires_inspect.py``).
    """
    _login(client, _make_user("guard_c2"))
    order_id = _make_order("PRODUCTION").id
    mark_order_inspected(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert saved.status == "CONSTRUCTION"


def test_complete_succeeds_from_legacy_korean_stage(client):
    """레거시 한글 stage('생산') + 검수까지 끝 → success (한글 값 허용 목록 포함)."""
    _login(client, _make_user("guard_c3"))
    order_id = _make_order("생산").id
    mark_order_inspected(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"


# --- 시작 가드 -----------------------------------------------------------------


def test_start_from_production_without_run_mints_run(client):
    """PRODUCTION 인데 current run 이 없는 주문(제작대기) 시작 → 200, 단계 불변, run 발급.

    2026-09-17 부터 고객 컨펌 승인이 주문을 PRODUCTION 으로 옮기므로 '제작대기' 는
    run 이 없는 PRODUCTION 이다. 시작은 단계를 쓰지 않고 run 만 발급한다(version +1).
    """
    _login(client, _make_user("guard_s1"))
    order = _make_order("PRODUCTION")
    order_id, base_version = order.id, order.mutation_version

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"
    assert data["run_started"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.mutation_version == base_version + 1
    runs = _runs(order_id)
    assert len(runs) == 1
    assert runs[0].status == "IN_PROGRESS" and runs[0].is_current is True
    started = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "PRODUCTION_STARTED")
        .all()
    )
    assert len(started) == 1


def test_start_blocked_when_already_running(client):
    """PRODUCTION + current run(제작중) 시작 재시도 → 409 INVALID_STAGE, run 중복 발급 0."""
    _login(client, _make_user("guard_s1b"))
    order_id = _make_order("PRODUCTION").id
    _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert len(_runs(order_id)) == 1


def test_start_succeeds_from_confirm(client):
    """제작대기(CONFIRM) 주문 시작 → success, PRODUCTION 전이."""
    _login(client, _make_user("guard_s2"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"


def test_start_succeeds_from_legacy_korean_stage(client):
    """레거시 한글 stage('고객컨펌') 주문 시작 → success (한글 값 허용 목록 포함)."""
    _login(client, _make_user("guard_s3"))
    order_id = _make_order("고객컨펌").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


# --- 보류 게이트 (P2-c) --------------------------------------------------------


def test_start_blocked_when_hold_active(client):
    """보류(hold active) 주문 시작 → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_h1"))
    order_id = _make_order_with_hold("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "HOLD_ACTIVE"
    assert "보류 중인 주문이에요" in data["message"]
    assert "자재 입고 지연" in data["message"]  # 사유 병기
    assert data["hold"]["active"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"  # 전이 미발생
    assert saved.structured_data["production"]["hold"]["active"] is True  # hold 불변


def test_start_with_release_hold_succeeds_and_clears_hold(client):
    """보류 주문 시작 + release_hold → success, PRODUCTION 전이, hold 해제, 토글 이벤트 기록."""
    _login(client, _make_user("guard_h2"))
    order_id = _make_order_with_hold("CONFIRM").id

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 발생
    assert saved.structured_data["production"]["hold"]["active"] is False  # hold 해제

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["active"] is False
    assert events[0].payload["via"] == "release_on_start"


def test_complete_blocked_when_hold_active(client):
    """보류(hold active) 주문 완료 → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_h3"))
    order_id = _make_order_with_hold("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "HOLD_ACTIVE"
    assert data["hold"]["active"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 전이 미발생


def test_complete_with_release_hold_succeeds(client):
    """보류 주문 완료 + release_hold → success, CONSTRUCTION 전이, hold 해제, 이벤트 via 표기."""
    _login(client, _make_user("guard_h4"))
    order_id = _make_order_with_hold("PRODUCTION").id
    mark_order_inspected(order_id)  # 검수까지 끝(2026-11-21 서버 규칙)

    resp = client.post(
        f"/api/orders/{order_id}/production/complete", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert saved.structured_data["production"]["hold"]["active"] is False

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["via"] == "release_on_complete"


def test_release_hold_on_order_without_hold_is_harmless(client):
    """보류 없는 주문 + release_hold:true → 정상 전이(무해), 토글 이벤트 미기록."""
    _login(client, _make_user("guard_h5"))
    order_id = _make_order("CONFIRM").id  # hold 없음

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 0  # 보류 없으면 해제 이벤트 없음


# --- 수정 제작 (rework, P3-c) --------------------------------------------------


def test_rework_from_construction_succeeds(client):
    """제작완료(CONSTRUCTION) 주문 → rework → success, PRODUCTION 전이, rework active/count=1, 이벤트."""
    _login(client, _make_user("guard_r1"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is True
    assert rework["count"] == 1

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_REWORK_STARTED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["count"] == 1


def test_rework_then_complete_clears_active_preserves_count(client):
    """rework 후 complete → CONSTRUCTION, rework active False + count 보존, 재제작 history/이벤트."""
    _login(client, _make_user("guard_r2"))
    order_id = _make_order("CONSTRUCTION").id
    mark_order_inspected(order_id)  # 검수까지 끝(2026-11-21 서버 규칙)

    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False   # 완료 시 해제
    assert rework["count"] == 1        # count 보존
    # history 마지막 = 재제작 완료 note.
    hist = saved.structured_data["workflow"]["history"]
    assert hist[-1]["note"] == "제작 완료 (재제작)"

    completed = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETED",
        )
        .all()
    )
    assert len(completed) == 1
    assert completed[0].payload.get("rework") is True


def test_rework_second_round_increments_count(client):
    """2회차 rework → count=2 (rework → complete → rework)."""
    _login(client, _make_user("guard_r3"))
    order_id = _make_order("CONSTRUCTION").id
    mark_order_inspected(order_id)  # 검수까지 끝(2026-11-21 서버 규칙)

    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/complete", json={}).status_code == 200
    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["production"]["rework"]["count"] == 2


def test_rework_blocked_when_not_construction(client):
    """제작대기(CONFIRM) 주문 → rework → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_r4"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"


def test_rework_blocked_when_hold_active(client):
    """보류(hold active) 제작완료 주문 → rework → 409 HOLD_ACTIVE, 전이·hold 불변."""
    _login(client, _make_user("guard_r5"))
    order_id = _make_order_with_hold("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/rework", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "HOLD_ACTIVE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"  # 전이 미발생


def test_rework_with_release_hold_succeeds_via_rework(client):
    """보류 제작완료 주문 → rework + release_hold → success, PRODUCTION 전이, via=release_on_rework."""
    _login(client, _make_user("guard_r6"))
    order_id = _make_order_with_hold("CONSTRUCTION").id

    resp = client.post(
        f"/api/orders/{order_id}/production/rework", json={"release_hold": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.structured_data["production"]["hold"]["active"] is False

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_HOLD_TOGGLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["via"] == "release_on_rework"


def test_rework_reason_is_trimmed(client):
    """rework reason 은 trim 되어 저장·이벤트에 반영된다."""
    _login(client, _make_user("guard_r7"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(
        f"/api/orders/{order_id}/production/rework", json={"reason": "  치수 오류  "}
    )
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["production"]["rework"]["reason"] == "치수 오류"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_REWORK_STARTED",
        )
        .all()
    )
    assert events[0].payload["reason"] == "치수 오류"


# --- 되돌리기 2종: 제작 취소 / 완료 취소 (B-3) --------------------------------


def test_cancel_from_production_succeeds(client):
    """제작중(PRODUCTION + run) → cancel → success, 단계 PRODUCTION 유지, run SUPERSEDED, 이벤트 기록."""
    _login(client, _make_user("guard_x1"))
    order_id = _make_order("PRODUCTION").id
    _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={"reason": "  오배정  "})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    runs = _runs(order_id)
    assert len(runs) == 1
    assert runs[0].status == "SUPERSEDED" and runs[0].is_current is False

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["reason"] == "오배정"  # trim 반영


def test_cancel_blocked_when_not_production(client):
    """제작대기(CONFIRM) 주문 → cancel → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_x2"))
    order_id = _make_order("CONFIRM").id

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONFIRM"


def test_cancel_blocked_when_production_without_run(client):
    """PRODUCTION 인데 run 이 없는(제작대기) 주문 → cancel → 409 INVALID_STAGE(시작 전은 취소 불가)."""
    _login(client, _make_user("guard_x2b"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"
    assert _runs(order_id) == []


def test_uncomplete_from_construction_succeeds(client):
    """제작완료(CONSTRUCTION) 주문 → uncomplete → success, PRODUCTION(제작중) 복귀, 이벤트."""
    _login(client, _make_user("guard_x3"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_status"] == "PRODUCTION"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    assert saved.status == "PRODUCTION"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert len(events) == 1


def test_uncomplete_blocked_when_not_construction(client):
    """제작중(PRODUCTION) 주문 → uncomplete → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_x4"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"


def test_uncomplete_restores_rework_when_was_rework_completion(client):
    """재제작 완료(rework→complete) 후 uncomplete → rework active 복원 + completed_at 삭제, count 불변."""
    _login(client, _make_user("guard_x5"))
    order_id = _make_order("CONSTRUCTION").id
    mark_order_inspected(order_id)  # 검수까지 끝(2026-11-21 서버 규칙)

    # rework → complete (completed_at 기록, active False, count=1)
    assert client.post(f"/api/orders/{order_id}/production/rework", json={}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/complete", json={}).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False
    assert "completed_at" in rework  # complete 가 완료 시각 기록

    # uncomplete → 재제작 복원
    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is True         # 활성 복원
    assert "completed_at" not in rework     # 완료 시각 표식 삭제
    assert rework["count"] == 1             # 회차 불변

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert events[-1].payload["rework_restored"] is True


def test_uncomplete_leaves_non_rework_completion_untouched(client):
    """재제작 아닌 일반 완료 주문 → uncomplete → rework 무터치(생성 안 됨)."""
    _login(client, _make_user("guard_x6"))
    order_id = _make_order("CONSTRUCTION").id  # rework 없음

    resp = client.post(f"/api/orders/{order_id}/production/uncomplete", json={})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"
    production = saved.structured_data.get("production") or {}
    assert "rework" not in production  # 무터치 — rework 미생성

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_COMPLETE_REVERTED",
        )
        .all()
    )
    assert events[-1].payload["rework_restored"] is False


# --- 시트 되돌리기 버튼 조건 렌더 (B-3) ----------------------------------------


# --- 보류 운영 가시성: hold_days 파생 단위 (P7 C-1) ---------------------------


def test_production_hold_days_normal_none_and_parsefail():
    """hold_days = 오늘(KST) − 보류시작일(KST) 일수. None·파싱 실패는 None(bare except 아님)."""
    import datetime

    from foms.services.production_dashboard_display import _production_hold_days

    three_days_ago = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
    ).isoformat()
    assert _production_hold_days(three_days_ago) == 3  # 정상(UTC aware ISO → KST 일수차)
    assert _production_hold_days(None) is None          # 미입력
    assert _production_hold_days("not-a-date") is None  # 파싱 실패


# --- 완료 이력 (소실 방지 + 무채 배지, Phase E) --------------------------------


def test_release_hold_via_gate_appends_history(client):
    """전이 게이트 release(start + release_hold) 시 직전 active hold 를 hold_history 에 보존(E-a)."""
    user = _make_user("guard_e_hist")
    user_name = user.name
    _login(client, user)
    order_id = _make_order_with_hold("CONFIRM", reason="자재 입고 지연").id

    resp = client.post(
        f"/api/orders/{order_id}/production/start", json={"release_hold": True}
    )
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    history = saved.structured_data["production"]["hold_history"]
    assert len(history) == 1
    assert history[0]["reason"] == "자재 입고 지연"
    assert history[0]["at"]  # 보류 시작 시각 보존
    assert history[0]["released_at"]
    assert history[0]["released_by"] == user_name
    # hold 자체는 해제됨(이력은 별도 보존).
    assert saved.structured_data["production"]["hold"]["active"] is False


def test_enrich_row_derives_history_counts(client):
    """enriched 행에 rework_count(int)·hold_history_count(int) 파생(E-b) — 완료 후 이력 소비용."""
    from foms.services.production_dashboard_display import build_production_enriched_rows

    _login(client, _make_user("guard_e_enrich"))
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="이력 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "production": {
                "rework": {"active": False, "count": 3},
                "hold_history": [{"reason": "a"}, {"reason": "b"}],
            },
        },
        erp_stage_code="CONSTRUCTION",
    )
    db_session.add(order)
    db_session.commit()

    rows = build_production_enriched_rows([order], {})
    assert len(rows) == 1
    assert rows[0]["rework_count"] == 3
    assert rows[0]["hold_history_count"] == 2


# --- 제작 취소 깨끗한 되돌림 (F-1) --------------------------------------------


def test_quest_state_true_when_production_history_present():
    """F-1a: 제작대기 stage 라도 workflow.history 에 PRODUCTION 기록이 있으면
    is_sales_approved=True (제작 이력 = 컨펌·제작된 건 → 재시작 허용, 승인 퀘스트 없어도)."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {
        "workflow": {"history": [{"stage": "PRODUCTION"}, {"stage": "CONFIRM"}]},
        "quests": [],  # 승인 퀘스트 없음 — 이력 없었다면 False 였을 상태.
    }
    approved, quest = _production_quest_sales_state(sd, "제작대기")
    assert approved is True
    assert quest is None


def test_quest_state_true_with_legacy_korean_production_history():
    """F-1a: 레거시 한글 stage('생산') 이력도 제작 이력으로 인정."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {"workflow": {"history": [{"stage": "생산"}]}, "quests": []}
    approved, _ = _production_quest_sales_state(sd, "제작대기")
    assert approved is True


def test_quest_state_false_for_new_unapproved_without_production_history():
    """F-1a: 신규 미승인 건(history 무 PRODUCTION)은 여전히 False(고객 컨펌 전 유지)."""
    from foms.services.production_dashboard_display import _production_quest_sales_state

    sd = {"workflow": {"history": [{"stage": "CONFIRM"}]}, "quests": []}
    approved, _ = _production_quest_sales_state(sd, "제작대기")
    assert approved is False


def test_cancel_then_restart_mints_second_run(client):
    """F-1a+b 통합(2026-09-17 run 축): CONFIRM 시작(run1) → 취소(단계 PRODUCTION 유지·run1 SUPERSEDED)
    → 보드 행 제작대기·is_sales_approved=True(재시작 버튼) → 재시작 200 → run 2개(1 SUPERSEDED,
    1 IN_PROGRESS) → 보드 행 제작중."""
    from foms.services.production_dashboard_display import build_production_enriched_rows

    _login(client, _make_user("guard_f1"))
    order_id = _make_order("CONFIRM").id

    assert client.post(f"/api/orders/{order_id}/production/start", json={}).status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, order_id).erp_stage_code == "PRODUCTION"
    assert len(_runs(order_id)) == 1

    assert client.post(f"/api/orders/{order_id}/production/cancel", json={}).status_code == 200
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 단계는 그대로, run 만 종결
    runs = _runs(order_id)
    assert len(runs) == 1 and runs[0].status == "SUPERSEDED" and runs[0].is_current is False

    rows = build_production_enriched_rows([saved], {}, set())
    assert len(rows) == 1
    assert rows[0]["stage"] == "제작대기"
    assert rows[0]["is_sales_approved"] is True  # 제작 이력 → 재시작 허용

    assert client.post(f"/api/orders/{order_id}/production/start", json={}).status_code == 200
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    runs = _runs(order_id)
    assert len(runs) == 2
    assert sorted(r.status for r in runs) == ["IN_PROGRESS", "SUPERSEDED"]
    assert [r.is_current for r in runs if r.status == "IN_PROGRESS"] == [True]

    rows = build_production_enriched_rows([saved], {}, {saved.id})
    assert rows[0]["stage"] == "제작중"


def test_cancel_clears_rework_active_preserves_count(client):
    """F-1b: 제작 취소 시 rework active=False 정리(count·reason 보존)."""
    _login(client, _make_user("guard_f2"))
    order_id = _make_order("CONSTRUCTION").id

    # rework 로 제작중(PRODUCTION + run) + rework active=True, count=1 상태 진입.
    assert client.post(
        f"/api/orders/{order_id}/production/rework", json={"reason": "치수"}
    ).status_code == 200
    if not any(r.is_current for r in _runs(order_id)):
        _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"  # 단계 유지(run 만 종결)
    rework = saved.structured_data["production"]["rework"]
    assert rework["active"] is False   # 취소 시 해제
    assert rework["count"] == 1        # count 보존
    assert rework["reason"] == "치수"  # reason 보존

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["rework_cleared"] is True


def test_cancel_releases_hold_and_appends_history(client):
    """F-1b: 제작 취소 시 active hold 해제 + hold_history 보존(released_by 기록)."""
    user = _make_user("guard_f3")
    user_name = user.name
    _login(client, user)
    order_id = _make_order_with_hold("PRODUCTION", reason="자재 지연").id
    _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    prod = saved.structured_data["production"]
    assert prod["hold"]["active"] is False   # 해제
    history = prod["hold_history"]
    assert len(history) == 1
    assert history[0]["reason"] == "자재 지연"
    assert history[0]["released_at"]
    assert history[0]["released_by"] == user_name

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["hold_released"] is True


def test_cancel_without_production_flags_is_harmless(client):
    """F-1b: production 플래그 없는 일반 제작중 주문 취소 → 정리 스킵(무해), 정상 복귀."""
    _login(client, _make_user("guard_f4"))
    order_id = _make_order("PRODUCTION").id  # production dict 없음
    _mint_run(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/cancel", json={})
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"

    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.order_id == order_id,
            OrderEvent.event_type == "PRODUCTION_CANCELLED",
        )
        .all()
    )
    assert events[-1].payload["rework_cleared"] is False
    assert events[-1].payload["hold_released"] is False
