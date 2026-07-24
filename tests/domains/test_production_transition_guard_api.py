"""생산 전이 전제조건 가드 계약 (P1).

- 제작 시작(POST /api/orders/<id>/production/start): 제작대기(고객컨펌/CONFIRM)에서만 허용.
  그 외 stage → 409 + code=INVALID_STAGE, message 키, 상태 불변.
- 제작 완료(POST /api/orders/<id>/production/complete): 제작중(생산/PRODUCTION)에서만 허용.
- 레거시 한글 stage 값('생산' 등)도 허용 목록에 포함.
- 시트 풋터 조건 렌더: stage/is_sales_approved 분기(제작중 → 생산 완료, 제작대기 미승인 → 고객 컨펌 전).

fixture/클라이언트 패턴은 test_production_hold_api.py 를 준용한다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


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


def _make_order(stage_code: str) -> Order:
    """지정한 erp_stage_code 로 ERP 주문 1건 생성. workflow.stage 도 동기화."""
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="전이 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _make_order_with_hold(stage_code: str, *, reason: str = "자재 입고 지연") -> Order:
    """보류(hold active) 상태의 ERP 주문 생성. workflow.stage 도 동기화."""
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
    """제작중(PRODUCTION) 주문 완료 → success, CONSTRUCTION 전이."""
    _login(client, _make_user("guard_c2"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert saved.status == "CONSTRUCTION"


def test_complete_succeeds_from_legacy_korean_stage(client):
    """레거시 한글 stage('생산') 주문 완료 → success (한글 값 허용 목록 포함)."""
    _login(client, _make_user("guard_c3"))
    order_id = _make_order("생산").id

    resp = client.post(f"/api/orders/{order_id}/production/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "CONSTRUCTION"


# --- 시작 가드 -----------------------------------------------------------------


def test_start_blocked_when_already_production(client):
    """제작중(PRODUCTION) 주문 시작 재시도 → 409 INVALID_STAGE, 상태 불변."""
    _login(client, _make_user("guard_s1"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/start", json={})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "INVALID_STAGE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION"


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


# --- 시트 풋터 조건 렌더 (P1-c) ------------------------------------------------

_SHEET_TEMPLATE = "production/partials/tablet_sheet.html"


def _sheet_ctx(**over) -> dict:
    base = {
        "id": 1,
        "customer_name": "고객",
        "load_md": "-",
        "total_units_display": "0",
        "spec_rows_view": [],
        "notes_text": "",
        "drawing_thumb": None,
        "hold_active": False,
        "hold_reason": "",
        "rework_active": False,
        "rework_reason": "",
        "stage": "제작중",
        "is_sales_approved": True,
        "change_alerts": [],
        "has_changes": False,
        "change_history": [],
        "has_change_history": False,
    }
    base.update(over)
    return base


def _render_sheet(app, **over) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template(_SHEET_TEMPLATE).render(order=_sheet_ctx(**over))


def test_sheet_production_shows_complete_button(app):
    """제작중 시트 → '생산 완료' primary 버튼(production-complete)."""
    html = _render_sheet(app, stage="제작중")
    assert 'data-tablet-sheet-action="production-complete"' in html
    assert "생산 완료" in html
    assert 'data-tablet-sheet-action="production-start"' not in html


def test_sheet_waiting_approved_shows_start_button(app):
    """제작대기 + 승인 → '제작 시작' primary 버튼(production-start)."""
    html = _render_sheet(app, stage="제작대기", is_sales_approved=True)
    assert 'data-tablet-sheet-action="production-start"' in html
    assert "제작 시작" in html


def test_sheet_waiting_unapproved_shows_muted_label(app):
    """제작대기 + 미승인 → 무채 라벨 '고객 컨펌 전', primary 버튼 없음."""
    html = _render_sheet(app, stage="제작대기", is_sales_approved=False)
    assert "고객 컨펌 전" in html
    assert 'data-tablet-sheet-action="production-start"' not in html
    assert 'data-tablet-sheet-action="production-complete"' not in html


def test_sheet_done_shows_rework_button(app):
    """제작완료 시트 → '수정 제작' primary 버튼(production-rework), start/complete 없음."""
    html = _render_sheet(app, stage="제작완료")
    assert 'data-tablet-sheet-action="production-rework"' in html
    assert "수정 제작" in html
    assert 'data-tablet-sheet-action="production-start"' not in html
    assert 'data-tablet-sheet-action="production-complete"' not in html


def test_sheet_rework_active_shows_badge_and_reason(app):
    """rework_active 시트 → 재제작 배지 + 사유 1줄(보류 배지/사유와 동일 문법)."""
    html = _render_sheet(app, stage="제작중", rework_active=True, rework_reason="치수 오류")
    assert "foms-prod-sheet__rework-badge" in html
    assert "재제작" in html
    assert "foms-prod-sheet__rework-reason" in html
    assert "치수 오류" in html


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
    assert "보류 중인 주문입니다" in data["message"]
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
