"""STATE-FORM-01: structured 폼 저장 ≠ 단계 전이 · 명시 override · stale tab.

계약:
- structured 폼 save 는 단계를 바꾸지 않는다(암묵 단계전이 0 — form save ≠ stage change).
- 단계 변경은 오직 명시적 stage-override 만: REV-00 mutation core(version/receipt)를 경유해
  ``STAGE_OVERRIDE`` audit 이벤트를 남긴다(STATE-CORE 정합 경로).
- 무효 override(비-메인 목표/짧은 사유/동일 단계)는 거부(400).
- stale tab(If-Match 불일치)은 폼·override 양쪽에서 409(오래된 탭이 상태를 덮어쓰지 못함).
"""
from __future__ import annotations

import copy
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _login(client, username: str, role: str = "ADMIN") -> User:
    """ADMIN/MANAGER 세션을 만든다(override 권한)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _structured_payload(*, stage: str = "RECEIVED", address: str = "서울 테헤란로 1") -> dict:
    """필수 필드를 갖춘 ERP structured payload(폼 저장 400 회피)."""
    return {
        "workflow": {"stage": stage},
        "flags": {"urgent": False},
        "assignments": {},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "items": [{"product_name": "붙박이장"}],
        "site": {"address_full": address, "address_main": address, "address_detail": ""},
    }


def _make_erp_order(*, stage: str = "RECEIVED") -> Order:
    """workflow.stage=status=<stage> 인 ERP 주문을 만든다."""
    order = Order(
        received_date="2026-07-01",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data=_structured_payload(stage=stage),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _current_version(client, order_id: int) -> int:
    """GET structured 로 현재 mutation_version 을 읽는다."""
    resp = client.get(f"/api/orders/{order_id}/structured")
    assert resp.status_code == 200
    return resp.get_json()["mutation_version"]


def _event_types(order_id: int) -> list[str]:
    return [
        e.event_type
        for e in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).all()
    ]


# --- 1) 폼 저장 ≠ 단계 전이 (암묵 전이 0) ------------------------------------
def test_form_save_ignores_forward_stage_change(client):
    """폼이 전진 단계(RECEIVED→MEASURE)를 보내도 서버는 단계를 바꾸지 않는다."""
    _login(client, "sf_forward")
    order = _make_erp_order(stage="RECEIVED")
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["workflow"]["stage"] = "MEASURE"
    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "RECEIVED"
    assert saved.structured_data["workflow"]["stage"] == "RECEIVED"
    # 폼 저장은 STAGE_CHANGED(암묵 단계전이) 이벤트를 만들지 않는다.
    assert "STAGE_CHANGED" not in _event_types(order_id)


def test_form_save_ignores_backward_stage_change(client):
    """폼이 역행 단계(DRAWING→MEASURE)를 보내도 서버는 서버 단계를 유지한다."""
    _login(client, "sf_backward")
    order = _make_erp_order(stage="DRAWING")
    order_id = order.id

    sd = copy.deepcopy(order.structured_data)
    sd["workflow"]["stage"] = "MEASURE"
    resp = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert "STAGE_CHANGED" not in _event_types(order_id)


# --- 2) 명시 override → REV core(version/receipt) + STAGE_OVERRIDE audit ------
def test_explicit_override_routes_through_rev_core_with_audit(client):
    """단계 변경은 override 만: REV-00 version/receipt 경유 + STAGE_OVERRIDE 감사 기록."""
    user = _login(client, "sf_override", role="MANAGER")
    order = _make_erp_order(stage="DRAWING")
    order_id = order.id
    before_version = _current_version(client, order_id)

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "실측 재방문 — 치수 재확인", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["mode"] == "regress"
    assert data["to"] == "MEASURE"
    # REV-00 mutation core 경유 증거: receipt 발급 + version 단조 증가.
    assert data["mutation_receipt"]
    assert data["mutation_version"] == before_version + 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "MEASURE"
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    assert saved.mutation_version == before_version + 1

    # audit/event: STAGE_OVERRIDE 1건(정책 사유·actor 보존), STAGE_CHANGED 없음.
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "STAGE_OVERRIDE")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["reason"].startswith("실측 재방문")
    assert events[0].created_by_user_id == user.id
    assert "STAGE_CHANGED" not in _event_types(order_id)


# --- 3) 무효 override 거부 ----------------------------------------------------
def test_invalid_override_rejected(client):
    """비-메인 목표·짧은 사유·동일 단계는 400, 상태·감사 불변."""
    _login(client, "sf_invalid")
    order = _make_erp_order(stage="DRAWING")
    order_id = order.id

    bad_target = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "AS_RECEIVED", "reason": "메인 파이프라인 아님", "confirm": True},
    )
    assert bad_target.status_code == 400

    short_reason = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "짧음", "confirm": True},
    )
    assert short_reason.status_code == 400

    same_stage = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "DRAWING", "reason": "동일 단계 거부 검증", "confirm": True},
    )
    assert same_stage.status_code == 400

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert "STAGE_OVERRIDE" not in _event_types(order_id)


# --- 4) stale tab (If-Match) → 409 ------------------------------------------
def test_form_save_stale_if_match_conflicts(client):
    """폼 저장: 오래된 If-Match(mutation_version)로 저장하면 409(상태 덮어쓰기 차단)."""
    _login(client, "sf_stale_form")
    order = _make_erp_order(stage="RECEIVED")
    order_id = order.id
    v0 = _current_version(client, order_id)
    sd = copy.deepcopy(order.structured_data)

    ok = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
        headers={"If-Match": str(v0)},
    )
    assert ok.status_code == 200, ok.get_json()

    stale = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
        headers={"If-Match": str(v0)},
    )
    assert stale.status_code == 409
    assert stale.get_json().get("code") == "REVISION_CONFLICT"


def test_stage_override_stale_if_match_conflicts(client):
    """override: 오래된 If-Match(mutation_version)로 강제 변경하면 409."""
    _login(client, "sf_stale_ovr")
    order = _make_erp_order(stage="DRAWING")
    order_id = order.id
    v0 = _current_version(client, order_id)

    ok = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "실측 재방문 — 정합 확인", "confirm": True},
        headers={"If-Match": str(v0)},
    )
    assert ok.status_code == 200, ok.get_json()

    stale = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "CONFIRM", "reason": "stale 탭 강제 변경 시도", "confirm": True},
        headers={"If-Match": str(v0)},
    )
    assert stale.status_code == 409
    assert stale.get_json().get("code") == "REVISION_CONFLICT"


# --- 5) client: override UI 는 If-Match 를 실어 stale tab 을 방어한다 ---------
def test_override_client_sends_if_match():
    """erp-stage-override.js 는 mutation_version 을 If-Match 로 전송한다(폼 저장과 분리)."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert "If-Match" in js
    assert "__erpLastMutationVersion" in js
    assert "/workflow/stage-override" in js
