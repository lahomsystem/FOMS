"""generic status/field write·admin override legacy writer 정본화 계약 (STATE-LEGACY-01, §5.2).

web order edit 의 generic status/field write(단건 /api/update_order_status, 벌크
/api/bulk_update_order_status, /api/update_order_field field=status)의 **순수 메인 파이프라인
전이**를 canonical 전이 엔진(order_transition_service ``SET_MAIN_STAGE``)으로 이관한 뒤 계약을
고정한다:

* 정상 status/field write(메인 파이프라인) → canonical command/projection: mutation_version++,
  STATE_SET_MAIN_STAGE receipt, legacy ``STAGE_CHANGED`` event(from/to·command), 같은 tx outbox,
  ``order.status`` 는 canonical projection 으로 파생. **direct order.status/workflow.stage 배정 0**.
* admin override(「단계 강제 변경」) → **reason + STAGE_OVERRIDE OrderEvent** 감사 기록(emergency
  override 만 남는 sanctioned legacy writer).
* **direct stage assignment 시도(역행·건너뛰기) → 403 거부**해 canonical override 경로로 강제.
* **새 generic stage endpoint 부재** — 기존 라우트를 canonical 로 이관했을 뿐 우회 엔드포인트 무추가.
* canonical 메인 전이는 overlay 축(logistics/hold/AS/delete)을 건드리지 않는다(orthogonal).
* 비ERP·물류 보드/overlay 타깃은 canonical 대상이 아니라 legacy writer 를 보존한다
  (그 축은 STATE-OVERLAY/STATE-AS/DELETE 소관, 이 배치 무접근).

fixture 패턴은 test_state_overlay.py 를 준용한다(SQLite domain lane; PG dev env 도 동일 계약,
DSN 은 env-only). transition_order 의 FOR UPDATE 는 SQLite 에서 no-op 이다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.order_transition_service import COMMAND_REGISTRY
from foms.services.orders.stage_override import OVERRIDE_BLOCK_MESSAGE
from foms.services.orders.state_axes import read_state_axes
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    User,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _make_user(username: str, *, role: str = "STAFF", team: str | None = "CS") -> User:
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


def _make_order(
    stage_code: str = "MEASURE",
    *,
    is_erp: bool = True,
    structured_data: dict | None = None,
) -> Order:
    sd = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="legacy 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=is_erp,
        structured_data=sd,
        erp_stage_code=stage_code if is_erp else None,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _receipts(policy_id: str) -> int:
    return db_session.query(OrderMutationReceipt).filter_by(policy_id=policy_id).count()


def _stage_changed(order_id: int) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter_by(order_id=order_id, event_type="STAGE_CHANGED")
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. 정상 status/field write(메인 파이프라인) → canonical command/projection
# --------------------------------------------------------------------------- #
def test_single_status_write_is_canonical(client):
    """단건 status API 메인 전이: version++/receipt/STAGE_CHANGED·outbox·projection, direct 배정 0."""
    _login(client, _make_user("leg_single", role="ADMIN"))
    order_id = _make_order("MEASURE").id

    resp = client.post("/api/update_order_status", json={"order_id": order_id, "status": "DRAWING"})
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    # canonical projection: status/workflow.stage/erp_stage_code 모두 DRAWING.
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.erp_stage_code == "DRAWING"
    assert saved.mutation_version == 2  # 전이 1회 bump(direct 배정이면 bump 없음)
    assert _receipts("STATE_SET_MAIN_STAGE") == 1
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="STAGE_NOTIFICATION").count() == 1

    events = _stage_changed(order_id)
    assert len(events) == 1  # canonical event 1개(legacy _sync_erp_stage 이중 기록 없음)
    assert events[0].payload["command"] == "SET_MAIN_STAGE"
    assert events[0].payload["from"] == "MEASURE"
    assert events[0].payload["to"] == "DRAWING"
    assert events[0].payload["emergency_override"] is False


def test_field_update_status_write_is_canonical(client):
    """field_update field=status 메인 전이도 canonical 엔진 경유(version++/receipt/STAGE_CHANGED)."""
    _login(client, _make_user("leg_field", role="STAFF"))
    order_id = _make_order("MEASURE").id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "DRAWING"},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.mutation_version == 2
    assert _receipts("STATE_SET_MAIN_STAGE") == 1
    events = _stage_changed(order_id)
    assert len(events) == 1
    assert events[0].payload["command"] == "SET_MAIN_STAGE"


def test_bulk_status_write_is_canonical(client):
    """벌크 status API 메인 전이: 주문별 canonical 전이(version++/STAGE_CHANGED)."""
    _login(client, _make_user("leg_bulk", role="ADMIN"))
    order_id = _make_order("MEASURE").id

    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [order_id], "status": "DRAWING"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["updated"] == 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.mutation_version == 2
    assert _receipts("STATE_SET_MAIN_STAGE") == 1
    events = _stage_changed(order_id)
    assert len(events) == 1
    assert events[0].payload["command"] == "SET_MAIN_STAGE"


def test_canonical_main_keeps_overlay_axes(client):
    """canonical 메인 전이는 logistics/hold/AS/delete 축을 건드리지 않는다(orthogonal)."""
    _login(client, _make_user("leg_orth", role="ADMIN"))
    order_id = _make_order("MEASURE").id
    before = read_state_axes(db_session.get(Order, order_id))

    client.post("/api/update_order_status", json={"order_id": order_id, "status": "DRAWING"})

    db_session.expire_all()
    after = read_state_axes(db_session.get(Order, order_id))
    assert after.main == "DRAWING"
    assert (after.logistics, after.hold, after.as_status, after.deleted) == (
        before.logistics, before.hold, before.as_status, before.deleted
    )


# --------------------------------------------------------------------------- #
# 2. admin override → emergency override 만 남되 reason + OrderEvent 필수(감사)
# --------------------------------------------------------------------------- #
def test_admin_override_records_reason_and_event(client):
    """「단계 강제 변경」 역행 → STAGE_OVERRIDE OrderEvent(reason 보존, ADMIN/MANAGER)."""
    user = _make_user("leg_override", role="MANAGER")
    user_id = user.id
    _login(client, user)
    order_id = _make_order("DRAWING").id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "실측 재방문 — 치수 오류 확인", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["mode"] == "regress"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "MEASURE"
    events = db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="STAGE_OVERRIDE"
    ).all()
    assert len(events) == 1
    assert events[0].payload["reason"].startswith("실측 재방문")  # 감사: reason 필수 기록
    assert events[0].created_by_user_id == user_id


def test_override_requires_reason_and_confirm(client):
    """emergency override 는 confirm+비어 있지 않은 reason 없으면 거부(감사 추적 강제)."""
    _login(client, _make_user("leg_ov_guard", role="ADMIN"))
    order_id = _make_order("DRAWING").id
    # confirm 누락
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "충분한 사유입니다", "confirm": False},
    ).status_code == 400
    # reason 공란
    assert client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "  ", "confirm": True},
    ).status_code == 400


# --------------------------------------------------------------------------- #
# 3. direct stage assignment 시도(역행·건너뛰기) → 거부(canonical override 경로로 강제)
# --------------------------------------------------------------------------- #
def test_regress_via_generic_endpoint_rejected_db_zero(client):
    """generic status 로 메인 역행 시도 → 403(OVERRIDE_BLOCK), DB 변화 0(version/event/receipt 0)."""
    _login(client, _make_user("leg_regress", role="ADMIN"))
    order_id = _make_order("DRAWING").id

    resp = client.post("/api/update_order_status", json={"order_id": order_id, "status": "MEASURE"})
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"  # 상태 불변
    assert saved.mutation_version == 1  # bump 없음
    assert _receipts("STATE_SET_MAIN_STAGE") == 0
    assert _stage_changed(order_id) == []


def test_skip_via_generic_endpoint_rejected(client):
    """비인접 전진(건너뛰기)도 generic status/field 에서 403 거부."""
    _login(client, _make_user("leg_skip", role="ADMIN"))
    order_id = _make_order("MEASURE").id

    assert client.post(
        "/api/update_order_status", json={"order_id": order_id, "status": "CONFIRM"}
    ).status_code == 403
    assert client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "CONFIRM"},
    ).status_code == 403


# --------------------------------------------------------------------------- #
# 4. 비ERP·물류 보드/overlay 타깃 → canonical 아님(legacy writer 보존, 무접근 축 소관)
# --------------------------------------------------------------------------- #
def test_non_erp_status_write_stays_legacy(client):
    """비ERP 주문 status write 는 canonical 대상 아님 — receipt/STAGE_CHANGED 0, version 불변."""
    _login(client, _make_user("leg_nonerp", role="ADMIN"))
    order_id = _make_order("MEASURE", is_erp=False).id

    resp = client.post("/api/update_order_status", json={"order_id": order_id, "status": "DRAWING"})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.mutation_version == 1  # canonical 아님 → bump 없음
    assert _receipts("STATE_SET_MAIN_STAGE") == 0
    assert _stage_changed(order_id) == []


def test_logistics_board_target_stays_legacy(client):
    """물류 보드 타깃(SCHEDULED)은 canonical 대상 아님 — overlay writer 보존(receipt 0)."""
    _login(client, _make_user("leg_logi", role="ADMIN"))
    order_id = _make_order("CONSTRUCTION").id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "SCHEDULED"},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "SCHEDULED"
    # 물류 중간상태: workflow.stage 오염 금지(CONSTRUCTION 보존).
    assert saved.structured_data["workflow"]["stage"] == "CONSTRUCTION"
    assert _receipts("STATE_SET_MAIN_STAGE") == 0


# --------------------------------------------------------------------------- #
# 5. 새 generic stage endpoint 부재 — canonical command 등록 + 기존 라우트만 유지
# --------------------------------------------------------------------------- #
def test_canonical_command_registered_no_new_endpoint(client):
    """SET_MAIN_STAGE canonical command 등록 + 기존 generic/override 라우트만(신규 bypass 0)."""
    assert "SET_MAIN_STAGE" in COMMAND_REGISTRY
    cmd = COMMAND_REGISTRY["SET_MAIN_STAGE"]
    assert cmd.axis == "MAIN" and cmd.event_type == "STAGE_CHANGED"

    rules = {r.rule for r in client.application.url_map.iter_rules()}
    # 기존 generic/override 라우트는 그대로 존재한다.
    assert "/api/update_order_status" in rules
    assert "/api/bulk_update_order_status" in rules
    assert "/api/update_order_field" in rules
    assert "/api/orders/<int:order_id>/workflow/stage-override" in rules
    assert "/api/orders/workflow/stage-override/bulk" in rules
    # 새 generic stage 우회 엔드포인트가 추가되지 않았다.
    lowered = " ".join(rules).lower()
    assert "set-stage" not in lowered
    assert "set_stage" not in lowered
    assert "set-main-stage" not in lowered
